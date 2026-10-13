"""Per-record result schema (``results.jsonl``) and aggregate metrics (format v2).

One ``ResultRecord`` exists for every (task, condition) pair of a finished run, whatever
happened to it:

    evaluated  the target produced output and the L0 checks ran (an empty output is still
               "evaluated": every check fails with ``empty_output``)
    failed     a model call failed or the transform produced an empty prompt; no checks ran
    not_run    the run stopped first (budget exhausted, cancelled, run inactive, database or
               persistence failure); calls already made for the pair are still listed

Accounting terms (kept distinct throughout):

    condition result   one record per task × condition (the logical evaluation unit)
    execution          one ``router.generate`` call recorded in a record (a rewrite or a target
                       call); it may be served from the cache, make several attempts, or be
                       refused before anything is sent
    provider attempt   one request handed to the provider adapter after the run budget
                       reserved a unit for it (retries are separate attempts; cache hits and
                       refusals before dispatch are 0). Attempts are not billing records.
    tokens             ``usage`` is what the provider reported for this execution's final
                       attempt (``source: provider``), nothing (``unknown``), or ``cache`` for
                       a replay (the original response's usage is kept in ``replayed_usage``
                       and never counted as new usage). ``budget_tokens`` is what the run
                       budget charged per attempt: provider-reported or locally estimated.

Aggregates are computed only from these records. Every count has an explicit denominator:
the number of selected tasks per condition (records that never ran or failed count against
it). Tasks marked ``limited_reason`` are excluded — and reported — from "all checks passed"
metrics and paired comparisons. Format v1 records (no attempt or budget data) parse with
those fields unset; their accounting is reported as unavailable.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from itertools import combinations
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from forge.benchmark import INTERPRETATION
from forge.benchmark.dataset import Task

RECORD_VERSION: Literal[2] = 2
SUMMARY_VERSION = 2
SHA256 = r"^[0-9a-f]{64}$"

RecordStatus = Literal["evaluated", "failed", "not_run"]
Reason = Literal[
    "provider_error",
    "empty_transform_output",
    "budget_exceeded",
    "cancelled",
    "run_not_active",
    "database_error",
    "persistence_failed",
    "internal_error",
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UsageRecord(_Strict):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    # "cache": replayed from the response cache — no new usage (see replayed_usage).
    source: Literal["provider", "unknown", "cache"]


class BudgetTokens(_Strict):
    """Tokens the run budget charged for this execution's attempts, by basis."""

    provider: int = Field(ge=0)  # attempts whose usage the provider reported in full
    estimated: int = Field(ge=0)  # attempts charged the local estimate


class CheckRecord(_Strict):
    index: int = Field(ge=0)
    type: str
    requirement: str
    passed: bool
    observed: Any = None
    detail: str | None = None


class EvaluationRecord(_Strict):
    evaluator: str
    evaluator_version: str
    empty_output: bool
    checks: tuple[CheckRecord, ...]
    checks_passed: int = Field(ge=0)
    checks_total: int = Field(ge=1)
    passed_all: bool


class ExecutionRecord(_Strict):
    role: Literal["generator", "target"]
    profile: str
    provider: str
    provider_type: str
    requested_model: str
    reported_model: str | None
    params: dict[str, Any]
    request_sha256: str = Field(pattern=SHA256)
    status: Literal["ok", "error"]
    output_text: str | None
    output_sha256: str | None = Field(default=None, pattern=SHA256)
    finish_reason: str | None
    usage: UsageRecord
    latency_ms: int = Field(ge=0)
    cache_hit: bool
    error_category: str | None
    # Format v2 (None in v1 records: not recorded).
    attempts: int | None = Field(default=None, ge=0)
    replayed_usage: UsageRecord | None = None
    budget_tokens: BudgetTokens | None = None


class ResultRecord(_Strict):
    record_version: Literal[1, 2] = RECORD_VERSION
    run_id: str
    task_id: str
    task_sha256: str = Field(pattern=SHA256)
    condition: str
    status: RecordStatus
    reason: Reason | None
    task_prompt_sha256: str = Field(pattern=SHA256)
    # The prompt given to the target: None for B0 (it is the task prompt itself, by hash).
    target_prompt: str | None
    target_prompt_sha256: str | None = Field(default=None, pattern=SHA256)
    executions: tuple[ExecutionRecord, ...]
    evaluation: EvaluationRecord | None

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _ratio(count: int, total: int) -> dict[str, int]:
    return {"count": count, "of": total}


def _sum_or_none(values: list[int | None]) -> int | None:
    """Exact total, or None ("unavailable") if any value was not recorded."""
    return None if any(v is None for v in values) else sum(v for v in values if v is not None)


def aggregate(
    records: Iterable[ResultRecord], tasks: Sequence[Task], condition_ids: Sequence[str]
) -> dict[str, Any]:
    """Aggregate metrics computed solely from ``records`` (one per task × condition)."""
    by_key = {(r.task_id, r.condition): r for r in records}
    task_count = len(tasks)
    limited = {t.id: t.limited_reason for t in tasks if t.limited_reason}
    result: dict[str, Any] = {
        "interpretation": INTERPRETATION,
        "limited_tasks": dict(sorted(limited.items())),
        "conditions": {},
    }
    for condition in condition_ids:
        statuses: Counter[str] = Counter()
        reasons: Counter[str] = Counter()
        checks: Counter[str] = Counter()
        by_type: dict[str, Counter[str]] = {}
        by_level: dict[str, Counter[str]] = {}
        tokens: Counter[str] = Counter()
        attempts: list[int | None] = []
        budget_provider: list[int | None] = []
        budget_estimated: list[int | None] = []
        executions = cache_hits = errors = 0
        refused: list[int | None] = []
        empty = all_passed = all_passed_limited = 0
        for task in tasks:
            record = by_key.get((task.id, condition))
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
            if task.id in limited:
                all_passed_limited += bool(evaluation and evaluation.passed_all)
            else:
                level = by_level.setdefault(task.spec_level, Counter())
                level["tasks"] += 1
                if evaluation is not None:
                    all_passed += evaluation.passed_all
                    level["all_checks_passed"] += evaluation.passed_all
            if evaluation is not None:
                empty += evaluation.empty_output
            for execution in record.executions if record else ():
                executions += 1
                errors += execution.status == "error"
                attempts.append(execution.attempts)
                tokens_charged = execution.budget_tokens
                budget_provider.append(tokens_charged.provider if tokens_charged else None)
                budget_estimated.append(tokens_charged.estimated if tokens_charged else None)
                if execution.cache_hit:
                    cache_hits += 1
                    refused.append(0)
                    continue  # replayed usage is not new usage
                refused.append(None if execution.attempts is None else int(execution.attempts == 0))
                if execution.usage.source == "provider":
                    tokens["provider_reported_input"] += execution.usage.input_tokens or 0
                    tokens["provider_reported_output"] += execution.usage.output_tokens or 0
                else:
                    tokens["executions_without_provider_usage"] += 1
        countable = task_count - len(limited)
        result["conditions"][condition] = {
            "tasks": task_count,
            "records": {k: statuses[k] for k in ("evaluated", "failed", "not_run", "missing")},
            "failure_reasons": dict(sorted(reasons.items())),
            "empty_outputs": _ratio(empty, task_count),
            # Excludes limited tasks: their checks cannot separate substantive answers.
            "tasks_all_checks_passed": _ratio(all_passed, countable),
            "tasks_all_checks_passed_limited_tasks": _ratio(all_passed_limited, len(limited)),
            "tasks_all_checks_passed_by_spec_level": {
                level: _ratio(c["all_checks_passed"], c["tasks"])
                for level, c in sorted(by_level.items())
            },
            "checks": {k: checks[k] for k in ("defined", "passed", "failed", "not_evaluated")},
            "checks_by_type": {
                name: {k: c[k] for k in ("defined", "passed", "failed", "not_evaluated")}
                for name, c in sorted(by_type.items())
            },
            "accounting": {
                "condition_results": task_count - statuses["missing"],
                "executions": executions,
                "provider_attempts": _sum_or_none(attempts),
                "cache_hits": cache_hits,
                "executions_refused_before_dispatch": _sum_or_none(refused),
                "execution_errors": errors,
            },
            "tokens": {
                "provider_reported_input": tokens["provider_reported_input"],
                "provider_reported_output": tokens["provider_reported_output"],
                "fresh_executions_without_provider_usage": tokens[
                    "executions_without_provider_usage"
                ],
                "budget_charged_provider_reported": _sum_or_none(budget_provider),
                "budget_charged_estimated": _sum_or_none(budget_estimated),
            },
        }
    result["paired_check_counts"] = _paired(by_key, tasks, condition_ids, set(limited))
    return result


def _paired(
    by_key: dict[tuple[str, str], ResultRecord],
    tasks: Sequence[Task],
    condition_ids: Sequence[str],
    limited: set[str],
) -> list[dict[str, Any]]:
    """Diagnostic only: per task, which condition passed more L0 checks. Limited tasks and
    tasks not evaluated under both conditions are excluded and counted."""
    pairs = []
    for a, b in combinations(condition_ids, 2):
        counts: Counter[str] = Counter()
        for task in tasks:
            if task.id in limited:
                counts["limited"] += 1
                continue
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
                "compared": len(tasks) - counts["excluded"] - counts["limited"],
                "a_more_checks_passed": counts["a_more"],
                "equal": counts["equal"],
                "b_more_checks_passed": counts["b_more"],
                "excluded_not_evaluated_in_both": counts["excluded"],
                "excluded_limited_tasks": counts["limited"],
            }
        )
    return pairs


def summary_document(
    records: Sequence[ResultRecord],
    tasks: Sequence[Task],
    condition_ids: Sequence[str],
    *,
    status: str,
    budget_usage: Mapping[str, int] | None,
) -> dict[str, Any]:
    """``summary.json`` (format v2): the terminal status and run-level accounting plus the
    aggregates. ``verify`` rebuilds it from the records and ``run.json``."""
    aggregates = aggregate(records, tasks, condition_ids)
    recorded = _sum_or_none([e.attempts for r in records for e in r.executions])
    budget_calls = budget_usage.get("model_calls_used") if budget_usage else None
    return {
        "summary_version": SUMMARY_VERSION,
        "status": status,
        "run_accounting": {
            "condition_results_expected": len(tasks) * len(condition_ids),
            "condition_results_recorded": len(records),
            "provider_attempts_recorded": recorded,
            # The budget counts every reserved attempt, including any made by a call that was
            # interrupted before its execution could be recorded.
            "provider_attempts_budget": budget_calls,
            "provider_attempts_unrecorded": (
                None if recorded is None or budget_calls is None else budget_calls - recorded
            ),
            "budget_tokens_used": budget_usage.get("tokens_used") if budget_usage else None,
        },
        **aggregates,
    }
