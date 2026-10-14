"""Paired analysis of a rated pilot run (Step 7 protocol, analysis plan v1).

Inputs: a verified, complete run; its dataset; the blinding key; human ratings; the
experiment config (for conformance, seeds and thresholds). Output: a report whose
``interpretation`` is always ``INCONCLUSIVE`` (pilot-sized sample; see the protocol).

Primary outcome: blinded human ``task_success`` (0–3) per task and condition. Per item the
score is the adjudicated rating if one exists, else the single rating, else the mean of the
raters when they differ by at most 1 point; larger disagreements without adjudication leave
the item unresolved (analysis incomplete). Condition failures (no usable answer) score 0;
infrastructure failures are excluded. Every comparison uses the same task set: the tasks
with a score under all three conditions.

Per comparison (A vs B, paired by task): tasks where A scored higher / tied / lower, mean
and median of A − B, and a percentile bootstrap interval for the mean difference (tasks
resampled with replacement; seed and resample count from the config). These are
descriptive summaries — no hypothesis test or p-value is computed.

Analysis refuses runs made with fake providers unless ``allow_synthetic`` is set, and then
labels the report SYNTHETIC. It also refuses (``ConfigurationError``) a run whose identity
differs from the experiment config: the experiment ID, protocol, protocol version and
config hash recorded in the manifest; the dataset ID, version and hash; the conditions; the
target and rewriter profiles and the provider, provider type and model behind each (from
the config's provider file); the recorded effective endpoint of each role (provider,
type, model and ``base_url``, compared exactly); every execution's role →
profile/provider/model mapping;
samples per case, cache and budget. A run made without ``--experiment`` has no recorded
identity and is refused.
"""

from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from forge.benchmark import INTERPRETATION
from forge.benchmark.blinding import Rating, classify_unrated
from forge.benchmark.dataset import Dataset
from forge.benchmark.experiment import ExperimentConfig, experiment_identity
from forge.benchmark.records import ResultRecord
from forge.benchmark.verify import verify_run
from forge.errors import ConfigurationError
from forge.infrastructure.budgets import BudgetLimits
from forge.providers.config import load_providers_config

ANALYSIS_VERSION = 1
PRIMARY = ("F-legacy", "B0")
SECONDARY = ("F-legacy", "B1")
EXPLORATORY = ("B1", "B0")


def _records(directory: Path) -> list[ResultRecord]:
    return [
        ResultRecord.model_validate_json(line)
        for line in (directory / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _resolve(ratings: list[Rating]) -> tuple[dict[str, Any] | None, str | None]:
    """Final scores for one item, or (None, reason) if unresolved."""
    adjudicated = [r for r in ratings if r.adjudicated]
    if len(adjudicated) > 1:
        return None, "several adjudicated ratings"
    if adjudicated:
        r = adjudicated[0]
        return {
            "task_success": float(r.task_success),
            "instruction_adherence": float(r.instruction_adherence),
            "factual_error": r.factual_error,
            "unsupported_claim": r.unsupported_claim,
        }, None
    if len({r.rater_id for r in ratings}) != len(ratings):
        return None, "a rater rated the same item twice"
    scores = [r.task_success for r in ratings]
    if max(scores) - min(scores) > 1:
        return None, "raters differ by more than 1 point; adjudication required"
    return {
        "task_success": statistics.fmean(scores),
        "instruction_adherence": statistics.fmean(r.instruction_adherence for r in ratings),
        # Conservative: a flag raised by any rater stands unless adjudicated.
        "factual_error": any(r.factual_error for r in ratings),
        "unsupported_claim": any(r.unsupported_claim for r in ratings),
    }, None


def bootstrap_interval(
    differences: list[float], *, resamples: int, seed: int
) -> tuple[float, float] | None:
    """95% percentile bootstrap interval of the mean paired difference (descriptive)."""
    n = len(differences)
    if n < 2:
        return None
    rng = random.Random(seed)
    means = sorted(
        sum(differences[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)
    )
    low = means[int(0.025 * resamples)]
    high = means[min(resamples - 1, int(0.975 * resamples))]
    return round(low, 4), round(high, 4)


def _compare(
    a: str,
    b: str,
    scores: dict[tuple[str, str], float],
    tasks: list[str],
    *,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    diffs = [scores[(t, a)] - scores[(t, b)] for t in tasks]
    interval = bootstrap_interval(diffs, resamples=resamples, seed=seed)
    return {
        "a": a,
        "b": b,
        "tasks": len(tasks),
        "task_ids": tasks,
        "a_higher": sum(d > 0 for d in diffs),
        "tied": sum(d == 0 for d in diffs),
        "b_higher": sum(d < 0 for d in diffs),
        "mean_a": round(statistics.fmean(scores[(t, a)] for t in tasks), 4) if tasks else None,
        "mean_b": round(statistics.fmean(scores[(t, b)] for t in tasks), 4) if tasks else None,
        "mean_difference": round(statistics.fmean(diffs), 4) if diffs else None,
        "median_difference": statistics.median(diffs) if diffs else None,
        "bootstrap_95_interval_mean_difference": interval,
    }


def _identity_mismatches(
    manifest: dict[str, Any],
    run_doc: dict[str, Any],
    records: list[ResultRecord],
    experiment: ExperimentConfig,
) -> list[str]:
    """Every way the run differs from the experiment config (empty if it conforms)."""
    problems: list[str] = []

    def compare(name: str, actual: Any, expected: Any) -> None:
        if actual != expected:
            problems.append(f"{name}: run has {actual!r}, experiment expects {expected!r}")

    recorded = manifest.get("experiment")
    if not isinstance(recorded, dict):
        problems.append("the run records no experiment identity (it was not run with --experiment)")
        recorded = {}
    expected_identity = experiment_identity(experiment)
    recorded_endpoints = recorded.get("endpoints")
    for field in ("id", "protocol", "protocol_version", "config_sha256"):
        compare(f"experiment {field}", recorded.get(field), expected_identity[field])

    compare("dataset id", manifest["dataset"]["id"], experiment.dataset.id)
    compare("dataset version", manifest["dataset"]["version"], experiment.dataset.version)
    compare("dataset sha256", manifest["dataset"]["sha256"], experiment.dataset.sha256)
    compare("conditions", [c["id"] for c in manifest["conditions"]], list(experiment.conditions))
    compare("samples per case", manifest["samples_per_case"], experiment.samples_per_case)
    compare("cache enabled", run_doc["cache"]["enabled"], False)
    compare(
        "budget",
        BudgetLimits.parse(run_doc["budget_limits"]).to_json(),
        BudgetLimits.parse(experiment.budget.model_dump(exclude_none=True)).to_json(),
    )

    try:
        providers = load_providers_config(experiment.providers_file)
    except (ConfigurationError, OSError):
        problems.append(f"providers file {experiment.providers_file!r} cannot be read")
        return problems
    expected_roles: dict[str, dict[str, Any]] = {}
    for role, name in (
        ("target", experiment.target_profile),
        ("rewriter", experiment.rewriter_profile),
    ):
        profile = providers.models.get(name)
        if profile is None:
            problems.append(
                f"{role} profile {name!r} is not defined in {experiment.providers_file}"
            )
            continue
        expected_roles[role] = {
            "profile": name,
            "provider": profile.provider,
            "provider_type": providers.providers[profile.provider].type,
            "model": profile.model,
        }
        actual = manifest["models"].get(role) or {}
        for field, value in expected_roles[role].items():
            compare(f"{role} {field}", actual.get(field), value)
        # The endpoint the run actually used (recorded by the live-run gate) must be the one
        # the providers file defines; compared exactly, as recorded (no normalization).
        endpoint = recorded_endpoints.get(role) if isinstance(recorded_endpoints, dict) else None
        if not isinstance(endpoint, dict):
            problems.append(f"{role} endpoint: not recorded in the run")
            continue
        for field, value in {
            **expected_roles[role],
            "base_url": providers.providers[profile.provider].base_url,
        }.items():
            compare(f"{role} endpoint {field}", endpoint.get(field), value)

    # Condition/profile mapping as executed: rewrites ("generator") use the rewriter profile,
    # target calls the target profile; conditions without a transform make no rewrite call.
    transforms = {c["id"]: c["transform"] is not None for c in manifest["conditions"]}
    seen: set[str] = set()
    for record in records:
        for execution in record.executions:
            role = "rewriter" if execution.role == "generator" else "target"
            if execution.role == "generator" and not transforms.get(record.condition, False):
                seen.add(f"{record.condition} made a rewrite call")
            want = expected_roles.get(role)
            got = {
                "profile": execution.profile,
                "provider": execution.provider,
                "provider_type": execution.provider_type,
                "model": execution.requested_model,
            }
            if want is not None and got != want:
                seen.add(f"{record.condition} {execution.role} call used {got}, expected {want}")
    problems += sorted(seen)
    return problems


def analyze(
    run_dir: str | Path,
    dataset: Dataset,
    key: dict[str, Any],
    ratings: list[Rating],
    experiment: ExperimentConfig,
    *,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    run_path = Path(run_dir)
    problems: list[str] = []
    verification = verify_run(run_path, dataset)
    if not verification.valid or not verification.complete:
        raise ConfigurationError(
            "Only a verified, complete run can be analysed: "
            + "; ".join(verification.problems[:3] or [f"status {verification.status}"])
        )
    run_doc = json.loads((run_path / "run.json").read_bytes())
    manifest = json.loads((run_path / "manifest.json").read_bytes())
    synthetic = run_doc["measurement"] != "model_outputs"
    if synthetic and not allow_synthetic:
        raise ConfigurationError(
            "This run used fake providers: its outputs are fixtures, not model measurements. "
            "Use --allow-synthetic only to exercise the analysis pipeline."
        )
    if (key.get("run_id"), key.get("manifest_sha256")) != (
        run_doc["run_id"],
        run_doc["manifest_sha256"],
    ):
        raise ConfigurationError("The blinding key belongs to a different run.")
    if key.get("dataset_sha256") != dataset.sha256:
        raise ConfigurationError("The blinding key was made with a different dataset.")

    records = {(r.task_id, r.condition): r for r in _records(run_path)}
    mismatches = _identity_mismatches(manifest, run_doc, list(records.values()), experiment)
    if mismatches:
        raise ConfigurationError(
            "The run does not match the experiment config, so it cannot be analysed under "
            "this experiment's labels: " + "; ".join(mismatches)
        )

    task_ids = [t["id"] for t in manifest["selection"]["tasks"]]
    conditions = [c["id"] for c in manifest["conditions"]]

    by_item: dict[str, list[Rating]] = {}
    for rating in ratings:
        if rating.item_id not in key["items"]:
            problems.append(f"rating for unknown item {rating.item_id}")
            continue
        by_item.setdefault(rating.item_id, []).append(rating)

    scores: dict[tuple[str, str], float] = {}
    rated: dict[tuple[str, str], dict[str, Any]] = {}
    unresolved: list[dict[str, str]] = []
    for item_id, mapping in key["items"].items():
        pair = (mapping["task_id"], mapping["condition"])
        item_ratings = by_item.get(item_id, [])
        if not item_ratings:
            unresolved.append({"item_id": item_id, "reason": "not rated"})
            continue
        final, reason = _resolve(item_ratings)
        if final is None:
            unresolved.append({"item_id": item_id, "reason": str(reason)})
            continue
        rated[pair] = final
        scores[pair] = final["task_success"]

    excluded: dict[str, list[str]] = {}
    failures: dict[str, Counter[str]] = {c: Counter() for c in conditions}
    for entry in key["unrated"]:
        pair = (entry["task_id"], entry["condition"])
        failures[entry["condition"]][entry["category"]] += 1
        if entry["category"] == "condition_failure":
            scores[pair] = 0.0
        else:
            excluded.setdefault(entry["task_id"], []).append(
                f"{entry['condition']}: {entry['reason']}"
            )
    # Cross-check the key against the records: every pair accounted for exactly once.
    key_pairs = Counter((m["task_id"], m["condition"]) for m in key["items"].values())
    unrated_pairs = {(u["task_id"], u["condition"]): u["category"] for u in key["unrated"]}
    for task_id in task_ids:
        for condition in conditions:
            pair = (task_id, condition)
            expected_unrated = classify_unrated(records[pair])
            if expected_unrated is None:
                if key_pairs[pair] != 1 or pair in unrated_pairs:
                    problems.append(f"{task_id}/{condition}: not exactly one rated item in key")
            elif unrated_pairs.get(pair) != expected_unrated[0] or key_pairs[pair]:
                problems.append(f"{task_id}/{condition}: key classification differs from run")

    complete_tasks = [
        t for t in task_ids if t not in excluded and all((t, c) in scores for c in conditions)
    ]
    excluded_fraction = len(excluded) / len(task_ids) if task_ids else 1.0
    if excluded_fraction > experiment.evaluation.max_excluded_task_fraction:
        problems.append(
            f"{len(excluded)} of {len(task_ids)} tasks excluded for infrastructure failures "
            f"(limit {experiment.evaluation.max_excluded_task_fraction:.0%}): the run is invalid"
        )

    status = "complete" if not problems and not unresolved else "incomplete"
    report: dict[str, Any] = {
        "analysis_version": ANALYSIS_VERSION,
        "experiment_id": experiment.experiment_id,
        "protocol_version": experiment.protocol_version,
        "experiment_config_sha256": manifest["experiment"]["config_sha256"],
        "run_id": run_doc["run_id"],
        "manifest_sha256": run_doc["manifest_sha256"],
        "dataset": {"id": dataset.id, "version": dataset.version, "sha256": dataset.sha256},
        "interpretation": INTERPRETATION,
        "synthetic": synthetic,
        "status": status,
        "problems": problems,
        "unresolved_items": unresolved,
        "tasks": len(task_ids),
        "complete_tasks": len(complete_tasks),
        "excluded_tasks": {t: reasons for t, reasons in sorted(excluded.items())},
        "failures_by_condition": {c: dict(failures[c]) for c in conditions},
    }
    if status != "complete":
        return report

    resamples = experiment.evaluation.bootstrap_resamples
    seed = experiment.evaluation.bootstrap_seed
    report["primary"] = _compare(*PRIMARY, scores, complete_tasks, resamples=resamples, seed=seed)
    report["secondary"] = _compare(
        *SECONDARY, scores, complete_tasks, resamples=resamples, seed=seed
    )
    report["exploratory"] = _compare(
        *EXPLORATORY, scores, complete_tasks, resamples=resamples, seed=seed
    )
    report["secondary_outcomes"] = _secondary_outcomes(records, rated, complete_tasks, conditions)
    return report


def _secondary_outcomes(
    records: dict[tuple[str, str], ResultRecord],
    rated: dict[tuple[str, str], dict[str, Any]],
    tasks: list[str],
    conditions: list[str],
) -> dict[str, Any]:
    def l0_pass(task: str, condition: str) -> bool:
        evaluation = records[(task, condition)].evaluation
        return bool(evaluation and evaluation.passed_all)

    paired_l0 = {}
    for a, b in (PRIMARY, SECONDARY):
        counts = Counter(
            "both"
            if l0_pass(t, a) and l0_pass(t, b)
            else "a_only"
            if l0_pass(t, a)
            else "b_only"
            if l0_pass(t, b)
            else "neither"
            for t in tasks
        )
        paired_l0[f"{a} vs {b}"] = {k: counts[k] for k in ("both", "a_only", "b_only", "neither")}
    per_condition = {}
    for condition in conditions:
        items = [rated[(t, condition)] for t in tasks if (t, condition) in rated]
        target_latencies = []
        tokens: Counter[str] = Counter()
        for t in tasks:
            for execution in records[(t, condition)].executions:
                if execution.role == "target" and not execution.cache_hit:
                    target_latencies.append(execution.latency_ms)
                if execution.usage.source == "provider":
                    tokens[f"{execution.role}_input"] += execution.usage.input_tokens or 0
                    tokens[f"{execution.role}_output"] += execution.usage.output_tokens or 0
        per_condition[condition] = {
            "rated_items": len(items),
            "instruction_adherence_mean": (
                round(statistics.fmean(i["instruction_adherence"] for i in items), 4)
                if items
                else None
            ),
            "factual_error": {"count": sum(i["factual_error"] for i in items), "of": len(items)},
            "unsupported_claim": {
                "count": sum(i["unsupported_claim"] for i in items),
                "of": len(items),
            },
            "l0_all_checks_passed": {
                "count": sum(l0_pass(t, condition) for t in tasks),
                "of": len(tasks),
            },
            "provider_reported_tokens": dict(sorted(tokens.items())),
            "target_latency_ms_median": (
                statistics.median(target_latencies) if target_latencies else None
            ),
        }
    return {"paired_l0_all_checks_passed": paired_l0, "per_condition": per_condition}


def render_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Pilot analysis — experiment `{report['experiment_id']}`",
        "",
        f"**Interpretation: {report['interpretation']}.** A ~30-task pilot cannot establish "
        "that any condition is better in general. Intervals are descriptive (bootstrap over "
        "tasks), not hypothesis tests.",
        "",
    ]
    if report["synthetic"]:
        lines += [
            "**SYNTHETIC: fake-provider run.** Outputs and ratings exercise the pipeline only; "
            "nothing here is a measurement.",
            "",
        ]
    lines += [
        f"- Status: `{report['status']}`; run `{report['run_id']}`; dataset "
        f"{report['dataset']['id']} {report['dataset']['version']}",
        f"- Tasks analysed: {report['complete_tasks']} / {report['tasks']} "
        f"(excluded for infrastructure failures: {len(report['excluded_tasks'])})",
    ]
    for problem in report["problems"]:
        lines.append(f"- Problem: {problem}")
    if report["unresolved_items"]:
        lines.append(f"- Unresolved items: {len(report['unresolved_items'])}")
    for label in ("primary", "secondary", "exploratory"):
        comparison = report.get(label)
        if not comparison:
            continue
        lines += [
            "",
            f"## {label.capitalize()}: {comparison['a']} vs {comparison['b']} "
            f"(task success 0–3, {comparison['tasks']} paired tasks)",
            "",
            f"- {comparison['a']} higher / tied / lower: {comparison['a_higher']} / "
            f"{comparison['tied']} / {comparison['b_higher']}",
            f"- Means: {comparison['mean_a']} vs {comparison['mean_b']}; mean difference "
            f"{comparison['mean_difference']} (bootstrap 95% interval "
            f"{comparison['bootstrap_95_interval_mean_difference']}); median difference "
            f"{comparison['median_difference']}",
        ]
    return "\n".join(lines) + "\n"
