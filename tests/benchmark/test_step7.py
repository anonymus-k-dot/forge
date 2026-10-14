"""Step 7: experiment config, offline plan (no provider contact), fail-closed cost and token
checks, the live execution gate, pacing, blinded export with a separate key, paired analysis
with experiment identity checks, rubric and rater notes."""

import hashlib
import io
import json
import socket

import httpx
import pytest

from forge.benchmark import blinding, experiment as experiment_module, runner as runner_module
from forge.benchmark.analysis import analyze, bootstrap_interval, render_report
from forge.benchmark.blinding import Rating, export_blind, load_ratings
from forge.benchmark.dataset import load_dataset
from forge.benchmark.experiment import (
    ExperimentConfig,
    build_plan,
    experiment_identity,
    load_experiment,
)
from forge.benchmark.runner import BenchmarkRunner
from forge.cli import main
from forge.errors import ConfigurationError
from forge.infrastructure.budgets import BudgetExceededError
from forge.infrastructure.cache import canonical_json
from forge.logging import configure_logging
from forge.providers import errors, router as router_module
from forge.providers.config import load_providers_config, parse_providers_config
from forge.providers.fake import FakeResponse
from forge.providers.openai_compatible import OpenAICompatibleAdapter
from forge.providers.router import ProviderRouter
from forge.settings import Settings
from tests.benchmark.helpers import (
    GOOD_ANSWER,
    PROVIDERS,
    REPO_ROOT,
    Responder,
    make_dataset,
    make_router,
    make_task,
    options,
    run,
    text_reply,
)
from tests.providers.helpers import RecordingSleep

EXPERIMENTS = REPO_ROOT / "benchmarks" / "experiments"
LIVE = EXPERIMENTS / "step7-pilot-v1.json"
SMOKE = EXPERIMENTS / "step7-smoke-v1.json"
REHEARSAL = EXPERIMENTS / "step7-offline-rehearsal.json"
GEMINI_PROVIDERS = EXPERIMENTS / "providers.step7-gemini.json"
EVALUATION = REPO_ROOT / "benchmarks" / "evaluation"
OWNER_GATES = [
    "account_tier_and_billing_confirmed",
    "rate_limits_checked",
    "data_use_terms_accepted",
    "thinking_risk_acknowledged",
    "live_execution_authorized",
]


@pytest.fixture(autouse=True)
def repo_cwd(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)  # experiment configs use repository-relative paths


def forbid_provider_contact(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("must not build adapters or routers, connect, or read settings")

    monkeypatch.setattr(router_module, "build_adapter", forbidden)
    monkeypatch.setattr(router_module.ProviderRouter, "__init__", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("forge.settings.Settings.from_env", forbidden)


def forbid_dotenv(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError(".env must not be read")

    monkeypatch.setattr("forge.settings.find_dotenv", forbidden)
    monkeypatch.setattr("forge.settings.load_dotenv", forbidden)


def live_data():
    return json.loads(LIVE.read_text(encoding="utf-8"))


def cleared(data=None):
    """The live config with every owner gate set (only ever used offline, in tests)."""
    data = data or live_data()
    data["live_execution_approved"] = True
    data["accounts"][0].update(
        tier_and_billing_status_confirmed=True,
        rate_limits_checked=True,
        data_use_terms_accepted=True,
        confirmed_by="test-owner",
        confirmed_on="2026-10-14",
    )
    data["thinking"]["accounting_risk_acknowledged"] = True
    return data


def write(tmp_path, data, name="experiment.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def plan_checks(tmp_path, data):
    plan = build_plan(load_experiment(write(tmp_path, data)))
    return plan, {c["check"]: c["ok"] for c in plan["checks"]}


def failed(plan):
    return [c["check"] for c in plan["checks"] if not c["ok"]]


class TestExperimentConfig:
    def test_repository_configs_are_valid_and_not_authorized(self):
        live, smoke = load_experiment(LIVE), load_experiment(SMOKE)
        rehearsal = load_experiment(REHEARSAL)
        assert not (
            live.live_execution_approved
            or smoke.live_execution_approved
            or rehearsal.live_execution_approved
        )
        v1 = load_dataset(REPO_ROOT / live.dataset.path)
        assert (live.dataset.version, live.dataset.sha256) == (v1.version, v1.sha256)
        assert live.cache == "disabled" and live.samples_per_case == 1
        assert live.conditions == ("B0", "B1", "F-legacy")
        assert smoke.dataset.task_ids == ("pilot-001",) and smoke.budget.max_model_calls == 10
        for config in (live, smoke):
            (account,) = config.accounts
            assert account.provider == "gemini" and config.thinking is not None
            assert not (
                account.tier_and_billing_status_confirmed
                or account.rate_limits_checked
                or account.data_use_terms_accepted
                or config.thinking.accounting_risk_acknowledged
            )
            (price,) = config.cost.prices
            assert (price.provider, price.provider_type, price.base_url) == (
                "gemini",
                "google_genai",
                None,
            )
            assert (price.model, price.tier, price.retrieved_on) == (
                "gemma-4-31b-it",
                "free",
                "2026-10-14",
            )
            assert price.source_url == "https://ai.google.dev/gemini-api/docs/pricing"

    @pytest.mark.parametrize(
        "change",
        [
            {"cache": "enabled"},
            {"samples_per_case": 3},
            {"unexpected": 1},
            {"pace_seconds": "5"},
            {"live_execution_approved": "yes"},
            {"thinking": {"control": "minimal", "accounting_risk_acknowledged": True}},
        ],
    )
    def test_strict_validation(self, tmp_path, change):
        data = live_data()
        data.update(change)
        with pytest.raises(ConfigurationError, match="Invalid experiment config"):
            load_experiment(write(tmp_path, data))

    @pytest.mark.parametrize(
        "field, value",
        [
            ("input_per_million_tokens", None),
            ("output_per_million_tokens", -1.0),
            ("source_url", "http://ai.google.dev/pricing"),
            ("source_url", ""),
            ("retrieved_on", "14 Oct 2026"),
            ("tier", ""),
            ("model", ""),
            ("provider", ""),
            ("provider", "Gemini"),  # provider names are exact and lowercase: no case folding
            ("provider", None),
            ("provider_type", "fake"),
            ("base_url", "https://generativelanguage.googleapis.com"),  # not for google_genai
        ],
    )
    def test_a_recorded_price_needs_complete_provenance(self, tmp_path, field, value):
        data = live_data()
        data["cost"]["prices"][0][field] = value
        with pytest.raises(ConfigurationError, match="Invalid experiment config"):
            load_experiment(write(tmp_path, data))

    def test_owner_confirmations_need_who_and_when(self, tmp_path):
        data = live_data()
        data["accounts"][0]["rate_limits_checked"] = True
        with pytest.raises(ConfigurationError, match="confirmed_by and confirmed_on"):
            load_experiment(write(tmp_path, data))


class TestOfflinePlan:
    def test_live_plan_never_contacts_a_provider_or_reads_credentials(self, monkeypatch):
        forbid_provider_contact(monkeypatch)
        forbid_dotenv(monkeypatch)
        monkeypatch.setenv("GEMINI_API_KEY", "SENTINEL-NOT-A-REAL-KEY")
        for path in (LIVE, SMOKE):
            plan = build_plan(load_experiment(path))
            assert plan["live_call_made"] is False and plan["ok"] is False
            assert "SENTINEL-NOT-A-REAL-KEY" not in json.dumps(plan)
            assert failed(plan) == OWNER_GATES  # pricing, cost and budgets pass

    def test_call_counts_and_bounds_for_pilot_v1(self, monkeypatch):
        forbid_provider_contact(monkeypatch)
        plan = build_plan(load_experiment(LIVE), config_path="benchmarks/x.json")
        assert plan["dataset"]["tasks"] == 30 and plan["logical_evaluations"] == 90
        calls = plan["calls"]
        assert (calls["rewrite_calls"], calls["target_calls"]) == (60, 90)
        assert calls["provider_attempts_first_attempt_path"] == 150
        assert calls["provider_attempts_retry_ceiling"] == 300  # max_attempts 2
        assert {c: v["target_calls"] for c, v in calls["per_condition"].items()} == {
            "B0": 30,
            "B1": 30,
            "F-legacy": 30,
        }
        tokens = plan["tokens"]
        assert (
            tokens["budget_reservation_retry_ceiling"]
            == 2 * tokens["budget_reservation_first_attempt_path"]
            == 703_272
        )
        assert tokens["budget_reservation_retry_ceiling"] <= 705_000
        assert plan["run_command"] == (
            "forge benchmark run --experiment benchmarks/x.json --confirm --allow-real-providers"
        )

    def test_smoke_plan_is_one_task_within_ten_attempts(self):
        plan = build_plan(load_experiment(SMOKE))
        assert plan["dataset"]["task_ids"] == ["pilot-001"]
        assert plan["calls"]["provider_attempts_retry_ceiling"] == 10
        assert plan["tokens"]["budget_reservation_retry_ceiling"] <= 24_000

    def test_call_budget_checks_fail_before_anything_runs(self, monkeypatch, tmp_path):
        forbid_provider_contact(monkeypatch)
        data = cleared()
        data["budget"] = {"max_model_calls": 100, "max_estimated_tokens": 1000}
        plan, checks = plan_checks(tmp_path, data)
        assert not (
            checks["budget_covers_first_attempts"]
            or checks["budget_covers_retry_ceiling"]
            or checks["token_budget_covers_retry_ceiling"]
        )
        assert plan["ok"] is False

    def test_wrong_dataset_hash_fails_preflight(self, tmp_path):
        data = cleared()
        data["dataset"]["sha256"] = "0" * 64
        plan, checks = plan_checks(tmp_path, data)
        assert checks["dataset_identity"] is False and plan["ok"] is False

    def test_rehearsal_plan_passes_and_cli_exit_codes(self, capsys):
        assert main(["benchmark", "plan", "--experiment", str(REHEARSAL)]) == 0
        assert "No provider was contacted" in capsys.readouterr().out
        assert main(["benchmark", "plan", "--experiment", str(LIVE)]) == 1  # not cleared
        out = capsys.readouterr().out
        assert "| live_execution_authorized | FAIL |" in out
        assert "| rate_limits_checked | FAIL |" in out
        assert main(["benchmark", "plan", "--experiment", str(LIVE), "--json"]) == 1
        assert json.loads(capsys.readouterr().out)["live_call_made"] is False


class TestCostFailsClosed:
    """F1: unknown prices fail; a documented zero price passes only with provenance; the
    account's tier is a separate owner check; the ceiling is enforced by the run path."""

    def test_fully_cleared_documented_zero_price_passes(self, tmp_path):
        plan, checks = plan_checks(tmp_path, cleared())
        assert plan["ok"] is True, failed(plan)
        assert checks["pricing_published"] and checks["cost_within_ceiling"]
        assert plan["cost"]["cost_at_token_budget"] == 0.0

    def test_unknown_price_fails_and_is_never_free(self, tmp_path):
        data = cleared()
        data["cost"]["prices"] = []
        plan, checks = plan_checks(tmp_path, data)
        assert checks["pricing_published"] is False and checks["cost_within_ceiling"] is False
        assert plan["cost"]["cost_at_token_budget"] is None and plan["ok"] is False

    def test_price_for_another_model_does_not_count(self, tmp_path):
        data = cleared()
        data["cost"]["prices"][0]["model"] = "gemma-4-26b-a4b-it"
        plan, checks = plan_checks(tmp_path, data)
        assert checks["pricing_published"] is False and plan["ok"] is False

    @pytest.mark.parametrize(
        "field",
        ["tier_and_billing_status_confirmed", "rate_limits_checked", "data_use_terms_accepted"],
    )
    def test_each_unconfirmed_account_check_blocks_execution(self, tmp_path, field):
        data = cleared()
        data["accounts"][0][field] = False
        plan, _ = plan_checks(tmp_path, data)
        expected = {
            "tier_and_billing_status_confirmed": "account_tier_and_billing_confirmed",
            "rate_limits_checked": "rate_limits_checked",
            "data_use_terms_accepted": "data_use_terms_accepted",
        }[field]
        assert failed(plan) == [expected]

    def test_published_free_tier_does_not_prove_the_account_tier(self, tmp_path):
        data = cleared()
        data["accounts"][0]["tier"] = "paid"  # the published price is for the free tier
        plan, checks = plan_checks(tmp_path, data)
        assert checks["pricing_published"] is True
        assert failed(plan) == ["account_tier_and_billing_confirmed"]
        data = cleared()
        data["accounts"] = []
        plan, _ = plan_checks(tmp_path, data)
        assert {"account_tier_and_billing_confirmed", "rate_limits_checked"} <= set(failed(plan))

    def test_thinking_risk_must_be_acknowledged(self, tmp_path):
        data = cleared()
        data["thinking"]["accounting_risk_acknowledged"] = False
        plan, _ = plan_checks(tmp_path, data)
        assert failed(plan) == ["thinking_risk_acknowledged"]

    def priced_provider(self, tmp_path):
        providers = {
            "default_model": "step7-target",
            "providers": {
                "priced": {
                    "type": "openai_compatible",
                    "base_url": "https://api.example.invalid/v1",
                    "api_key_env": "PRICED_TEST_KEY",
                    "max_concurrency": 1,
                    "retry": {"max_attempts": 2},
                }
            },
            "models": {
                "step7-rewriter": {"provider": "priced", "model": "priced-model"},
                "step7-target": {"provider": "priced", "model": "priced-model"},
            },
        }
        data = cleared()
        data["providers_file"] = str(write(tmp_path, providers, "providers.json"))
        data["accounts"][0]["provider"] = "priced"
        data["accounts"][0]["tier"] = "paid"
        data["cost"]["prices"] = [
            {
                **data["cost"]["prices"][0],
                "provider": "priced",
                "provider_type": "openai_compatible",
                "base_url": "https://api.example.invalid/v1",
                "model": "priced-model",
                "tier": "paid",
                "input_per_million_tokens": 0.15,
                "output_per_million_tokens": 0.60,
            }
        ]
        return data

    def test_cost_ceiling_violation(self, tmp_path):
        data = self.priced_provider(tmp_path)
        data["cost"]["ceiling"] = 0.01
        plan, checks = plan_checks(tmp_path, data)
        # Bound: 705,000 budgeted tokens x 0.60 per million = 0.423 > 0.01.
        assert plan["cost"]["cost_at_token_budget"] == 0.423
        assert failed(plan) == ["cost_within_ceiling"]
        data["cost"]["ceiling"] = 0.5
        plan, _ = plan_checks(tmp_path, data)
        assert plan["ok"] is True

    def test_nonzero_gemini_price_cannot_be_bounded(self, tmp_path):
        data = cleared()
        data["cost"]["prices"][0]["output_per_million_tokens"] = 0.01
        data["cost"]["ceiling"] = 100.0
        plan, _ = plan_checks(tmp_path, data)
        assert failed(plan) == ["cost_within_ceiling"]
        assert "thought tokens" in next(
            c["detail"] for c in plan["checks"] if c["check"] == "cost_within_ceiling"
        )

    def test_live_run_path_refuses_before_credentials_or_adapters(
        self, monkeypatch, tmp_path, capsys
    ):
        forbid_provider_contact(monkeypatch)
        forbid_dotenv(monkeypatch)
        base = ["benchmark", "run", "--allow-real-providers", "--confirm", "--output-dir"]
        for config in (LIVE, SMOKE):
            assert main([*base, str(tmp_path / "runs"), "--experiment", str(config)]) == 2
            err = capsys.readouterr().err
            assert "not cleared" in err and "rate_limits_checked" in err
        data = self.priced_provider(tmp_path)
        data["cost"]["ceiling"] = 0.01
        path = write(tmp_path, data, "over-ceiling.json")
        assert main([*base, str(tmp_path / "runs"), "--experiment", str(path)]) == 2
        assert "cost_within_ceiling" in capsys.readouterr().err
        assert not (tmp_path / "runs").exists()

    def test_a_cleared_experiment_reaches_the_runner_with_its_own_settings(
        self, monkeypatch, tmp_path, capsys
    ):
        """No provider is called: the runner is replaced by a stub that records options."""

        def forbidden(*_args, **_kwargs):
            raise AssertionError("no adapter may be built")

        seen = {}

        def stub_run(_self, run_options):
            seen["options"] = run_options
            raise ConfigurationError("STUB-RUNNER-REACHED")

        original = Settings.from_env
        monkeypatch.setattr(router_module, "build_adapter", forbidden)
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        monkeypatch.setattr(
            Settings, "from_env", classmethod(lambda _cls, environ=None: original({}))
        )
        monkeypatch.setattr(runner_module.BenchmarkRunner, "run", stub_run)
        path = write(tmp_path, cleared())
        args = ["benchmark", "run", "--experiment", str(path), "--output-dir", str(tmp_path)]
        assert main([*args, "--confirm", "--allow-real-providers"]) == 2
        assert "STUB-RUNNER-REACHED" in capsys.readouterr().err
        chosen = seen["options"]
        assert dict(chosen.budget_limits) == {
            "max_model_calls": 300,
            "max_estimated_tokens": 705_000,
            "confirm_above_model_calls": 150,
        }
        assert (chosen.pace_seconds, chosen.cache, chosen.task_ids) == (5.0, False, None)
        assert chosen.experiment == load_experiment(path)

    def test_experiment_defined_flags_cannot_be_overridden(self, tmp_path, capsys):
        args = ["benchmark", "run", "--experiment", str(REHEARSAL), "--output-dir", str(tmp_path)]
        assert main([*args, "--max-model-calls", "999"]) == 2
        assert "cannot be combined with --experiment" in capsys.readouterr().err

    def test_real_providers_need_an_experiment_even_with_the_flag(self, tmp_path, capsys):
        args = [
            "benchmark",
            "run",
            "--dataset",
            "benchmarks/pilot-v1",
            "--providers",
            str(GEMINI_PROVIDERS),
            "--target-model",
            "step7-target",
            "--conditions",
            "B0",
            "--max-model-calls",
            "300",
            "--allow-real-providers",
            "--output-dir",
            str(tmp_path),
        ]
        assert main(args) == 2
        assert "without an approved experiment config" in capsys.readouterr().err

    def test_runner_gate_refuses_uncleared_or_mismatched_runs(self, monkeypatch, tmp_path):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("no adapter may be built")

        monkeypatch.setattr(router_module, "build_adapter", forbidden)
        runner = BenchmarkRunner(ProviderRouter(load_providers_config(GEMINI_PROVIDERS)))
        common = {
            "dataset": load_dataset(REPO_ROOT / "benchmarks/pilot-v1"),
            "target_profile": "step7-target",
            "rewriter_profile": "step7-rewriter",
            "allow_real_providers": True,
            "pace_seconds": 5.0,
            "confirmed": True,
            "budget_limits": {
                "max_model_calls": 300,
                "max_estimated_tokens": 705_000,
                "confirm_above_model_calls": 150,
            },
        }
        with pytest.raises(ConfigurationError, match="not cleared.*rate_limits_checked"):
            runner.run(options(tmp_path, experiment=load_experiment(LIVE), **common))
        cleared_config = load_experiment(write(tmp_path, cleared()))
        with pytest.raises(ConfigurationError, match=r"match the experiment config \(budget\)"):
            runner.run(
                options(
                    tmp_path,
                    experiment=cleared_config,
                    **{**common, "budget_limits": {"max_model_calls": 300}},
                )
            )
        assert not (tmp_path / "runs").exists()

    def test_library_budget_is_enforced_before_any_adapter_is_built(self, monkeypatch, tmp_path):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("no adapter may be built")

        monkeypatch.setattr(router_module, "build_adapter", forbidden)
        runner = BenchmarkRunner(ProviderRouter(load_providers_config(GEMINI_PROVIDERS)))
        pilot = load_dataset(REPO_ROOT / "benchmarks/pilot-v1")
        profiles = {"target_profile": "step7-target", "rewriter_profile": "step7-rewriter"}
        with pytest.raises(ConfigurationError, match="not authorized"):
            runner.run(options(tmp_path, dataset=pilot, **profiles))
        with pytest.raises(BudgetExceededError):
            runner.run(
                options(
                    tmp_path,
                    dataset=pilot,
                    allow_real_providers=True,
                    budget_limits={"max_model_calls": 149},
                    **profiles,
                )
            )
        assert not (tmp_path / "runs").exists()


OTHER_ENDPOINT = "https://api.example.invalid/v1"


def openai_compatible(**overrides):
    return {
        "type": "openai_compatible",
        "base_url": OTHER_ENDPOINT,
        "api_key_env": "OTHER_TEST_KEY",
        "max_concurrency": 1,
        "retry": {"max_attempts": 2},
        **overrides,
    }


def confirmed_account(provider, tier="free"):
    return {
        "provider": provider,
        "tier": tier,
        "tier_and_billing_status_confirmed": True,
        "rate_limits_checked": True,
        "data_use_terms_accepted": True,
        "confirmed_by": "test-owner",
        "confirmed_on": "2026-10-14",
    }


class TestPriceBinding:
    """Prices resolve by the exact provider/model pair and provider entry; owner
    confirmations are required for every real provider."""

    def with_providers(self, tmp_path, providers, models, data=None):
        data = data or cleared()
        document = {"default_model": "step7-target", "providers": providers, "models": models}
        data["providers_file"] = str(write(tmp_path, document, "providers.json"))
        return data

    def pricing_detail(self, plan):
        return next(c["detail"] for c in plan["checks"] if c["check"] == "pricing_published")

    def test_gemini_zero_price_is_not_applied_to_another_provider_with_the_same_model(
        self, tmp_path
    ):
        same_model = {"provider": "other", "model": "gemma-4-31b-it"}
        data = self.with_providers(
            tmp_path,
            {"other": openai_compatible()},
            {"step7-rewriter": same_model, "step7-target": same_model},
        )
        data["accounts"] = [confirmed_account("other")]  # every owner check confirmed
        plan, checks = plan_checks(tmp_path, data)
        assert checks["pricing_published"] is False and checks["cost_within_ceiling"] is False
        assert "other/gemma-4-31b-it: no published price" in self.pricing_detail(plan)
        assert plan["cost"]["cost_at_token_budget"] is None and plan["ok"] is False

    def test_a_provider_alias_cannot_borrow_another_providers_price(self, tmp_path):
        # An OpenAI-compatible endpoint registered under the name "gemini": same provider
        # name and model ID as the Gemini price, but a different provider entry.
        same_model = {"provider": "gemini", "model": "gemma-4-31b-it"}
        data = self.with_providers(
            tmp_path,
            {"gemini": openai_compatible()},
            {"step7-rewriter": same_model, "step7-target": same_model},
        )
        plan, checks = plan_checks(tmp_path, data)
        assert checks["pricing_published"] is False and plan["ok"] is False
        assert "not applied" in self.pricing_detail(plan)

    def test_endpoint_must_match_for_openai_compatible_prices(self, tmp_path):
        model = {"provider": "other", "model": "priced-model"}
        data = self.with_providers(
            tmp_path,
            {"other": openai_compatible()},
            {"step7-rewriter": model, "step7-target": model},
        )
        data["accounts"] = [confirmed_account("other", tier="paid")]
        price = {
            **data["cost"]["prices"][0],
            "provider": "other",
            "provider_type": "openai_compatible",
            "base_url": "https://api.another.invalid/v1",
            "model": "priced-model",
            "tier": "paid",
        }
        data["cost"] = {"currency": "USD", "ceiling": 1.0, "prices": [price]}
        plan, checks = plan_checks(tmp_path, data)
        assert checks["pricing_published"] is False and "not applied" in self.pricing_detail(plan)
        data["cost"]["prices"][0]["base_url"] = OTHER_ENDPOINT
        plan, checks = plan_checks(tmp_path, data)
        assert checks["pricing_published"] is True and plan["ok"] is True

    def test_matching_provider_and_model_price_is_accepted(self, tmp_path):
        plan, checks = plan_checks(tmp_path, cleared())
        assert checks["pricing_published"] is True and plan["ok"] is True
        assert self.pricing_detail(plan).startswith("gemini/gemma-4-31b-it: 0 in / 0 out USD")

    def test_missing_provider_model_price_fails_closed(self, tmp_path):
        data = cleared()
        data["cost"]["prices"][0]["provider"] = "gemini-other"  # same model, another provider
        plan, checks = plan_checks(tmp_path, data)
        assert checks["pricing_published"] is False and checks["cost_within_ceiling"] is False
        assert plan["ok"] is False

    def test_duplicate_provider_model_prices_are_rejected(self, tmp_path):
        data = cleared()
        data["cost"]["prices"].append({**data["cost"]["prices"][0], "tier": "paid"})
        with pytest.raises(ConfigurationError, match="more than one published price"):
            load_experiment(write(tmp_path, data))
        data = cleared()  # the same model under another provider is a different pair
        data["cost"]["prices"].append({**data["cost"]["prices"][0], "provider": "gemini-b"})
        assert len(load_experiment(write(tmp_path, data)).cost.prices) == 2

    def multi_provider(self, tmp_path):
        data = self.with_providers(
            tmp_path,
            {
                "gemini": json.loads(GEMINI_PROVIDERS.read_text(encoding="utf-8"))["providers"][
                    "gemini"
                ],
                "priced": openai_compatible(),
            },
            {
                "step7-rewriter": {"provider": "gemini", "model": "gemma-4-31b-it"},
                "step7-target": {"provider": "priced", "model": "priced-model"},
            },
        )
        data["cost"]["ceiling"] = 0.5
        data["cost"]["prices"].append(
            {
                **data["cost"]["prices"][0],
                "provider": "priced",
                "provider_type": "openai_compatible",
                "base_url": OTHER_ENDPOINT,
                "model": "priced-model",
                "tier": "paid",
                "input_per_million_tokens": 0.15,
                "output_per_million_tokens": 0.60,
            }
        )
        return data

    def test_every_real_provider_needs_its_own_owner_confirmations(self, tmp_path):
        data = self.multi_provider(tmp_path)  # accounts: only "gemini" confirmed
        plan, checks = plan_checks(tmp_path, data)
        assert checks["pricing_published"] is True and checks["cost_within_ceiling"] is True
        assert failed(plan) == [
            "account_tier_and_billing_confirmed",
            "rate_limits_checked",
            "data_use_terms_accepted",
        ]
        detail = next(c["detail"] for c in plan["checks"] if c["check"] == "rate_limits_checked")
        assert "gemini: checked" in detail and "priced: no accounts entry" in detail
        unconfirmed = {**confirmed_account("priced", tier="paid"), "rate_limits_checked": False}
        data["accounts"].append(unconfirmed)
        plan, _ = plan_checks(tmp_path, data)
        assert failed(plan) == ["rate_limits_checked"]
        data["accounts"][-1] = confirmed_account("priced", tier="paid")
        plan, _ = plan_checks(tmp_path, data)
        assert plan["ok"] is True, failed(plan)
        assert plan["cost"]["cost_at_token_budget"] == 0.423

    def test_account_tier_must_match_each_providers_priced_tier(self, tmp_path):
        data = self.multi_provider(tmp_path)
        data["accounts"].append(confirmed_account("priced", tier="free"))  # price is "paid"
        plan, _ = plan_checks(tmp_path, data)
        assert failed(plan) == ["account_tier_and_billing_confirmed"]

    def test_one_accounts_entry_per_provider(self, tmp_path):
        data = cleared()
        data["accounts"].append(confirmed_account("gemini"))
        with pytest.raises(ConfigurationError, match="one accounts entry per provider"):
            load_experiment(write(tmp_path, data))


ENDPOINT_SECRET = "sk-test-ENDPOINT-SECRET-0a1b2c3d4e5f"
ENDPOINT_KEY_ENV = "STEP7_TEST_API_KEY"
ENDPOINT = "https://api.example.invalid/v1"
OTHER_URL = "https://api.other.invalid/v1"


def endpoint_providers(base_url=ENDPOINT):
    return {
        "default_model": "target",
        "providers": {
            "loc": {
                "type": "openai_compatible",
                "base_url": base_url,
                "api_key_env": ENDPOINT_KEY_ENV,
                "max_concurrency": 1,
                "retry": {"max_attempts": 2},
            }
        },
        "models": {
            "target": {"provider": "loc", "model": "m"},
            "rewriter": {"provider": "loc", "model": "m"},
        },
    }


class TestEndpointIdentity:
    """The run's effective endpoint must be the configured one: checked by the runner gate
    before any request, recorded in the manifest, and checked again by analysis. Requests
    go to an in-process HTTP mock (httpx.MockTransport); nothing leaves the process."""

    def experiment(self, tmp_path, dataset, providers_url=ENDPOINT):
        data = cleared()
        data["dataset"].update(id=dataset.id, version=dataset.version, sha256=dataset.sha256)
        data.update(
            target_profile="target",
            rewriter_profile="rewriter",
            pace_seconds=0.0,
            budget={"max_model_calls": 100, "max_estimated_tokens": 100_000},
            providers_file=str(
                write(tmp_path, endpoint_providers(providers_url), "providers.json")
            ),
            accounts=[confirmed_account("loc", tier="paid")],
        )
        price = {
            **data["cost"]["prices"][0],
            "provider": "loc",
            "provider_type": "openai_compatible",
            "base_url": ENDPOINT,
            "model": "m",
            "tier": "paid",
            "input_per_million_tokens": 0.15,
            "output_per_million_tokens": 0.60,
        }
        data["cost"] = {"currency": "USD", "ceiling": 1.0, "prices": [price]}
        return load_experiment(write(tmp_path, data, "endpoint-experiment.json"))

    def router(self, requests, base_url=ENDPOINT):
        def server(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "model": "m",
                    "choices": [{"message": {"content": GOOD_ANSWER}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 5},
                },
            )

        adapter = OpenAICompatibleAdapter(
            "loc",
            base_url=base_url,
            auth="bearer",
            api_key_env=ENDPOINT_KEY_ENV,
            get_secret=lambda name: ENDPOINT_SECRET if name == ENDPOINT_KEY_ENV else None,
            timeout_seconds=5,
            transport=httpx.MockTransport(server),
        )
        return ProviderRouter(
            parse_providers_config(json.dumps(endpoint_providers(base_url))),
            adapters={"loc": adapter},
            sleep=RecordingSleep(),
        )

    def run_with(self, tmp_path, dataset, experiment, router):
        return BenchmarkRunner(router).run(
            options(
                tmp_path,
                dataset=dataset,
                allow_real_providers=True,
                experiment=experiment,
                budget_limits=experiment.budget.model_dump(exclude_none=True),
            )
        )

    def completed_run(self, tmp_path):
        dataset = two_task_dataset()
        experiment = self.experiment(tmp_path, dataset)
        requests = []
        outcome = self.run_with(tmp_path, dataset, experiment, self.router(requests))
        assert outcome.status == "completed" and requests
        return outcome, dataset, experiment

    def test_matching_endpoint_is_accepted_recorded_and_free_of_secrets(self, tmp_path):
        stream = io.StringIO()
        configure_logging("INFO", stream=stream)
        try:
            outcome, dataset, experiment = self.completed_run(tmp_path)
        finally:
            configure_logging("INFO")
        manifest = json.loads((outcome.directory / "manifest.json").read_bytes())
        expected = {
            "profile": "target",
            "provider": "loc",
            "provider_type": "openai_compatible",
            "model": "m",
            "base_url": ENDPOINT,
        }
        assert manifest["experiment"]["endpoints"]["target"] == expected
        assert manifest["experiment"]["endpoints"]["rewriter"] == {
            **expected,
            "profile": "rewriter",
        }
        key_path = tmp_path / "key.json"
        export_blind(outcome.directory, dataset, tmp_path / "raters", key_path=key_path, seed=3)
        key = json.loads(key_path.read_bytes())
        report = analyze(
            outcome.directory,
            dataset,
            key,
            rate_all(key, {"B0": 1, "B1": 2, "F-legacy": 3}),
            experiment,
        )
        assert report["status"] == "complete" and report["synthetic"] is False
        artifacts = b"".join(
            path.read_bytes()
            for folder in (outcome.directory, tmp_path / "raters")
            for path in folder.iterdir()
        )
        artifacts += key_path.read_bytes()
        artifacts += json.dumps(report).encode() + render_report(report).encode()
        for forbidden in (ENDPOINT_SECRET, ENDPOINT_KEY_ENV, "Bearer"):
            assert forbidden.encode() not in artifacts
            assert forbidden not in stream.getvalue()

    def test_changed_endpoint_is_rejected_by_the_runner_before_any_request(self, tmp_path):
        dataset = two_task_dataset()
        experiment = self.experiment(tmp_path, dataset)  # configured: ENDPOINT
        requests = []
        with pytest.raises(ConfigurationError, match=r"differs from .*\(base_url\)"):
            self.run_with(tmp_path, dataset, experiment, self.router(requests, OTHER_URL))
        assert requests == [] and not (tmp_path / "runs").exists()

    @pytest.mark.parametrize("change", ["other endpoint", "removed"])
    def test_changed_endpoint_in_recorded_metadata_is_rejected_by_analysis(self, tmp_path, change):
        outcome, dataset, experiment = self.completed_run(tmp_path)
        manifest_path, run_path = (
            outcome.directory / "manifest.json",
            outcome.directory / "run.json",
        )
        manifest = json.loads(manifest_path.read_bytes())
        if change == "removed":
            del manifest["experiment"]["endpoints"]
        else:
            manifest["experiment"]["endpoints"]["target"]["base_url"] = OTHER_URL
        old_sha = json.loads(run_path.read_bytes())["manifest_sha256"]
        tampered = canonical_json(manifest)
        manifest_path.write_bytes(tampered)  # re-sealed so that only the endpoint differs
        new_sha = hashlib.sha256(tampered).hexdigest()
        run_path.write_bytes(run_path.read_bytes().replace(old_sha.encode(), new_sha.encode()))
        key_path = tmp_path / "key.json"
        export_blind(outcome.directory, dataset, tmp_path / "raters", key_path=key_path, seed=3)
        key = json.loads(key_path.read_bytes())
        with pytest.raises(ConfigurationError, match="does not match the experiment") as caught:
            analyze(
                outcome.directory,
                dataset,
                key,
                rate_all(key, {"B0": 1, "B1": 1, "F-legacy": 1}),
                experiment,
            )
        message = str(caught.value)
        if change == "removed":
            assert "target endpoint: not recorded" in message
        else:
            assert (
                f"target endpoint base_url: run has {OTHER_URL!r}, experiment expects {ENDPOINT!r}"
                in message
            )

    @pytest.mark.parametrize(
        "providers_url, accepted",
        [
            (OTHER_URL, False),
            ("https://API.example.invalid/v1", False),  # case differences are not equated
            ("https://api.example.invalid/v1/", True),  # the providers config drops one "/"
        ],
    )
    def test_analysis_compares_the_recorded_endpoint_with_the_providers_file(
        self, tmp_path, providers_url, accepted
    ):
        outcome, dataset, experiment = self.completed_run(tmp_path)
        # Same providers-file path (same config hash); only its endpoint changes.
        write(tmp_path, endpoint_providers(providers_url), "providers.json")
        key_path = tmp_path / "key.json"
        export_blind(outcome.directory, dataset, tmp_path / "raters", key_path=key_path, seed=3)
        key = json.loads(key_path.read_bytes())
        ratings = rate_all(key, {"B0": 1, "B1": 1, "F-legacy": 1})
        if accepted:
            assert (
                analyze(outcome.directory, dataset, key, ratings, experiment)["status"]
                == "complete"
            )
        else:
            with pytest.raises(ConfigurationError, match="target endpoint base_url"):
                analyze(outcome.directory, dataset, key, ratings, experiment)

    @pytest.mark.parametrize(
        "unsafe_url",
        [
            "https://user:pw-URL-SECRET@api.example.invalid/v1",
            "https://api.example.invalid/v1?key=pw-URL-SECRET",
            "https://api.example.invalid/v1#pw-URL-SECRET",
        ],
    )
    def test_endpoints_with_credentials_or_query_are_refused_without_echo(
        self, tmp_path, unsafe_url
    ):
        dataset = load_dataset(REPO_ROOT / "benchmarks/pilot-v1")
        data = cleared()
        data["providers_file"] = str(
            write(tmp_path, endpoint_providers(unsafe_url), "unsafe-providers.json")
        )
        with pytest.raises(ConfigurationError) as caught:
            build_plan(load_experiment(write(tmp_path, data)), dataset=dataset)
        assert "pw-URL-SECRET" not in str(caught.value)
        assert "base_url" in str(caught.value)


class TestTokenBudgetRequired:
    """F2: real-provider plans need a positive token budget; fake rehearsals do not."""

    def test_missing_token_budget_fails(self, tmp_path):
        data = cleared()
        del data["budget"]["max_estimated_tokens"]
        plan, checks = plan_checks(tmp_path, data)
        assert checks["token_budget_required"] is False
        assert checks["cost_within_ceiling"] is False  # cannot be bounded without it
        assert plan["ok"] is False

    @pytest.mark.parametrize("value", [0, -1, "705000", 1.5, True])
    def test_zero_negative_or_non_integer_token_budget_is_rejected(self, tmp_path, value):
        data = cleared()
        data["budget"]["max_estimated_tokens"] = value
        with pytest.raises(ConfigurationError, match="max_estimated_tokens"):
            load_experiment(write(tmp_path, data))

    def test_valid_token_budget_passes(self, tmp_path):
        plan, checks = plan_checks(tmp_path, cleared())
        assert checks["token_budget_required"] is True and plan["ok"] is True

    def test_fake_rehearsal_without_token_budget_still_plans(self, tmp_path):
        data = json.loads(REHEARSAL.read_text(encoding="utf-8"))
        del data["budget"]["max_estimated_tokens"]
        plan, checks = plan_checks(tmp_path, data)
        assert checks["token_budget_required"] is True and plan["ok"] is True


class TestOfflineRehearsalPath:
    def test_fake_experiment_run_needs_no_credentials_and_records_identity(
        self, monkeypatch, tmp_path, capsys
    ):
        forbid_dotenv(monkeypatch)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        args = ["benchmark", "run", "--experiment", str(REHEARSAL), "--confirm"]
        assert main([*args, "--output-dir", str(tmp_path)]) == 0
        result = json.loads(capsys.readouterr().out)
        manifest = json.loads((tmp_path / result["run_id"] / "manifest.json").read_bytes())
        recorded = manifest["experiment"]
        assert {k: recorded[k] for k in experiment_identity(load_experiment(REHEARSAL))} == (
            experiment_identity(load_experiment(REHEARSAL))
        )
        assert recorded["endpoints"]["target"] == {
            "profile": "step7-target",
            "provider": "fixture",
            "provider_type": "fake",
            "model": "fixture-model",
            "base_url": None,
        }


class TestPacing:
    def test_calls_are_spaced_and_recorded(self, tmp_path):
        clock = {"t": 0.0}
        sleeps = []

        def sleep(seconds):
            sleeps.append(round(seconds, 6))
            clock["t"] += seconds

        router = make_router()
        outcome = BenchmarkRunner(router, monotonic=lambda: clock["t"], sleep=sleep).run(
            options(tmp_path, pace_seconds=4.0)
        )
        assert outcome.status == "completed"
        assert sleeps == [4.0] * 4  # 5 calls (B0 1, B1 2, F-legacy 2) -> 4 waits
        run_doc = json.loads((outcome.directory / "run.json").read_bytes())
        assert run_doc["pace_seconds"] == 4.0

    def test_no_pacing_by_default(self, tmp_path):
        sleeps = []
        BenchmarkRunner(make_router(), sleep=sleeps.append).run(options(tmp_path))
        assert sleeps == []


def two_task_dataset():
    return make_dataset(make_task("task-001"), make_task("task-002"))


class TestBlinding:
    def test_rater_folder_holds_only_items_and_template(self, tmp_path):
        dataset = two_task_dataset()
        rewriter = Responder("rw", text_reply("REWRITTEN-PROMPT-MARKER"))
        outcome = run(tmp_path, make_router(rewriter), dataset=dataset)
        key_path = tmp_path / "experimenter" / "key.json"
        result = export_blind(
            outcome.directory, dataset, tmp_path / "raters", key_path=key_path, seed=11
        )
        rater_files = sorted(p.name for p in (tmp_path / "raters").iterdir())
        assert rater_files == result["rater_files"] == ["items.jsonl", "rating-template.jsonl"]
        assert key_path.is_file() and (tmp_path / "raters") not in key_path.parents
        key = json.loads(key_path.read_bytes())
        rater_text = "".join(
            (tmp_path / "raters" / name).read_text(encoding="utf-8") for name in rater_files
        )
        items = [
            json.loads(line)
            for line in (tmp_path / "raters" / "items.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert len(items) == 6
        assert all(
            set(i) == {"item_id", "task_id", "position", "task_prompt", "answer"} for i in items
        )
        for leak in (
            "B0",
            "B1",
            "F-legacy",
            "REWRITTEN-PROMPT-MARKER",
            "target-model",
            "rewriter-model",
            outcome.run_id,
            key["manifest_sha256"],
            "condition",
            "key",
        ):
            assert leak not in rater_text
        assert len({i["item_id"] for i in items}) == 6
        assert all(len(i["item_id"]) == 16 for i in items)
        assert {i["task_prompt"] for i in items} == {t.prompt for t in dataset.tasks}
        assert sorted(m["condition"] for m in key["items"].values()) == [
            "B0",
            "B0",
            "B1",
            "B1",
            "F-legacy",
            "F-legacy",
        ]

    @pytest.mark.parametrize("inside", ["raters/key.json", "raters/sub/key.json", "raters"])
    def test_key_inside_the_rater_folder_is_refused(self, tmp_path, inside):
        dataset = two_task_dataset()
        outcome = run(tmp_path, dataset=dataset)
        with pytest.raises(ConfigurationError, match="outside the rater folder"):
            export_blind(
                outcome.directory, dataset, tmp_path / "raters", key_path=tmp_path / inside, seed=1
            )
        assert not (tmp_path / "raters").exists()

    def test_existing_key_is_never_overwritten(self, tmp_path):
        dataset = two_task_dataset()
        outcome = run(tmp_path, dataset=dataset)
        key_path = tmp_path / "key.json"
        key_path.write_text("KEEP", encoding="utf-8")
        with pytest.raises(ConfigurationError, match="already exists"):
            export_blind(outcome.directory, dataset, tmp_path / "raters", key_path=key_path, seed=1)
        assert key_path.read_text(encoding="utf-8") == "KEEP"

    def test_cli_requires_a_separate_key_path(self, tmp_path):
        with pytest.raises(SystemExit):
            main(
                [
                    "benchmark",
                    "export-blind",
                    str(tmp_path),
                    "--experiment",
                    str(REHEARSAL),
                    "--out",
                    str(tmp_path / "r"),
                ]
            )

    def test_seeded_and_reproducible(self, tmp_path):
        dataset = two_task_dataset()
        outcome = run(tmp_path, dataset=dataset)
        for name, seed in (("a", 5), ("b", 5), ("c", 6)):
            export_blind(
                outcome.directory,
                dataset,
                tmp_path / name,
                key_path=tmp_path / f"{name}-key.json",
                seed=seed,
            )
        read = lambda n: (tmp_path / f"{n}-key.json").read_bytes()  # noqa: E731
        assert read("a") == read("b") and read("a") != read("c")

    def test_unratable_outcomes_are_classified(self, tmp_path):
        def target(_m, request):
            prompt = request.messages[0].content
            if "task-001" in prompt:
                return FakeResponse(())  # empty answer -> condition failure
            return (
                errors.RateLimitError("429")
                if "task-002" in prompt
                else FakeResponse((GOOD_ANSWER,))
            )

        dataset = make_dataset(
            make_task(
                "task-001", prompt="task-001: List three fruits as bullet points, under 20 words."
            ),
            make_task(
                "task-002", prompt="task-002: List three fruits as bullet points, under 20 words."
            ),
        )
        outcome = run(
            tmp_path,
            make_router(target=Responder("tg", target)),
            dataset=dataset,
            conditions=("B0",),
        )
        export_blind(
            outcome.directory, dataset, tmp_path / "blind", key_path=tmp_path / "key.json", seed=1
        )
        key = json.loads((tmp_path / "key.json").read_bytes())
        assert key["items"] == {}
        assert sorted((u["task_id"], u["category"], u["reason"]) for u in key["unrated"]) == [
            ("task-001", "condition_failure", "empty_answer"),
            ("task-002", "infrastructure", "provider_error:rate_limit"),
        ]


def rate_all(key, scores, rater="r1"):
    """Ratings from a {condition: task_success} map."""
    return [
        Rating(
            item_id=item_id,
            rater_id=rater,
            task_success=scores[m["condition"]],
            instruction_adherence=2,
            factual_error=False,
            unsupported_claim=False,
        )
        for item_id, m in key["items"].items()
    ]


def providers_file(tmp_path, name="providers.json", edit=None):
    data = json.loads(json.dumps(PROVIDERS))
    if edit:
        edit(data)
    return str(write(tmp_path, data, name))


def experiment_for(dataset, tmp_path, /, **overrides):
    """An offline experiment matching the test helpers' fake router."""
    data = json.loads(REHEARSAL.read_text(encoding="utf-8"))
    data["dataset"].update({"id": dataset.id, "version": dataset.version, "sha256": dataset.sha256})
    data.update(
        target_profile="target",
        rewriter_profile="rewriter",
        providers_file=providers_file(tmp_path),
        budget={"max_model_calls": 1000},
    )
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    return ExperimentConfig.model_validate_json(json.dumps(data))


class TestAnalysis:
    def rated_run(self, tmp_path, dataset=None, router=None, experiment_overrides=None):
        dataset = dataset or two_task_dataset()
        experiment = experiment_for(dataset, tmp_path, **(experiment_overrides or {}))
        outcome = run(tmp_path, router or make_router(), dataset=dataset, experiment=experiment)
        export_blind(
            outcome.directory, dataset, tmp_path / "blind", key_path=tmp_path / "key.json", seed=3
        )
        key = json.loads((tmp_path / "key.json").read_bytes())
        return outcome, dataset, key, experiment

    def test_synthetic_runs_are_refused_unless_explicitly_allowed(self, tmp_path):
        outcome, dataset, key, experiment = self.rated_run(tmp_path)
        ratings = rate_all(key, {"B0": 1, "B1": 2, "F-legacy": 3})
        with pytest.raises(ConfigurationError, match="not model measurements"):
            analyze(outcome.directory, dataset, key, ratings, experiment)
        report = analyze(outcome.directory, dataset, key, ratings, experiment, allow_synthetic=True)
        assert report["synthetic"] is True and report["interpretation"] == "INCONCLUSIVE"
        assert (
            report["experiment_config_sha256"] == experiment_identity(experiment)["config_sha256"]
        )

    def test_paired_comparisons_share_one_task_set(self, tmp_path):
        outcome, dataset, key, experiment = self.rated_run(tmp_path)
        ratings = rate_all(key, {"B0": 1, "B1": 2, "F-legacy": 3})
        report = analyze(outcome.directory, dataset, key, ratings, experiment, allow_synthetic=True)
        assert report["status"] == "complete"
        primary, secondary = report["primary"], report["secondary"]
        assert primary["task_ids"] == secondary["task_ids"] == report["exploratory"]["task_ids"]
        assert (primary["a"], primary["b"]) == ("F-legacy", "B0")
        assert (secondary["a"], secondary["b"]) == ("F-legacy", "B1")
        assert (primary["a_higher"], primary["tied"], primary["b_higher"]) == (2, 0, 0)
        assert primary["mean_difference"] == 2.0 and secondary["mean_difference"] == 1.0
        assert primary["bootstrap_95_interval_mean_difference"] == (2.0, 2.0)
        assert "p_value" not in json.dumps(report)

    def test_condition_failure_scores_zero_and_infrastructure_is_excluded(self, tmp_path):
        def rewrite(_m, request):
            text = request.messages[0].content
            if "task-001" in text and request.system:  # F-legacy rewrite of task-001
                return errors.InvalidRequestError("400")
            if "task-002" in text and request.system:
                return errors.UpstreamServerError("503")
            return FakeResponse(("Rewritten " + text[-60:],))

        dataset = make_dataset(
            *(
                make_task(
                    f"task-{i:03d}",
                    prompt=f"task-{i:03d}: List three fruits as bullet points, under 20 words.",
                )
                for i in range(1, 4)
            )
        )
        outcome, dataset, key, experiment = self.rated_run(
            tmp_path, dataset, make_router(Responder("rw", rewrite))
        )
        ratings = rate_all(key, {"B0": 1, "B1": 2, "F-legacy": 3})
        report = analyze(outcome.directory, dataset, key, ratings, experiment, allow_synthetic=True)
        assert report["excluded_tasks"] == {"task-002": ["F-legacy: provider_error:server_error"]}
        assert report["failures_by_condition"]["F-legacy"] == {
            "condition_failure": 1,
            "infrastructure": 1,
        }
        # 1 of 3 tasks excluded > 10%: invalid run, no comparison computed.
        assert report["status"] == "incomplete" and "primary" not in report
        # A different exclusion threshold is a different experiment: refused, not re-labelled.
        lenient_overrides = {"evaluation": {"max_excluded_task_fraction": 0.5}}
        lenient = experiment_for(dataset, tmp_path, **lenient_overrides)
        with pytest.raises(ConfigurationError, match="config_sha256"):
            analyze(outcome.directory, dataset, key, ratings, lenient, allow_synthetic=True)
        # A run made under the lenient experiment itself is analysed on one task set.
        (tmp_path / "lenient").mkdir()
        outcome, dataset, key, lenient = self.rated_run(
            tmp_path / "lenient",
            dataset,
            make_router(Responder("rw", rewrite)),
            experiment_overrides=lenient_overrides,
        )
        ratings = rate_all(key, {"B0": 1, "B1": 2, "F-legacy": 3})
        report = analyze(outcome.directory, dataset, key, ratings, lenient, allow_synthetic=True)
        assert report["primary"]["task_ids"] == ["task-001", "task-003"]
        # task-001: F-legacy failed (score 0) vs B0 1 -> B0 higher; task-003: 3 vs 1.
        assert (report["primary"]["a_higher"], report["primary"]["b_higher"]) == (1, 1)

    def test_missing_and_disputed_ratings_leave_the_analysis_incomplete(self, tmp_path):
        outcome, dataset, key, experiment = self.rated_run(tmp_path)
        full = rate_all(key, {"B0": 1, "B1": 2, "F-legacy": 3})
        report = analyze(
            outcome.directory, dataset, key, full[:-1], experiment, allow_synthetic=True
        )
        assert (
            report["status"] == "incomplete"
            and report["unresolved_items"][0]["reason"] == "not rated"
        )
        disputed = full + rate_all(key, {"B0": 3, "B1": 2, "F-legacy": 3}, rater="r2")
        report = analyze(
            outcome.directory, dataset, key, disputed, experiment, allow_synthetic=True
        )
        assert report["status"] == "incomplete"
        assert "adjudication required" in report["unresolved_items"][0]["reason"]
        b0_items = [i for i, m in key["items"].items() if m["condition"] == "B0"]
        adjudications = [
            Rating(
                item_id=i,
                rater_id="adj",
                task_success=2,
                instruction_adherence=2,
                factual_error=False,
                unsupported_claim=False,
                adjudicated=True,
            )
            for i in b0_items
        ]
        report = analyze(
            outcome.directory,
            dataset,
            key,
            disputed + adjudications,
            experiment,
            allow_synthetic=True,
        )
        assert report["status"] == "complete"
        assert report["primary"]["mean_b"] == 2.0  # adjudicated B0 score

    def test_key_must_belong_to_the_run(self, tmp_path):
        outcome, dataset, key, experiment = self.rated_run(tmp_path)
        ratings = rate_all(key, {"B0": 1, "B1": 1, "F-legacy": 1})
        with pytest.raises(ConfigurationError, match="different run"):
            analyze(
                outcome.directory,
                dataset,
                {**key, "run_id": "other"},
                ratings,
                experiment,
                allow_synthetic=True,
            )

    @pytest.mark.parametrize(
        "change, message",
        [
            ("provider", "target provider: run has 'tg', experiment expects 'tg2'"),
            ("model", "target model: run has 'target-model', experiment expects 'other-model'"),
            ("profiles", "target profile: run has 'target', experiment expects 'rewriter'"),
            ("conditions", "conditions: run has"),
            ("dataset_version", "dataset version: run has"),
            ("dataset_sha256", "dataset sha256: run has"),
            ("protocol", "experiment protocol: run has"),
            ("protocol_version", "experiment protocol_version: run has"),
        ],
    )
    def test_each_identity_mismatch_is_rejected(self, tmp_path, change, message):
        outcome, dataset, key, _ = self.rated_run(tmp_path)
        ratings = rate_all(key, {"B0": 1, "B1": 1, "F-legacy": 1})

        def rename_provider(data):
            data["providers"]["tg2"] = data["providers"].pop("tg")
            data["models"]["target"]["provider"] = "tg2"

        def rename_model(data):
            data["models"]["target"]["model"] = "other-model"

        overrides = {
            "provider": {"providers_file": providers_file(tmp_path, "p2.json", rename_provider)},
            "model": {"providers_file": providers_file(tmp_path, "p3.json", rename_model)},
            "profiles": {"target_profile": "rewriter", "rewriter_profile": "target"},
            "conditions": {"conditions": ["B0", "F-legacy"]},
            "dataset_version": {"dataset": {"version": "9.9.9"}},
            "dataset_sha256": {"dataset": {"sha256": "f" * 64}},
            "protocol": {"protocol": "docs/benchmark/other-protocol.md"},
            "protocol_version": {"protocol_version": "1.0.1"},
        }[change]
        altered = experiment_for(dataset, tmp_path, **overrides)
        with pytest.raises(ConfigurationError, match="does not match the experiment") as caught:
            analyze(outcome.directory, dataset, key, ratings, altered, allow_synthetic=True)
        assert message in str(caught.value)

    def test_run_without_recorded_experiment_is_rejected(self, tmp_path):
        dataset = two_task_dataset()
        outcome = run(tmp_path, dataset=dataset)  # no experiment gate
        export_blind(
            outcome.directory, dataset, tmp_path / "blind", key_path=tmp_path / "key.json", seed=3
        )
        key = json.loads((tmp_path / "key.json").read_bytes())
        with pytest.raises(ConfigurationError, match="records no experiment identity"):
            analyze(
                outcome.directory,
                dataset,
                key,
                rate_all(key, {"B0": 1, "B1": 1, "F-legacy": 1}),
                experiment_for(dataset, tmp_path),
                allow_synthetic=True,
            )

    def test_bootstrap_is_seeded_and_bounded(self):
        diffs = [0, 1, -1, 2, 0, 1, 1, -2, 0, 3]
        first = bootstrap_interval(diffs, resamples=2000, seed=9)
        assert first == bootstrap_interval(diffs, resamples=2000, seed=9)
        assert first[0] <= sum(diffs) / len(diffs) <= first[1]
        assert bootstrap_interval([1], resamples=2000, seed=9) is None

    def test_ratings_file_validation(self, tmp_path):
        path = tmp_path / "ratings.jsonl"
        path.write_text(
            json.dumps(
                {
                    "item_id": "0" * 16,
                    "rater_id": "r1",
                    "task_success": 4,
                    "instruction_adherence": 2,
                    "factual_error": False,
                    "unsupported_claim": False,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError, match="invalid rating"):
            load_ratings(path)


class TestEvaluationMaterials:
    def test_rubric_has_anchored_primary_scale(self):
        rubric = json.loads((EVALUATION / "rubric-v1.json").read_text(encoding="utf-8"))
        primary = rubric["dimensions"]["task_success"]
        assert primary["primary"] is True and primary["scale"] == [0, 1, 2, 3]
        assert set(primary["anchors"]) == {"0", "1", "2", "3"}
        assert set(rubric["dimensions"]["instruction_adherence"]["anchors"]) == {"0", "1", "2"}
        assert any("Length" in rule for rule in rubric["general_rules"])

    def test_rater_notes_cover_every_pilot_v1_task_version(self):
        dataset = load_dataset(REPO_ROOT / "benchmarks" / "pilot-v1")
        notes = [
            json.loads(line)
            for line in (EVALUATION / "pilot-v1-rater-notes.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert {n["task_id"]: n["task_sha256"] for n in notes} == {
            t.id: t.sha256 for t in dataset.tasks
        }
        assert all(n["kind"] in ("objective", "open") and n["note"] for n in notes)


def test_modules_reexported_for_cli():
    assert hasattr(experiment_module, "render_plan") and hasattr(blinding, "export_blind")
