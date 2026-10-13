"""Frozen record/summary format v1 (runs written before the Step 6 acceptance fixes).

Kept unchanged so that existing v1 artefacts (``summary.json`` without ``summary_version``)
remain verifiable: ``verify`` recomputes their aggregates with exactly this code. Do not
edit; new behaviour belongs in ``records.aggregate`` (format v2).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from itertools import combinations
from typing import TYPE_CHECKING, Any

from forge.benchmark import INTERPRETATION
from forge.benchmark.dataset import Task

if TYPE_CHECKING:
    from forge.benchmark.records import ResultRecord


def _ratio(count: int, total: int) -> dict[str, int]:
    return {"count": count, "of": total}


def aggregate_v1(
    records: Iterable[ResultRecord], tasks: Sequence[Task], condition_ids: Sequence[str]
) -> dict[str, Any]:
    """Aggregate metrics computed solely from ``records`` (one per task × condition)."""
    by_key = {(r.task_id, r.condition): r for r in records}
    task_count = len(tasks)
    result: dict[str, Any] = {"interpretation": INTERPRETATION, "conditions": {}}
    for condition in condition_ids:
        statuses: Counter[str] = Counter()
        reasons: Counter[str] = Counter()
        checks: Counter[str] = Counter()
        by_type: dict[str, Counter[str]] = {}
        by_level: dict[str, Counter[str]] = {}
        calls: Counter[str] = Counter()
        usage: Counter[str] = Counter()
        empty = all_passed = 0
        for task in tasks:
            record = by_key.get((task.id, condition))
            level = by_level.setdefault(task.spec_level, Counter())
            level["tasks"] += 1
            statuses[record.status if record else "missing"] += 1
            if record and record.reason:
                reasons[record.reason] += 1
            evaluation = record.evaluation if record and record.status == "evaluated" else None
            if evaluation is not None and len(evaluation.checks) != len(task.checks):
                raise ValueError(f"evaluation of {task.id}/{condition} does not match the task")
            for index, check in enumerate(task.checks):
                counts = by_type.setdefault(check.type, Counter())
                counts["defined"] += 1
                checks["defined"] += 1
                if evaluation is None:
                    outcome = "not_evaluated"
                else:
                    outcome = "passed" if evaluation.checks[index].passed else "failed"
                counts[outcome] += 1
                checks[outcome] += 1
            if evaluation is not None:
                empty += evaluation.empty_output
                all_passed += evaluation.passed_all
                level["all_checks_passed"] += evaluation.passed_all
            for execution in record.executions if record else ():
                calls["executions"] += 1
                calls["cache_hits" if execution.cache_hit else "fresh"] += 1
                calls["errors"] += execution.status == "error"
                if execution.cache_hit:
                    continue  # replayed usage is not new usage
                if execution.usage.source == "provider":
                    usage["provider_input_tokens"] += execution.usage.input_tokens or 0
                    usage["provider_output_tokens"] += execution.usage.output_tokens or 0
                else:
                    usage["fresh_executions_without_usage"] += 1
        result["conditions"][condition] = {
            "tasks": task_count,
            "records": {k: statuses[k] for k in ("evaluated", "failed", "not_run", "missing")},
            "failure_reasons": dict(sorted(reasons.items())),
            "empty_outputs": _ratio(empty, task_count),
            "tasks_all_checks_passed": _ratio(all_passed, task_count),
            "tasks_all_checks_passed_by_spec_level": {
                level: _ratio(c["all_checks_passed"], c["tasks"])
                for level, c in sorted(by_level.items())
            },
            "checks": {k: checks[k] for k in ("defined", "passed", "failed", "not_evaluated")},
            "checks_by_type": {
                name: {k: c[k] for k in ("defined", "passed", "failed", "not_evaluated")}
                for name, c in sorted(by_type.items())
            },
            "model_calls": {k: calls[k] for k in ("executions", "fresh", "cache_hits", "errors")},
            "usage": {
                k: usage[k]
                for k in (
                    "provider_input_tokens",
                    "provider_output_tokens",
                    "fresh_executions_without_usage",
                )
            },
        }
    result["paired_check_counts"] = _paired(by_key, tasks, condition_ids)
    return result


def _paired(
    by_key: dict[tuple[str, str], ResultRecord], tasks: Sequence[Task], condition_ids: Sequence[str]
) -> list[dict[str, Any]]:
    """Diagnostic only: per task, which condition passed more L0 checks. Tasks not evaluated
    under both conditions are excluded and counted."""
    pairs = []
    for a, b in combinations(condition_ids, 2):
        counts: Counter[str] = Counter()
        for task in tasks:
            ra, rb = by_key.get((task.id, a)), by_key.get((task.id, b))
            if not (ra and rb and ra.evaluation and rb.evaluation):
                counts["excluded"] += 1
                continue
            pa, pb = ra.evaluation.checks_passed, rb.evaluation.checks_passed
            counts["a_more" if pa > pb else "b_more" if pb > pa else "equal"] += 1
        pairs.append(
            {
                "a": a,
                "b": b,
                "tasks": len(tasks),
                "compared": len(tasks) - counts["excluded"],
                "a_more_checks_passed": counts["a_more"],
                "equal": counts["equal"],
                "b_more_checks_passed": counts["b_more"],
                "excluded_not_evaluated_in_both": counts["excluded"],
            }
        )
    return pairs
