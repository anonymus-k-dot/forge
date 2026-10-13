"""Human-readable ``summary.md`` (summary format v2), rendered from ``summary.json``.

Every number is shown with its denominator; the result is always labelled INCONCLUSIVE, runs
on fake providers are labelled synthetic, and the status shown is the one in the summary
document (which the runner writes with the terminal status).
"""

from __future__ import annotations

from typing import Any

from forge.benchmark import INTERPRETATION


def _r(ratio: dict[str, int]) -> str:
    return f"{ratio['count']} / {ratio['of']}"


def _n(value: int | None) -> str:
    return "unavailable" if value is None else str(value)


def render_summary(
    manifest: dict[str, Any], digest: str, run_id: str, summary: dict[str, Any]
) -> str:
    models = manifest["models"]
    provider_types = {models["target"]["provider_type"]}
    if models["rewriter"]:
        provider_types.add(models["rewriter"]["provider_type"])
    run = summary["run_accounting"]
    lines = [
        f"# FORGE pilot benchmark — run `{run_id}`",
        "",
        f"**Interpretation: {INTERPRETATION}.** These are deterministic L0 checks of format, "
        "required content and length on a ~30-task pilot. They do not measure correctness, "
        "usefulness or overall prompt quality, and a pilot this small cannot show that any "
        "condition is better than another.",
        "",
    ]
    if "fake" in provider_types:
        lines += [
            "**SYNTHETIC: fake providers were used.** Outputs are fixtures, not model "
            "responses; these numbers validate the harness only and are not measurements.",
            "",
        ]
    lines += [
        f"- Status: `{summary['status']}`",
        f"- Manifest SHA-256: `{digest}`",
        f"- Protocol: {manifest['protocol']['id']} v{manifest['protocol']['version']}; "
        f"dataset {manifest['dataset']['id']} {manifest['dataset']['version']}; "
        f"evaluator {manifest['evaluator']['name']} v{manifest['evaluator']['version']}",
        f"- Target: {models['target']['provider']} / {models['target']['model']}"
        + (
            f"; rewriter: {models['rewriter']['provider']} / {models['rewriter']['model']}"
            if models["rewriter"]
            else ""
        ),
        f"- Condition results: {run['condition_results_recorded']} / "
        f"{run['condition_results_expected']}; provider attempts: "
        f"{_n(run['provider_attempts_recorded'])} recorded, "
        f"{_n(run['provider_attempts_budget'])} counted by the run budget "
        f"({_n(run['provider_attempts_unrecorded'])} unrecorded). Attempts are requests "
        "handed to a provider, not billing records.",
    ]
    limited = summary["limited_tasks"]
    if limited:
        lines.append(
            "- Limited tasks (excluded from 'all checks passed' and paired counts): "
            + "; ".join(f"`{task}`: {reason}" for task, reason in limited.items())
        )
    lines += [
        "",
        "| Condition | Evaluated | Failed | Not run | Empty output | All checks passed "
        "| Checks passed | Checks not evaluated |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for condition, c in summary["conditions"].items():
        n = c["tasks"]
        checks = c["checks"]
        lines.append(
            f"| {condition} | {c['records']['evaluated']} / {n} | {c['records']['failed']} / {n} "
            f"| {c['records']['not_run'] + c['records']['missing']} / {n} "
            f"| {_r(c['empty_outputs'])} | {_r(c['tasks_all_checks_passed'])} "
            f"| {checks['passed']} / {checks['defined']} "
            f"| {checks['not_evaluated']} / {checks['defined']} |"
        )
    lines += [
        "",
        "| Condition | Executions | Provider attempts | Cache hits | Refused before dispatch "
        "| Errors | Provider-reported tokens (in / out) | Budget tokens (provider / estimated) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for condition, c in summary["conditions"].items():
        a, t = c["accounting"], c["tokens"]
        lines.append(
            f"| {condition} | {a['executions']} | {_n(a['provider_attempts'])} "
            f"| {a['cache_hits']} | {_n(a['executions_refused_before_dispatch'])} "
            f"| {a['execution_errors']} "
            f"| {t['provider_reported_input']} / {t['provider_reported_output']} "
            f"| {_n(t['budget_charged_provider_reported'])} / "
            f"{_n(t['budget_charged_estimated'])} |"
        )
    lines += [
        "",
        "Paired L0 check counts (diagnostic only; more checks passed is not better quality):",
        "",
        "| A | B | Compared | A more | Equal | B more | Not evaluated in both | Limited |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for pair in summary["paired_check_counts"]:
        lines.append(
            f"| {pair['a']} | {pair['b']} | {pair['compared']} / {pair['tasks']} "
            f"| {pair['a_more_checks_passed']} | {pair['equal']} | {pair['b_more_checks_passed']} "
            f"| {pair['excluded_not_evaluated_in_both']} | {pair['excluded_limited_tasks']} |"
        )
    lines += [
        "",
        "Per-task results: `results.jsonl`. Machine-readable aggregates: `summary.json`.",
        "",
    ]
    return "\n".join(lines)
