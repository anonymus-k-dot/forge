"""Versioned experiment configuration, the offline execution plan and the live-run gate
(Step 7).

An experiment config pins everything a live pilot needs - dataset path/version/hash,
provider file and model profiles, conditions, budget, cache mode, pacing, evaluation seeds,
published prices, the owner's account confirmations, the thinking-mode policy, and an
explicit ``live_execution_approved`` flag (false in the repository). ``build_plan`` validates
it and computes call counts, token bounds, the budget, cost and the exact run command
**without constructing a provider adapter, reading credentials or touching the network**:
it reads only the config, the provider config file and the dataset.

Fail-closed rules for real providers (each is its own preflight check):

- a token budget (``max_estimated_tokens``) is required;
- every real provider/model pair needs a published price bound to that exact provider
  entry (provider name, provider type and, for OpenAI-compatible providers, endpoint URL)
  and model ID, with tier, source URL and retrieval date - a pair without one has an
  unknown price, never free, and a price is never applied to another provider;
- the cost at the token budget (``max_estimated_tokens`` x the highest recorded price) must
  not exceed the ceiling. The budget refuses the next call once exhausted; it does not cap
  a call's provider-reported usage, so this is not a hard cost cap;
- published pricing does not prove the owner's API project is on that tier: the owner's
  confirmations of tier/billing status, rate limits and data-use terms are separate checks,
  required for every real provider used;
- the thinking-mode policy and its accounting risk must be acknowledged;
- ``live_execution_approved`` must be true.

``check_run_against_experiment`` is the live execution gate: ``forge benchmark run
--experiment`` and the runner call it before any credential is read or adapter is built, so
a run that does not match a passing plan never starts. It compares each profile's provider,
provider type, model, retry limit and endpoint with the config's providers file and records
the run's effective endpoints in the manifest's experiment identity.

Endpoint identity (``endpoint_record``): the provider entry's ``base_url`` exactly as the
providers config stores it - that validator already rejects credentials, query strings and
fragments and removes one trailing ``/``; FORGE applies no other normalization (scheme,
host case, port or path differences are different endpoints). ``google_genai`` providers
have no ``base_url``: the endpoint is the google-genai SDK default, recorded as ``None`` with
the provider type.

Token figures use the budget system's estimate (``ceil(chars / 4) + max_output_tokens``,
``forge.infrastructure.budgets``); they are planning bounds, not provider token counts.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from importlib import metadata
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from forge.benchmark import INTERPRETATION
from forge.benchmark.conditions import (
    TARGET_PARAMS,
    get_conditions,
    target_request,
)
from forge.benchmark.dataset import Dataset, load_dataset
from forge.errors import ConfigurationError
from forge.infrastructure.budgets import BudgetLimits, estimate_reservation_tokens
from forge.infrastructure.cache import canonical_json
from forge.providers.base import GenerationParams, GenerationRequest
from forge.providers.config import ProvidersConfig, load_providers_config

EXPERIMENT_CONFIG_VERSION = 1
SHA256 = r"^[0-9a-f]{64}$"
DATE = r"^\d{4}-\d{2}-\d{2}$"
# Same rule as provider names in a providers file (lowercase; compared exactly).
PROVIDER_NAME = r"^[a-z0-9][a-z0-9_.-]{0,63}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DatasetRef(_Strict):
    path: str = Field(min_length=1)
    id: str
    version: str
    sha256: str = Field(pattern=SHA256)
    splits: tuple[Literal["dev", "heldout"], ...] = ("dev", "heldout")
    # Optional subset (e.g. the one-task smoke test); None means every task in the splits.
    task_ids: tuple[str, ...] | None = None


class BudgetConfig(_Strict):
    max_model_calls: int = Field(ge=1)
    # Required for real providers (checked by the plan); must be positive when given.
    max_estimated_tokens: int | None = Field(default=None, ge=1)
    confirm_above_model_calls: int | None = Field(default=None, ge=1)


class PublishedPrice(_Strict):
    """A price published for one model on one provider and tier, copied from an
    authoritative source. It applies only to the provider entry it names - the same provider
    name, provider type and (for OpenAI-compatible providers) endpoint URL in the providers
    file - and the same model ID, compared exactly (no case folding or aliases). A
    provider/model pair without an entry has an unknown price - never "free"."""

    provider: str = Field(pattern=PROVIDER_NAME)
    provider_type: Literal["google_genai", "openai_compatible"]
    base_url: str | None = Field(default=None, pattern=r"^https://\S+$")
    model: str = Field(min_length=1)
    tier: str = Field(min_length=1)
    input_per_million_tokens: float = Field(ge=0)
    output_per_million_tokens: float = Field(ge=0)
    source_url: str = Field(pattern=r"^https://\S+$")
    retrieved_on: str = Field(pattern=DATE)
    source_note: str = Field(min_length=1)

    @model_validator(mode="after")
    def _endpoint_matches_type(self) -> PublishedPrice:
        if self.provider_type == "google_genai" and self.base_url is not None:
            raise ValueError("google_genai prices have no base_url (fixed endpoint)")
        if self.provider_type == "openai_compatible" and self.base_url is None:
            raise ValueError("openai_compatible prices need the provider's base_url")
        return self


class CostConfig(_Strict):
    currency: str = "USD"
    ceiling: float = Field(ge=0)
    prices: tuple[PublishedPrice, ...] = ()

    @model_validator(mode="after")
    def _one_price_per_provider_and_model(self) -> CostConfig:
        pairs = [(p.provider, p.model) for p in self.prices]
        if len(set(pairs)) != len(pairs):
            raise ValueError("ambiguous: more than one published price for a provider and model")
        return self


class AccountChecks(_Strict):
    """The owner's statements about the specific API project used with one provider. They
    are account-specific: FORGE records them, it cannot verify them, and it never queries an
    account. Published pricing does not imply that a project qualifies for that tier."""

    provider: str = Field(pattern=PROVIDER_NAME)
    tier: str = Field(min_length=1)
    tier_and_billing_status_confirmed: bool
    rate_limits_checked: bool
    data_use_terms_accepted: bool
    confirmed_by: str | None = Field(default=None, min_length=1, max_length=64)
    confirmed_on: str | None = Field(default=None, pattern=DATE)

    @model_validator(mode="after")
    def _who_and_when(self) -> AccountChecks:
        confirmed = (
            self.tier_and_billing_status_confirmed
            or self.rate_limits_checked
            or self.data_use_terms_accepted
        )
        if confirmed and (self.confirmed_by is None or self.confirmed_on is None):
            raise ValueError("confirmations need confirmed_by and confirmed_on")
        return self


class ThinkingPolicy(_Strict):
    """Thinking-mode handling. The current adapter (google-genai 1.2.0) sends no thinking
    setting, so the provider's default applies; the only accepted value says so. Thought
    tokens, if any, are not in the adapter's token accounting."""

    control: Literal["provider_default"]
    accounting_risk_acknowledged: bool


class EvaluationConfig(_Strict):
    rubric: str
    rater_notes: str
    blinding_seed: int
    bootstrap_seed: int
    bootstrap_resamples: int = Field(ge=1000, le=100_000)
    max_excluded_task_fraction: float = Field(ge=0, le=1)


class ExperimentConfig(_Strict):
    config_version: Literal[1]
    experiment_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    protocol: str
    protocol_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    dataset: DatasetRef
    providers_file: str
    target_profile: str
    rewriter_profile: str
    conditions: tuple[Literal["B0", "B1", "F-legacy"], ...] = ("B0", "B1", "F-legacy")
    samples_per_case: Literal[1] = 1
    cache: Literal["disabled"] = "disabled"
    execution_order: Literal["protocol"] = "protocol"
    pace_seconds: float = Field(ge=0, le=600)
    budget: BudgetConfig
    cost: CostConfig
    # One entry per real provider used (owner confirmations are per provider).
    accounts: tuple[AccountChecks, ...] = ()
    thinking: ThinkingPolicy | None = None
    evaluation: EvaluationConfig
    live_execution_approved: bool

    @model_validator(mode="after")
    def _one_account_per_provider(self) -> ExperimentConfig:
        names = [a.provider for a in self.accounts]
        if len(set(names)) != len(names):
            raise ValueError("at most one accounts entry per provider")
        return self


def load_experiment(path: str | Path) -> ExperimentConfig:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigurationError(f"Experiment config not found: {source}") from None
    try:
        return ExperimentConfig.model_validate_json(text)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ConfigurationError(f"Invalid experiment config {source}: {problems}") from None


def config_sha256(config: ExperimentConfig) -> str:
    """Hash of the validated config content (independent of file formatting)."""
    return hashlib.sha256(canonical_json(config.model_dump(mode="json"))).hexdigest()


def endpoint_record(providers: ProvidersConfig, profile_name: str) -> dict[str, Any] | None:
    """The effective endpoint identity of one model profile (see the module docstring).

    Contains no credentials: the providers config holds only the name of the environment
    variable with the key, and its URL validator rejects user info, query strings and
    fragments; this function re-checks that before anything is recorded.
    """
    profile = providers.models.get(profile_name)
    if profile is None:
        return None
    provider = providers.providers[profile.provider]
    if provider.base_url is not None:
        parts = urlsplit(provider.base_url)
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ConfigurationError(
                f"Provider {profile.provider!r}: base_url must not contain credentials, a "
                "query string or a fragment."
            )
    return {
        "profile": profile_name,
        "provider": profile.provider,
        "provider_type": provider.type,
        "model": profile.model,
        "base_url": provider.base_url,
    }


def experiment_identity(config: ExperimentConfig) -> dict[str, str]:
    """What a run made from this config records in its manifest (checked by analysis)."""
    return {
        "id": config.experiment_id,
        "protocol": config.protocol,
        "protocol_version": config.protocol_version,
        "config_sha256": config_sha256(config),
    }


def _check(checks: list[dict[str, Any]], name: str, ok: bool, detail: str) -> bool:
    checks.append({"check": name, "ok": ok, "detail": detail})
    return ok


def _effective(request: GenerationRequest, profile_params: GenerationParams) -> GenerationRequest:
    # Same merge the router applies (request values win over profile defaults).
    return replace(request, params=request.params.merged_over(profile_params))


def _reservation(request: GenerationRequest) -> tuple[int, int]:
    """(estimated input tokens, max output tokens) as the budget would reserve them."""
    total = estimate_reservation_tokens(request)
    max_out = request.params.max_output_tokens
    if total is None or max_out is None:
        raise ConfigurationError("Every planned request needs max_output_tokens.")
    return total - max_out, max_out


def _versions() -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for package in ("google-genai", "httpx"):
        try:
            found[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            found[package] = None
    return found


def _profile(providers: ProvidersConfig, name: str) -> dict[str, Any] | None:
    profile = providers.models.get(name)
    if profile is None:
        return None
    provider = providers.providers[profile.provider]
    return {
        "profile": name,
        "provider": profile.provider,
        "provider_type": provider.type,
        "base_url": provider.base_url,
        "model": profile.model,
        "params": profile.params.to_params(),
        "max_attempts": provider.retry.max_attempts,
        "max_concurrency": provider.max_concurrency,
        "timeout_seconds": provider.timeout_seconds,
    }


def _cost_checks(
    config: ExperimentConfig,
    checks: list[dict[str, Any]],
    real_models: list[dict[str, Any]],
    tokens: dict[str, int],
) -> dict[str, Any]:
    """Token-budget, pricing, cost, account and thinking checks (one check each)."""
    budget, cost_config = config.budget, config.cost
    cost: dict[str, Any] = {
        "currency": cost_config.currency,
        "ceiling": cost_config.ceiling,
        "cost_at_token_budget": None,
        "cost_plan_estimate": None,
        "basis": "max_estimated_tokens x the highest recorded price; the budget refuses the "
        "next call once exhausted, but a call's provider-reported usage can exceed its "
        "reservation, so this is not a hard cap",
        "prices": [p.model_dump() for p in cost_config.prices],
    }
    names = (
        "token_budget_required",
        "pricing_published",
        "cost_within_ceiling",
        "account_tier_and_billing_confirmed",
        "rate_limits_checked",
        "data_use_terms_accepted",
        "thinking_risk_acknowledged",
    )
    if not real_models:
        for name in names:
            _check(checks, name, True, "fake providers only: no external calls, no cost")
        cost["cost_at_token_budget"] = 0.0
        cost["note"] = "fake providers only: no external calls"
        return cost

    has_tokens = _check(
        checks,
        "token_budget_required",
        budget.max_estimated_tokens is not None,
        f"max_estimated_tokens {budget.max_estimated_tokens}"
        if budget.max_estimated_tokens is not None
        else "missing: real-provider runs need a positive max_estimated_tokens",
    )

    # Prices resolve by the exact (provider, model) pair and must describe the same provider
    # entry (type and endpoint) as the providers file; nothing is case-folded or aliased.
    prices = {(p.provider, p.model): p for p in cost_config.prices}
    endpoints = {m["provider"]: (m["provider_type"], m["base_url"]) for m in real_models}
    pairs = sorted({(m["provider"], m["model"]) for m in real_models})
    resolved: dict[tuple[str, str], PublishedPrice] = {}
    details = []
    for provider, model in pairs:
        price = prices.get((provider, model))
        kind, url = endpoints[provider]
        if price is None:
            details.append(
                f"{provider}/{model}: no published price recorded for this provider and model "
                "- unknown, never treated as free"
            )
        elif (price.provider_type, price.base_url) != (kind, url):
            details.append(
                f"{provider}/{model}: the recorded price is for a {price.provider_type} provider "
                f"({price.base_url or 'fixed endpoint'}) but the providers file defines "
                f"{kind} ({url or 'fixed endpoint'}) - not applied"
            )
        else:
            resolved[(provider, model)] = price
            details.append(
                f"{provider}/{model}: {price.input_per_million_tokens:g} in / "
                f"{price.output_per_million_tokens:g} out {cost_config.currency} per 1M "
                f"tokens, {price.tier} tier ({price.source_url}, retrieved {price.retrieved_on})"
            )
    priced = _check(checks, "pricing_published", len(resolved) == len(pairs), "; ".join(details))

    if priced and has_tokens:
        assert budget.max_estimated_tokens is not None
        max_in = max(p.input_per_million_tokens for p in resolved.values())
        max_out = max(p.output_per_million_tokens for p in resolved.values())
        at_budget = budget.max_estimated_tokens * max(max_in, max_out) / 1_000_000
        estimate = (
            tokens["input_retry_ceiling"] * max_in + tokens["output_retry_ceiling"] * max_out
        ) / 1_000_000
        cost["cost_at_token_budget"] = round(at_budget, 4)
        cost["cost_plan_estimate"] = round(estimate, 4)
        # Thought tokens are not in the google_genai adapter's accounting; with a nonzero
        # price the budget could not bound what is billed.
        unbounded = sorted(
            f"{provider}/{model}"
            for (provider, model), price in resolved.items()
            if endpoints[provider][0] == "google_genai"
            and (price.input_per_million_tokens or price.output_per_million_tokens)
        )
        if unbounded:
            _check(
                checks,
                "cost_within_ceiling",
                False,
                f"{unbounded}: nonzero price, and thought tokens are not counted by the current "
                "Gemini adapter, so the token budget cannot bound the bill",
            )
        else:
            _check(
                checks,
                "cost_within_ceiling",
                at_budget <= cost_config.ceiling,
                f"{at_budget:.4f} {cost_config.currency} if the whole token budget "
                f"({budget.max_estimated_tokens}) is used at the highest recorded price, vs "
                f"ceiling {cost_config.ceiling}; the budget stops the next call, it does not "
                "cap the final call's reported usage",
            )
    else:
        cost["note"] = "cost cannot be established: price or token budget missing"
        _check(
            checks,
            "cost_within_ceiling",
            False,
            "cannot be established (unknown price or no token budget); unknown is not free",
        )

    # Owner confirmations are per provider: every real provider needs its own entry.
    accounts = {a.provider: a for a in config.accounts}
    providers = sorted(endpoints)

    def per_provider(name: str, what: str, confirmed: Any) -> None:
        notes, ok_all = [], True
        for provider in providers:
            account = accounts.get(provider)
            if account is None:
                ok, note = False, "no accounts entry"
            else:
                ok, note = confirmed(provider, account)
            ok_all = ok_all and ok
            notes.append(f"{provider}: {note}")
        _check(checks, name, ok_all, f"{what} - " + "; ".join(notes))

    def tier_confirmed(provider: str, account: AccountChecks) -> tuple[bool, str]:
        tiers = {p.tier for (prov, _), p in resolved.items() if prov == provider}
        if tiers - {account.tier}:
            return (
                False,
                f"account tier {account.tier!r} differs from priced tier(s) {sorted(tiers)}",
            )
        state = "confirmed" if account.tier_and_billing_status_confirmed else "not confirmed"
        return account.tier_and_billing_status_confirmed, f"tier {account.tier!r} {state}"

    per_provider(
        "account_tier_and_billing_confirmed",
        "published pricing does not prove the owner's project qualifies",
        tier_confirmed,
    )
    per_provider(
        "rate_limits_checked",
        "owner checks the model's limits in each account's own console (e.g. AI Studio)",
        lambda _p, a: (
            a.rate_limits_checked,
            "checked" if a.rate_limits_checked else "not checked",
        ),
    )
    per_provider(
        "data_use_terms_accepted",
        "owner accepts each tier's data-use terms; no sensitive, confidential or personal data",
        lambda _p, a: (
            a.data_use_terms_accepted,
            "accepted" if a.data_use_terms_accepted else "not accepted",
        ),
    )
    thinking = config.thinking
    _check(
        checks,
        "thinking_risk_acknowledged",
        thinking is not None and thinking.accounting_risk_acknowledged,
        "not recorded"
        if thinking is None
        else f"control {thinking.control} (not pinned: unsupported by the current SDK/adapter); "
        "thought tokens may be uncounted and may consume max_output_tokens - acknowledged: "
        f"{str(thinking.accounting_risk_acknowledged).lower()}",
    )
    return cost


def build_plan(
    config: ExperimentConfig,
    *,
    config_path: str | None = None,
    dataset: Dataset | None = None,
    providers: ProvidersConfig | None = None,
) -> dict[str, Any]:
    """Offline plan and preflight. Never builds adapters, reads credentials or calls out.

    ``dataset``/``providers`` default to the files the config names; the live-run gate
    passes the objects the run will actually use.
    """
    checks: list[dict[str, Any]] = []
    if dataset is None:
        dataset = load_dataset(config.dataset.path)
    _check(
        checks,
        "dataset_identity",
        (dataset.id, dataset.version, dataset.sha256)
        == (config.dataset.id, config.dataset.version, config.dataset.sha256),
        f"{dataset.id} {dataset.version} sha256 {dataset.sha256[:12]}... "
        f"(config expects {config.dataset.version} {config.dataset.sha256[:12]}...)",
    )
    tasks = dataset.select(splits=config.dataset.splits, task_ids=config.dataset.task_ids)
    conditions = get_conditions(config.conditions)
    if providers is None:
        providers = load_providers_config(config.providers_file)

    profiles: dict[str, Any] = {}
    for role, name in (("target", config.target_profile), ("rewriter", config.rewriter_profile)):
        found = _profile(providers, name)
        if _check(checks, f"{role}_profile_defined", found is not None, name):
            profiles[role] = found
    if len(profiles) < 2:
        return {"ok": False, "checks": checks, "live_call_made": False}
    target, rewriter = profiles["target"], profiles["rewriter"]
    _check(
        checks,
        "one_target_model_for_all_conditions",
        True,
        f"every condition calls {target['provider']}/{target['model']} with the same request "
        f"parameters {TARGET_PARAMS} (single target profile by construction)",
    )
    _check(
        checks,
        "same_rewriter_for_b1_and_f_legacy",
        True,
        f"{rewriter['provider']}/{rewriter['model']}",
    )
    _check(checks, "cache_disabled", config.cache == "disabled", "no cached outputs can enter")
    _check(checks, "one_sample_per_task", config.samples_per_case == 1, "samples_per_case = 1")
    _check(
        checks,
        "sequential_execution",
        target["max_concurrency"] >= 1,
        "the runner executes one call at a time in protocol order",
    )

    # Calls: per task, B0 = 1 target call; B1/F-legacy = 1 rewrite + 1 target call.
    per_condition: dict[str, dict[str, int]] = {}
    totals = {"rewrite_calls": 0, "target_calls": 0, "attempts_first": 0, "attempts_max": 0}
    tokens = {
        "input_estimate": 0,
        "output_max": 0,
        "input_retry_ceiling": 0,
        "output_retry_ceiling": 0,
        "reservation_first": 0,
        "reservation_max": 0,
    }

    def add_call(tokens_in: int, tokens_out: int, attempts: int) -> None:
        tokens["input_estimate"] += tokens_in
        tokens["output_max"] += tokens_out
        tokens["input_retry_ceiling"] += tokens_in * attempts
        tokens["output_retry_ceiling"] += tokens_out * attempts
        tokens["reservation_first"] += tokens_in + tokens_out
        tokens["reservation_max"] += (tokens_in + tokens_out) * attempts
        totals["attempts_first"] += 1
        totals["attempts_max"] += attempts

    for condition in conditions:
        c = {
            "rewrite_calls": 0,
            "target_calls": 0,
            "rewrite_input_tokens_estimate": 0,
            "rewrite_output_tokens_max": 0,
            "target_input_tokens_estimate_or_bound": 0,
            "target_output_tokens_max": 0,
        }
        for task in tasks:
            if condition.transform is not None:
                rewrite = _effective(condition.transform.build(task.prompt), rewriter["params"])
                r_in, r_out = _reservation(rewrite)
                add_call(r_in, r_out, rewriter["max_attempts"])
                c["rewrite_calls"] += 1
                c["rewrite_input_tokens_estimate"] += r_in
                c["rewrite_output_tokens_max"] += r_out
                # The rewritten prompt is at most the rewrite's output, so its size is
                # bounded by r_out tokens (a planning bound; known only at run time).
                t_in = r_out
            else:
                t_in = _reservation(_effective(target_request(task.prompt), target["params"]))[0]
            t_out = _effective(target_request(task.prompt), target["params"]).params
            assert t_out.max_output_tokens is not None
            add_call(t_in, t_out.max_output_tokens, target["max_attempts"])
            c["target_calls"] += 1
            c["target_input_tokens_estimate_or_bound"] += t_in
            c["target_output_tokens_max"] += t_out.max_output_tokens
        totals["rewrite_calls"] += c["rewrite_calls"]
        totals["target_calls"] += c["target_calls"]
        per_condition[condition.id] = c

    budget = config.budget
    _check(
        checks,
        "budget_covers_first_attempts",
        budget.max_model_calls >= totals["attempts_first"],
        f"max_model_calls {budget.max_model_calls} vs {totals['attempts_first']} first attempts",
    )
    _check(
        checks,
        "budget_covers_retry_ceiling",
        budget.max_model_calls >= totals["attempts_max"],
        f"max_model_calls {budget.max_model_calls} vs worst case {totals['attempts_max']} "
        "(every call using every allowed attempt)",
    )
    if budget.max_estimated_tokens is not None:
        _check(
            checks,
            "token_budget_covers_retry_ceiling",
            budget.max_estimated_tokens >= tokens["reservation_max"],
            f"max_estimated_tokens {budget.max_estimated_tokens} vs worst-case reservation "
            f"{tokens['reservation_max']}",
        )
    needs_confirmation = (
        budget.confirm_above_model_calls is not None
        and totals["attempts_max"] > budget.confirm_above_model_calls
    )

    real_models = [p for p in (target, rewriter) if p["provider_type"] != "fake"]
    cost = _cost_checks(config, checks, real_models, tokens)
    real = sorted({p["provider"] for p in real_models})
    _check(
        checks,
        "live_execution_authorized",
        not real or config.live_execution_approved,
        "fake providers only (offline)"
        if not real
        else f"real provider(s) {real}: live_execution_approved is "
        f"{str(config.live_execution_approved).lower()} - a live run needs the owner's "
        "explicit approval of provider/model, dataset, request and token budget, and cost "
        "ceiling",
    )

    command = ["forge benchmark run", f"--experiment {config_path or '<experiment.json>'}"]
    if needs_confirmation:
        command.append("--confirm")
    if real:
        command.append("--allow-real-providers")

    ok = all(c["ok"] for c in checks)
    return {
        "plan_version": 2,
        "experiment_id": config.experiment_id,
        "protocol_version": config.protocol_version,
        "config_sha256": config_sha256(config),
        "interpretation": INTERPRETATION,
        "ok": ok,
        "live_call_made": False,
        "dataset": {
            "id": dataset.id,
            "version": dataset.version,
            "sha256": dataset.sha256,
            "tasks": len(tasks),
            "task_ids": [t.id for t in tasks],
        },
        "conditions": [c.id for c in conditions],
        "models": {
            role: {k: v for k, v in p.items() if k != "params"}
            | {"profile_params": str(p["params"])}
            for role, p in profiles.items()
        },
        "logical_evaluations": len(tasks) * len(conditions),
        "calls": {
            "rewrite_calls": totals["rewrite_calls"],
            "target_calls": totals["target_calls"],
            "provider_attempts_first_attempt_path": totals["attempts_first"],
            "provider_attempts_retry_ceiling": totals["attempts_max"],
            "per_condition": per_condition,
        },
        "tokens": {
            "basis": "chars/4 estimate for inputs; rewritten prompts bounded by the rewrite "
            "max_output_tokens; outputs at their maximum (upper bound)",
            "input_estimate": tokens["input_estimate"],
            "output_max": tokens["output_max"],
            "input_retry_ceiling": tokens["input_retry_ceiling"],
            "output_retry_ceiling": tokens["output_retry_ceiling"],
            "budget_reservation_first_attempt_path": tokens["reservation_first"],
            "budget_reservation_retry_ceiling": tokens["reservation_max"],
        },
        "budget": budget.model_dump(),
        "pace_seconds": config.pace_seconds,
        "min_duration_seconds": round(config.pace_seconds * max(0, totals["attempts_first"] - 1)),
        "cost": cost,
        "sdk_versions": _versions(),
        "checks": checks,
        "run_command": " ".join(command),
    }


def failed_checks(plan: Mapping[str, Any]) -> list[str]:
    return [c["check"] for c in plan["checks"] if not c["ok"]]


def check_run_against_experiment(
    config: ExperimentConfig,
    *,
    dataset: Dataset,
    providers: ProvidersConfig,
    splits: Sequence[str],
    task_ids: Sequence[str] | None,
    target_profile: str,
    rewriter_profile: str | None,
    conditions: Sequence[str],
    budget_limits: Mapping[str, Any],
    pace_seconds: float,
    cache: bool,
) -> dict[str, Any]:
    """Live execution gate: the run must be exactly the planned experiment and the plan must
    pass. Raises ``ConfigurationError``; returns the identity recorded in the manifest (the
    experiment identity plus the run's effective endpoint per role).

    Runs offline (no adapter, credential or network access), before anything is sent.
    """
    problems: list[str] = []
    plan = build_plan(config, dataset=dataset, providers=providers)
    if not plan["ok"]:
        problems.append(f"preflight fails ({', '.join(failed_checks(plan))})")
    try:
        planned_providers = load_providers_config(config.providers_file)
    except (ConfigurationError, OSError):
        planned_providers = None
        problems.append(f"providers file {config.providers_file!r} cannot be read")
    if planned_providers is not None:
        for role, name in (
            ("target", config.target_profile),
            ("rewriter", config.rewriter_profile),
        ):
            planned, actual = _profile(planned_providers, name), _profile(providers, name)
            if planned is None or actual is None:
                problems.append(f"{role} profile {name!r} is not defined for this run")
                continue
            keys = ("provider", "provider_type", "model", "base_url", "max_attempts")
            differing = [k for k in keys if planned[k] != actual[k]]
            if differing:
                problems.append(
                    f"{role} profile {name!r} differs from {config.providers_file} "
                    f"({', '.join(differing)})"
                )
    expected = {
        "splits": (sorted(splits), sorted(config.dataset.splits)),
        "task selection": (
            list(task_ids) if task_ids else None,
            list(config.dataset.task_ids) if config.dataset.task_ids else None,
        ),
        "target profile": (target_profile, config.target_profile),
        "rewriter profile": (rewriter_profile, config.rewriter_profile),
        "conditions": (
            [c.id for c in get_conditions(tuple(conditions))],
            [c.id for c in get_conditions(config.conditions)],
        ),
        "budget": (
            BudgetLimits.parse(dict(budget_limits)).to_json(),
            BudgetLimits.parse(config.budget.model_dump(exclude_none=True)).to_json(),
        ),
        "pace_seconds": (float(pace_seconds), config.pace_seconds),
        "cache": (cache, False),
    }
    problems += [
        f"run does not match the experiment config ({name})"
        for name, (actual_value, wanted) in expected.items()
        if actual_value != wanted
    ]
    if problems:
        raise ConfigurationError(
            f"Experiment {config.experiment_id}: the run is not cleared - "
            + "; ".join(problems)
            + ". Nothing was sent. See `forge benchmark plan --experiment ...`."
        )
    return {
        **experiment_identity(config),
        "endpoints": {
            role: endpoint_record(providers, name)
            for role, name in (
                ("target", config.target_profile),
                ("rewriter", config.rewriter_profile),
            )
        },
    }


def render_plan(plan: dict[str, Any]) -> str:
    if "calls" not in plan:
        return json.dumps(plan, indent=2)
    cost = plan["cost"]
    at_budget = cost.get("cost_at_token_budget")
    lines = [
        f"# Offline plan - experiment `{plan['experiment_id']}`",
        "",
        "No provider was contacted, no adapter was built and no credential was read.",
        "",
        f"- Preflight: **{'PASS' if plan['ok'] else 'FAIL'}**"
        + ("" if plan["ok"] else f" (not cleared for execution: {', '.join(failed_checks(plan))})"),
        f"- Dataset: {plan['dataset']['id']} {plan['dataset']['version']} "
        f"(`{plan['dataset']['sha256']}`), {plan['dataset']['tasks']} tasks",
        f"- Conditions: {', '.join(plan['conditions'])}; logical evaluations: "
        f"{plan['logical_evaluations']}",
        f"- Calls: {plan['calls']['rewrite_calls']} rewrite + {plan['calls']['target_calls']} "
        f"target; provider attempts {plan['calls']['provider_attempts_first_attempt_path']} "
        f"(first-attempt path), at most {plan['calls']['provider_attempts_retry_ceiling']} "
        "(retry ceiling)",
        f"- Tokens (planning bounds): input ~ {plan['tokens']['input_estimate']}, output <= "
        f"{plan['tokens']['output_max']}; budget reservation <= "
        f"{plan['tokens']['budget_reservation_retry_ceiling']} with every retry",
        f"- Cost at the token budget: "
        f"{'cannot be established (FAIL)' if at_budget is None else at_budget} "
        f"{cost['currency']} (ceiling {cost['ceiling']}; budget stops the next call, not a "
        "hard cap)",
        f"- Pacing: {plan['pace_seconds']} s between calls (>= {plan['min_duration_seconds']} s)",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    lines += [
        f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} | {c['detail']} |"
        for c in plan["checks"]
    ]
    lines += [
        "",
        "Command for a later, separately authorized run (not executed):",
        "",
        f"    {plan['run_command']}",
        "",
    ]
    return "\n".join(lines)
