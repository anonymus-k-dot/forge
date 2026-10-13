"""Integrity verification of a run directory, independent of the runner.

A run is **complete** only if all of these hold: ``run.json`` says ``completed``; the
manifest bytes hash to ``manifest_sha256`` and are canonical; ``results.jsonl`` hashes to
``results_sha256`` and holds exactly one valid record per selected task × condition, none
``not_run``; every record is internally consistent (statuses, executions, output hashes);
and the persistence report shows no failed store. With the dataset, task hashes are
compared with the manifest and every evaluation is recomputed from the stored output, so
an edited or fabricated evaluation is detected; ``summary.json`` must equal the aggregates
recomputed from the records (format v1 with the frozen v1 aggregator, format v2 including the
terminal status and run accounting), and ``summary.md`` must state the same status as
``run.json``. Format v2 also checks attempt accounting: cache hits made no attempts and
carry no new usage, and recorded attempts never exceed the attempts the budget counted
(equal for a completed run).

Optionally (``database``) the run row is cross-checked: status, manifest hash and the number
of stored executions must match the files. Without it, verification uses the files only and
cannot see a database left in a different state by a failed finalization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from forge.benchmark import INTERPRETATION
from forge.benchmark.checks import evaluate
from forge.benchmark.conditions import CONDITIONS
from forge.benchmark.dataset import Dataset
from forge.benchmark.legacy_formats import aggregate_v1
from forge.benchmark.records import (
    EvaluationRecord,
    ResultRecord,
    sha256_text,
    summary_document,
)
from forge.infrastructure.cache import canonical_json

if TYPE_CHECKING:
    from forge.db.session import Database

FAILED_REASONS = {"provider_error", "empty_transform_output"}
NOT_RUN_REASONS = {
    "budget_exceeded",
    "cancelled",
    "run_not_active",
    "database_error",
    "persistence_failed",
    "internal_error",
}


@dataclass
class VerificationReport:
    run_id: str | None = None
    status: str | None = None
    complete: bool = False
    evaluations_recomputed: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "valid": self.valid,
            "complete": self.complete,
            "evaluations_recomputed": self.evaluations_recomputed,
            "problems": self.problems,
        }


def _load_json(path: Path, report: VerificationReport) -> Any:
    try:
        return json.loads(path.read_bytes())
    except FileNotFoundError:
        report.problems.append(f"{path.name} is missing")
    except ValueError:
        report.problems.append(f"{path.name} is not valid JSON")
    return None


def verify_run(
    directory: str | Path, dataset: Dataset | None = None, database: Database | None = None
) -> VerificationReport:
    root = Path(directory)
    report = VerificationReport()
    run = _load_json(root / "run.json", report)
    if run is None:
        return report
    if not isinstance(run, dict):
        report.problems.append("run.json is not an object")
        return report
    report.run_id, report.status = run.get("run_id"), run.get("status")
    if run.get("interpretation") != INTERPRETATION:
        report.problems.append("interpretation is not INCONCLUSIVE")

    try:
        manifest_raw = (root / "manifest.json").read_bytes()
    except FileNotFoundError:
        report.problems.append("manifest.json is missing")
        return report
    if hashlib.sha256(manifest_raw).hexdigest() != run.get("manifest_sha256"):
        report.problems.append("manifest.json does not match manifest_sha256")
    try:
        manifest = json.loads(manifest_raw)
    except ValueError:
        report.problems.append("manifest.json is not valid JSON")
        return report
    if canonical_json(manifest) != manifest_raw:
        report.problems.append("manifest.json is not in canonical form")

    provider_types = {
        m["provider_type"] for m in manifest["models"].values() if isinstance(m, dict)
    }
    expected_measurement = "offline_fixture" if "fake" in provider_types else "model_outputs"
    if run.get("measurement") != expected_measurement:
        report.problems.append(
            f"measurement is {run.get('measurement')!r}, expected {expected_measurement!r}"
        )

    tasks_by_id = {t["id"]: t for t in manifest["selection"]["tasks"]}
    condition_ids = [c["id"] for c in manifest["conditions"]]
    expected = {(t, c) for t in tasks_by_id for c in condition_ids}
    if run.get("expected_records") != len(expected):
        report.problems.append("expected_records does not match the manifest")

    records = _read_records(root / "results.jsonl", run, report)
    if records is None:
        return report
    keys = [(r.task_id, r.condition) for r in records]
    if len(set(keys)) != len(keys):
        report.problems.append("results.jsonl contains duplicate task/condition records")
    unknown = set(keys) - expected
    missing = expected - set(keys)
    if unknown:
        report.problems.append(f"{len(unknown)} record(s) not in the manifest selection")
    for record in records:
        _check_record(record, run, tasks_by_id, report)
    format_v2 = run.get("run_record_version", 1) >= 2
    if format_v2:
        _check_accounting(records, run, report)

    tasks = None
    if dataset is not None:
        tasks = _check_against_dataset(records, manifest, dataset, report)
        report.evaluations_recomputed = tasks is not None
    summary = _load_json(root / "summary.json", report) if run.get("status") != "running" else None
    if isinstance(summary, dict) and tasks is not None:
        if summary.get("summary_version") == 2:
            expected_summary = summary_document(
                records,
                tasks,
                condition_ids,
                status=summary.get("status", ""),
                budget_usage=run.get("budget_usage"),
            )
        else:
            expected_summary = aggregate_v1(records, tasks, condition_ids)
        if summary != json.loads(canonical_json(expected_summary)):
            report.problems.append("summary.json does not match the recorded results")
    if isinstance(summary, dict) and summary.get("summary_version") == 2:
        if summary.get("status") != run.get("status"):
            report.problems.append("summary.json status differs from run.json")
    summary_md = root / "summary.md"
    if run.get("status") in ("completed", "failed", "cancelled", "budget_exceeded"):
        try:
            if f"- Status: `{run.get('status')}`" not in summary_md.read_text(encoding="utf-8"):
                report.problems.append("summary.md status differs from run.json")
        except FileNotFoundError:
            report.problems.append("summary.md is missing")

    persistence = run.get("persistence") or {}
    if run.get("status") == "completed":
        if missing:
            report.problems.append(f"marked completed but {len(missing)} record(s) are missing")
        if any(r.status == "not_run" for r in records):
            report.problems.append("marked completed but has not_run records")
        if "failed" in persistence.values():
            report.problems.append("marked completed but a persistence store failed")
    elif run.get("status") in ("running", "finalizing"):
        report.problems.append(f"run did not finish (status {run.get('status')}): incomplete")
    if database is not None:
        _check_database(database, run, records, report)
    report.complete = report.valid and run.get("status") == "completed" and not missing
    return report


def _check_accounting(
    records: list[ResultRecord], run: dict[str, Any], report: VerificationReport
) -> None:
    recorded = 0
    for record in records:
        where = f"{record.task_id}/{record.condition}"
        if record.record_version != 2:
            report.problems.append(f"{where}: record format does not match run.json")
            continue
        for execution in record.executions:
            if execution.attempts is None or execution.budget_tokens is None:
                report.problems.append(f"{where}: execution lacks attempt accounting")
                continue
            recorded += execution.attempts
            if execution.cache_hit and (
                execution.attempts != 0 or execution.usage.source != "cache"
            ):
                report.problems.append(f"{where}: cache hit with attempts or new usage")
            if not execution.cache_hit and execution.usage.source == "cache":
                report.problems.append(f"{where}: cache usage on a fresh execution")
    budget = (run.get("budget_usage") or {}).get("model_calls_used")
    if budget is not None:
        if recorded > budget:
            report.problems.append("more provider attempts recorded than the budget counted")
        elif run.get("status") == "completed" and recorded != budget:
            report.problems.append("completed run with unrecorded provider attempts")


def _check_database(
    database: Database, run: dict[str, Any], records: list[ResultRecord], report: VerificationReport
) -> None:
    import uuid

    from sqlalchemy import text

    try:
        run_uuid = uuid.UUID(str(run.get("run_id")))
    except ValueError:
        report.problems.append("run_id is not a database run ID")
        return
    with database.session() as session:
        row = session.execute(
            text("SELECT status, manifest_hash FROM runs WHERE id = :id"), {"id": run_uuid}
        ).one_or_none()
        stored = session.scalar(
            text("SELECT count(*) FROM executions WHERE run_id = :id"), {"id": run_uuid}
        )
    if row is None:
        report.problems.append("database has no run with this run_id")
        return
    if row.status != run.get("status"):
        report.problems.append(
            f"database status {row.status!r} differs from run.json {run.get('status')!r}"
        )
    if row.manifest_hash != run.get("manifest_sha256"):
        report.problems.append("database manifest_hash differs from run.json")
    expected = sum(len(r.executions) for r in records if r.reason != "persistence_failed")
    if stored != expected:
        report.problems.append(f"database holds {stored} executions, the files record {expected}")


def _read_records(
    path: Path, run: dict[str, Any], report: VerificationReport
) -> list[ResultRecord] | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        report.problems.append("results.jsonl is missing")
        return None
    if run.get("status") != "running" and hashlib.sha256(raw).hexdigest() != run.get(
        "results_sha256"
    ):
        report.problems.append("results.jsonl does not match results_sha256")
    records = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        try:
            records.append(ResultRecord.model_validate_json(line))
        except ValidationError:
            report.problems.append(f"results.jsonl line {number} is not a valid record")
    if run.get("status") != "running" and run.get("records_written") != len(records):
        report.problems.append("records_written does not match results.jsonl")
    return records


def _check_record(
    record: ResultRecord,
    run: dict[str, Any],
    tasks_by_id: dict[str, dict[str, Any]],
    report: VerificationReport,
) -> None:
    where = f"{record.task_id}/{record.condition}"
    if record.run_id != run.get("run_id"):
        report.problems.append(f"{where}: belongs to another run")
    task = tasks_by_id.get(record.task_id)
    if task is not None and record.task_sha256 != task["sha256"]:
        report.problems.append(f"{where}: task hash differs from the manifest")
    for execution in record.executions:
        if execution.output_text is not None and execution.output_sha256 != sha256_text(
            execution.output_text
        ):
            report.problems.append(f"{where}: output hash mismatch")
        if (execution.status == "ok") != (execution.output_text is not None):
            report.problems.append(f"{where}: execution status inconsistent with output")
        if (execution.status == "error") != (execution.error_category is not None):
            report.problems.append(f"{where}: execution error inconsistent")
    roles = [e.role for e in record.executions]
    condition = CONDITIONS.get(record.condition)
    if condition is None:
        report.problems.append(f"{where}: unknown condition")
        return
    allowed_roles = (
        (["target"],) if condition.transform is None else (["generator"], ["generator", "target"])
    )
    if record.status == "evaluated":
        if record.evaluation is None:
            report.problems.append(f"{where}: evaluated without an evaluation")
        if roles not in allowed_roles or roles[-1] != "target":
            report.problems.append(f"{where}: evaluated without a target execution")
        elif record.executions[-1].status != "ok" or any(
            e.status != "ok" for e in record.executions
        ):
            report.problems.append(f"{where}: evaluated but an execution failed")
        if condition.transform is not None and (
            record.target_prompt is None
            or record.target_prompt_sha256 != sha256_text(record.target_prompt)
        ):
            report.problems.append(f"{where}: transformed prompt missing or hash mismatch")
    else:
        if record.evaluation is not None:
            report.problems.append(f"{where}: {record.status} record carries an evaluation")
        reasons = FAILED_REASONS if record.status == "failed" else NOT_RUN_REASONS
        if record.reason not in reasons:
            report.problems.append(f"{where}: invalid reason for {record.status}")
        if record.status == "failed" and (
            not roles
            or (record.reason == "provider_error" and record.executions[-1].status != "error")
        ):
            report.problems.append(f"{where}: failed record without a failed execution")


def _check_against_dataset(
    records: list[ResultRecord],
    manifest: dict[str, Any],
    dataset: Dataset,
    report: VerificationReport,
) -> list[Any] | None:
    by_id = {t.id: t for t in dataset.tasks}
    selected = []
    for entry in manifest["selection"]["tasks"]:
        task = by_id.get(entry["id"])
        if task is None or task.sha256 != entry["sha256"]:
            report.problems.append(f"{entry['id']}: dataset task differs from the manifest")
            return None
        selected.append(task)
    if dataset.sha256 != manifest["dataset"]["sha256"]:
        report.problems.append("dataset hash differs from the manifest")
    for record in records:
        if record.status != "evaluated" or record.evaluation is None:
            continue
        task = by_id.get(record.task_id)
        target = record.executions[-1] if record.executions else None
        if task is None or target is None or target.output_text is None:
            continue
        recomputed = EvaluationRecord.model_validate(evaluate(task, target.output_text).to_json())
        if recomputed != record.evaluation:
            report.problems.append(
                f"{record.task_id}/{record.condition}: stored evaluation differs from a "
                "recomputation of the recorded output"
            )
    return selected
