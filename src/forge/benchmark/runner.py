"""Executes a pilot run through ``ProviderRouter`` and persists it to files and (optionally)
PostgreSQL.

Order of work: validate everything (dataset selection, profiles, real-provider guard, budget
plan) → create the database run (``pending``) → create the run directory with
``manifest.json`` and ``run.json`` (``running``) → mark the database run ``running`` →
for each task (by ID) and condition (B0, B1, F-legacy): check for cancellation, make the
calls, evaluate, write the record to the database (one transaction) and append it to
``results.jsonl`` → write ``summary.json``/``summary.md`` → write the final ``run.json`` →
set the final database status.

Statuses (run.json and ``runs.status``): ``completed`` only when every task × condition has
an ``evaluated`` or ``failed`` record and every persistence step succeeded; otherwise
``budget_exceeded``, ``cancelled`` or ``failed``. A process crash leaves ``running``, which
``verify`` reports as incomplete. If one store fails, the run stops and is marked
``failed`` in the other (best effort); ``verify`` detects any remaining disagreement.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from forge.benchmark import INTERPRETATION, PROTOCOL_ID, PROTOCOL_VERSION
from forge.benchmark.checks import evaluate
from forge.benchmark.conditions import CONDITION_IDS, Condition, get_conditions, target_request
from forge.benchmark.dataset import SPLITS, Dataset, Task
from forge.benchmark.manifest import (
    build_manifest,
    manifest_bytes,
    manifest_sha256,
    profile_description,
)
from forge.benchmark.records import (
    BudgetTokens,
    EvaluationRecord,
    ExecutionRecord,
    ResultRecord,
    UsageRecord,
    sha256_text,
    summary_document,
)
from forge.benchmark.report import render_summary
from forge.db import repositories
from forge.db.models import Evaluation, Execution
from forge.db.session import Database
from forge.errors import ConfigurationError, DatabaseUnavailableError
from forge.infrastructure.budgets import (
    BudgetExceededError,
    BudgetGuard,
    BudgetLimits,
    MemoryRunBudget,
    PostgresRunBudget,
    Reservation,
    RunNotActiveError,
    RunPlan,
    Settlement,
    check_plan,
)
from forge.infrastructure.cache import (
    DEFAULT_TTL_SECONDS,
    CachePolicy,
    CacheStore,
    PostgresCacheStore,
    canonical_json,
)
from forge.providers.base import GenerationRequest, GenerationResult, Usage
from forge.providers.errors import ProviderError
from forge.providers.router import ProviderRouter

logger = logging.getLogger(__name__)

RUN_RECORD_VERSION = 2
STOP_STATUS = {
    "budget_exceeded": "budget_exceeded",
    "cancelled": "cancelled",
    "run_not_active": "failed",
    "database_error": "failed",
    "persistence_failed": "failed",
    "internal_error": "failed",
}


def utc_timestamp(now: datetime | None = None) -> str:
    """ISO 8601 UTC with millisecond precision and a ``Z`` suffix."""
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class RunOptions:
    dataset: Dataset
    target_profile: str
    budget_limits: Mapping[str, Any]
    output_dir: Path
    rewriter_profile: str | None = None
    conditions: tuple[str, ...] = CONDITION_IDS
    splits: tuple[str, ...] = SPLITS
    task_ids: tuple[str, ...] | None = None
    confirmed: bool = False
    allow_real_providers: bool = False
    cache: bool = False
    cache_scope: str | None = None  # default: the run ID (no reuse across runs)
    cache_ttl_seconds: int = DEFAULT_TTL_SECONDS
    workspace_slug: str = "benchmarks"


@dataclass
class RunOutcome:
    run_id: str
    status: str
    directory: Path
    manifest_sha256: str
    summary: dict[str, Any]
    stop_reason: str | None
    persistence: dict[str, str]
    # False if a store could not be brought to the final status after another store
    # failed (see _finalize); details are logged as benchmark.finalization_inconsistent.
    consistent: bool = True


class _Stop(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ── stores ─────────────────────────────────────────────────────────────────


class RunFiles:
    """``<output_dir>/<run_id>/``: manifest.json, run.json, results.jsonl, summary.*"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.results_path = directory / "results.jsonl"

    def create(self, manifest: bytes) -> None:
        self.directory.mkdir(parents=True, exist_ok=False)
        self._write_atomic("manifest.json", manifest)
        self.results_path.touch(exist_ok=False)

    def append_record(self, record: ResultRecord) -> None:
        line = canonical_json(record.to_json()) + b"\n"
        with self.results_path.open("ab") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def write_summary(self, summary: dict[str, Any], markdown: str) -> None:
        self._write_atomic("summary.json", canonical_json(summary))
        self._write_atomic("summary.md", markdown.encode("utf-8"))

    def write_run(self, run: dict[str, Any]) -> None:
        self._write_atomic("run.json", canonical_json(run))

    def results_sha256(self) -> str:
        return hashlib.sha256(self.results_path.read_bytes()).hexdigest()

    def _write_atomic(self, name: str, data: bytes) -> None:
        target = self.directory / name
        temporary = self.directory / f".{name}.tmp"
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)


class RunRows:
    """The ``runs`` row and its ``executions``/``evaluations`` (existing schema)."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.run_uuid: uuid.UUID | None = None

    def create(
        self,
        *,
        workspace_slug: str,
        manifest: dict[str, Any],
        manifest_hash: str,
        forge_version: str,
        budget_limits: Mapping[str, Any],
    ) -> uuid.UUID:
        with self.database.session() as session:
            workspace = repositories.get_or_create_workspace(
                session, workspace_slug, workspace_slug
            )
            run = repositories.create_run(
                session,
                workspace=workspace,
                manifest=manifest,
                manifest_hash=manifest_hash,
                forge_version=forge_version,
                budget_limits=budget_limits,
            )
            self.run_uuid = run.id
        return run.id

    def mark_running(self) -> None:
        self._update(
            "UPDATE runs SET status = 'running', started_at = now() "
            "WHERE id = :id AND status = 'pending'"
        )

    def status(self) -> str | None:
        with self.database.session() as session:
            return session.execute(
                text("SELECT status FROM runs WHERE id = :id"), {"id": self.run_uuid}
            ).scalar_one_or_none()

    def usage(self) -> dict[str, int]:
        with self.database.session() as session:
            row = session.execute(
                text(
                    "SELECT model_calls_used, tokens_used, tokens_reserved, cache_hits "
                    "FROM runs WHERE id = :id"
                ),
                {"id": self.run_uuid},
            ).one()
        return dict(row._mapping)

    def write_record(self, record: ResultRecord, task: Task) -> None:
        if not record.executions:
            return
        with self.database.session() as session:
            target_row = None
            for execution in record.executions:
                row = Execution(
                    run_id=self.run_uuid,
                    case_id=record.task_id,
                    system=record.condition,
                    role=execution.role,
                    sample_index=0,
                    provider=execution.provider,
                    requested_model=execution.requested_model,
                    reported_model=execution.reported_model,
                    params=execution.params,
                    request_hash=execution.request_sha256,
                    output_text=execution.output_text,
                    finish_reason=execution.finish_reason,
                    # Cache replays store no token counts and usage_source 'unknown' (the
                    # column allows provider/estimated/unknown); cache_hit marks them, so
                    # summing executions never counts replayed usage as new usage.
                    input_tokens=execution.usage.input_tokens,
                    output_tokens=execution.usage.output_tokens,
                    usage_source=(
                        "unknown" if execution.usage.source == "cache" else execution.usage.source
                    ),
                    latency_ms=execution.latency_ms,
                    cache_hit=execution.cache_hit,
                    error_category=execution.error_category,
                )
                session.add(row)
                if execution.role == "target":
                    target_row = row
            if record.evaluation is not None and target_row is not None:
                session.add(
                    Evaluation(
                        execution=target_row,
                        evaluator=record.evaluation.evaluator,
                        evaluator_version=record.evaluation.evaluator_version,
                        config={"task_id": task.id, "task_sha256": task.sha256},
                        results=record.evaluation.model_dump(mode="json"),
                        passed=record.evaluation.passed_all,
                    )
                )

    def finish(self, status: str) -> None:
        # started_at is set here too if the run never reached 'running' (CHECK constraint).
        self._update(
            "UPDATE runs SET status = :status, started_at = coalesce(started_at, now()), "
            "finished_at = now() WHERE id = :id",
            status=status,
        )

    def _update(self, sql: str, **params: Any) -> None:
        with self.database.session() as session:
            session.execute(text(sql), {"id": self.run_uuid, **params})


# ── runner ─────────────────────────────────────────────────────────────────


@dataclass
class _State:
    run_id: str
    files: RunFiles
    rows: RunRows | None
    budget: BudgetGuard
    cache_store: CacheStore | None
    cache_scope: str | None
    options: RunOptions
    profiles: dict[str, dict[str, Any]]
    records: list[ResultRecord] = field(default_factory=list)
    persistence: dict[str, str] = field(default_factory=dict)
    stop_reason: str | None = None
    failure: dict[str, str] | None = None
    consistent: bool = True
    summary: dict[str, Any] = field(default_factory=dict)


class BenchmarkRunner:
    def __init__(
        self,
        router: ProviderRouter,
        database: Database | None = None,
        *,
        cache_store: CacheStore | None = None,
        should_stop: Callable[[], bool] = lambda: False,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._router = router
        self._database = database
        # Default store: PostgreSQL (with a database). Tests may inject a memory store.
        self._cache_store = cache_store
        self._should_stop = should_stop
        self._monotonic = monotonic
        self._now = now

    # ── preparation ────────────────────────────────────────────────────────

    def prepare(
        self, options: RunOptions
    ) -> tuple[tuple[Task, ...], tuple[Condition, ...], dict[str, Any]]:
        """Validate the run and build its manifest; no calls, no writes."""
        conditions = get_conditions(options.conditions)
        tasks = options.dataset.select(splits=options.splits, task_ids=options.task_ids)
        needs_rewriter = any(c.transform is not None for c in conditions)
        if needs_rewriter and not options.rewriter_profile:
            raise ConfigurationError("B1 and F-legacy need a rewriter model profile.")
        target = profile_description(self._router, options.target_profile)
        rewriter = (
            profile_description(self._router, options.rewriter_profile)
            if needs_rewriter and options.rewriter_profile
            else None
        )
        used = [p for p in (target, rewriter) if p is not None]
        real = sorted({p["provider"] for p in used if p["provider_type"] != "fake"})
        if real and not options.allow_real_providers:
            raise ConfigurationError(
                f"Provider(s) {real} would make real model calls. Real-provider benchmark runs "
                "are not authorized by default; pass --allow-real-providers only with explicit "
                "approval."
            )
        if options.cache and self._database is None and self._cache_store is None:
            raise ConfigurationError("The response cache requires --database (PostgreSQL).")
        limits = BudgetLimits.parse(dict(options.budget_limits))
        calls_per_task = sum(2 if c.transform else 1 for c in conditions)
        max_attempts = max(
            self._router.config.providers[p["provider"]].retry.max_attempts for p in used
        )
        check_plan(
            limits,
            RunPlan(cases=len(tasks), systems=1, calls_per_execution=calls_per_task),
            max_attempts=max_attempts,
            confirmed=options.confirmed,
        )
        manifest = build_manifest(
            dataset=options.dataset,
            tasks=tasks,
            splits=options.splits,
            conditions=conditions,
            target=target,
            rewriter=rewriter,
        )
        return tasks, conditions, manifest

    # ── execution ──────────────────────────────────────────────────────────

    def run(self, options: RunOptions) -> RunOutcome:
        tasks, conditions, manifest = self.prepare(options)
        digest = manifest_sha256(manifest)
        limits = BudgetLimits.parse(dict(options.budget_limits)).to_json()
        created_at = utc_timestamp(self._now())

        rows: RunRows | None = None
        if self._database is not None:
            if self._database.readiness() != "ok":
                raise ConfigurationError(
                    "The database is not ready (unavailable or not migrated to head)."
                )
            rows = RunRows(self._database)
            run_id = str(
                rows.create(
                    workspace_slug=options.workspace_slug,
                    manifest=manifest,
                    manifest_hash=digest,
                    forge_version=manifest["forge_version"],
                    budget_limits=limits,
                )
            )
        else:
            run_id = str(uuid.uuid4())

        files = RunFiles(Path(options.output_dir) / run_id)
        try:
            files.create(manifest_bytes(manifest))
        except OSError:
            if rows is not None:
                _best_effort(rows.finish, "failed")
            raise

        budget: BudgetGuard
        if rows is not None and rows.run_uuid is not None and self._database is not None:
            budget = PostgresRunBudget(self._database, rows.run_uuid)
        else:
            budget = MemoryRunBudget(BudgetLimits.parse(limits))
        state = _State(
            run_id=run_id,
            files=files,
            rows=rows,
            budget=budget,
            cache_store=self._select_cache_store(options),
            cache_scope=(options.cache_scope or run_id) if options.cache else None,
            options=options,
            profiles={
                "target": manifest["models"]["target"],
                "rewriter": manifest["models"]["rewriter"],
            },
            persistence={"files": "ok", "database": "ok" if rows else "disabled"},
        )
        run_doc = self._run_document(state, manifest, digest, created_at, status="running")
        try:
            files.write_run(run_doc)
            if rows is not None:
                rows.mark_running()
        except (OSError, SQLAlchemyError, DatabaseUnavailableError) as exc:
            store = "files" if isinstance(exc, OSError) else "database"
            state.persistence[store] = "failed"
            state.stop_reason = "persistence_failed"
            state.failure = {"reason": "persistence_failed", "error_type": type(exc).__name__}

        logger.info(
            "benchmark.started",
            extra={
                "forge": {
                    "run_id": run_id,
                    "manifest_sha256": digest,
                    "tasks": len(tasks),
                    "conditions": [c.id for c in conditions],
                }
            },
        )
        interrupted: BaseException | None = None
        for task in tasks:
            for condition in conditions:
                if state.stop_reason is None:
                    try:
                        self._check_active(state)
                    except _Stop as stop:
                        state.stop_reason = stop.reason
                if state.stop_reason is not None:
                    record = self._not_run(state, task, condition, state.stop_reason, ())
                else:
                    # Calls made for this pair, kept even if it is interrupted part-way.
                    executions: list[ExecutionRecord] = []
                    try:
                        record = self._execute(state, task, condition, executions)
                    except KeyboardInterrupt as exc:
                        interrupted = exc
                        state.stop_reason = "cancelled"
                        record = self._not_run(state, task, condition, "cancelled", executions)
                    except Exception as exc:  # noqa: BLE001 - finalize honestly, re-raise later
                        interrupted = exc
                        state.stop_reason = "internal_error"
                        state.failure = {
                            "reason": "internal_error",
                            "error_type": type(exc).__name__,
                        }
                        record = self._not_run(state, task, condition, "internal_error", executions)
                self._persist(state, task, record)
        status = self._finalize(state, tasks, conditions, manifest, digest, created_at)
        logger.info(
            "benchmark.finished",
            extra={
                "forge": {
                    "run_id": run_id,
                    "status": status,
                    "records": len(state.records),
                    "stop_reason": state.stop_reason,
                    "persistence": dict(state.persistence),
                    "consistent": state.consistent,
                }
            },
        )
        if interrupted is not None:
            raise interrupted
        return RunOutcome(
            run_id=run_id,
            status=status,
            directory=files.directory,
            manifest_sha256=digest,
            summary=state.summary,
            stop_reason=state.stop_reason,
            persistence=dict(state.persistence),
            consistent=state.consistent,
        )

    def _select_cache_store(self, options: RunOptions) -> CacheStore | None:
        if not options.cache:
            return None
        if self._cache_store is not None:
            return self._cache_store
        return PostgresCacheStore(self._database) if self._database is not None else None

    def _check_active(self, state: _State) -> None:
        if self._should_stop():
            raise _Stop("cancelled")
        if state.rows is None:
            return
        try:
            status = state.rows.status()
        except (SQLAlchemyError, DatabaseUnavailableError):
            raise _Stop("database_error") from None
        if status not in ("pending", "running"):
            raise _Stop(_inactive_reason(status))

    def _execute(
        self,
        state: _State,
        task: Task,
        condition: Condition,
        executions: list[ExecutionRecord],
    ) -> ResultRecord:
        target_prompt = task.prompt
        try:
            if condition.transform is not None:
                transform = condition.transform
                execution, result = self._call(
                    state, task, condition, "generator", transform.build(task.prompt)
                )
                executions.append(execution)
                if result is None:
                    return self._record(
                        state, task, condition, "failed", "provider_error", executions
                    )
                target_prompt = transform.postprocess(result.text)
                if not target_prompt.strip():
                    return self._record(
                        state, task, condition, "failed", "empty_transform_output", executions
                    )
            execution, result = self._call(
                state, task, condition, "target", target_request(target_prompt)
            )
            executions.append(execution)
        except _Stop as stop:
            state.stop_reason = stop.reason
            return self._not_run(state, task, condition, stop.reason, executions)
        if result is None:
            return self._record(
                state, task, condition, "failed", "provider_error", executions, target_prompt
            )
        evaluation = evaluate(task, result.text)
        return self._record(
            state,
            task,
            condition,
            "evaluated",
            None,
            executions,
            target_prompt,
            EvaluationRecord.model_validate(evaluation.to_json()),
        )

    def _call(
        self,
        state: _State,
        task: Task,
        condition: Condition,
        role: str,
        request: GenerationRequest,
    ) -> tuple[ExecutionRecord, GenerationResult | None]:
        profile_key = "rewriter" if role == "generator" else "target"
        info = state.profiles[profile_key]
        profile_name = (
            state.options.rewriter_profile if role == "generator" else state.options.target_profile
        )
        profile = self._router.profile(profile_name)
        effective = replace(request, params=request.params.merged_over(profile.params))
        identity = self._router.adapter(profile.provider).cache_identity(profile.model, effective)
        request_sha256 = hashlib.sha256(canonical_json(identity)).hexdigest()
        cache = None
        if state.cache_store is not None:
            cache = CachePolicy(
                state.cache_store,
                state.options.cache_ttl_seconds,
                {
                    "benchmark": PROTOCOL_ID,
                    "protocol_version": PROTOCOL_VERSION,
                    "cache_scope": state.cache_scope,
                    "condition": condition.id,
                    "task_id": task.id,
                    "task_sha256": task.sha256,
                    "role": role,
                    "sample_index": 0,
                },
            )
        meter = _AttemptMeter(state.budget)
        started = self._monotonic()
        base = {
            "role": role,
            "profile": profile.name,
            "provider": profile.provider,
            "provider_type": info["provider_type"],
            "requested_model": profile.model,
            "params": _params_json(effective),
            "request_sha256": request_sha256,
        }
        try:
            result = self._router.generate(request, model=profile_name, budget=meter, cache=cache)
        except ProviderError as error:
            return (
                ExecutionRecord(
                    **base,
                    reported_model=None,
                    status="error",
                    output_text=None,
                    finish_reason=None,
                    usage=UsageRecord(source="unknown"),
                    latency_ms=self._elapsed_ms(started),
                    cache_hit=False,
                    error_category=error.category.value,
                    attempts=meter.attempts,
                    budget_tokens=meter.tokens(),
                ),
                None,
            )
        except BudgetExceededError:
            raise _Stop("budget_exceeded") from None
        except RunNotActiveError as exc:
            raise _Stop(_inactive_reason(exc.status)) from None
        except (SQLAlchemyError, DatabaseUnavailableError):
            raise _Stop("database_error") from None
        reported_usage = _provider_usage(result)
        return (
            ExecutionRecord(
                **base,
                reported_model=result.reported_model,
                status="ok",
                output_text=result.text,
                output_sha256=sha256_text(result.text),
                finish_reason=result.finish_reason,
                # A cache hit is a replay: no new usage; the original response's reported
                # usage is kept separately and is never added to usage totals.
                usage=UsageRecord(source="cache") if result.cache_hit else reported_usage,
                replayed_usage=reported_usage if result.cache_hit else None,
                latency_ms=self._elapsed_ms(started),
                cache_hit=result.cache_hit,
                error_category=None,
                attempts=meter.attempts,
                budget_tokens=meter.tokens(),
            ),
            result,
        )

    def _elapsed_ms(self, started: float) -> int:
        return max(0, round((self._monotonic() - started) * 1000))

    def _record(
        self,
        state: _State,
        task: Task,
        condition: Condition,
        status: str,
        reason: str | None,
        executions: Sequence[ExecutionRecord],
        target_prompt: str | None = None,
        evaluation: EvaluationRecord | None = None,
    ) -> ResultRecord:
        transformed = condition.transform is not None and target_prompt is not None
        return ResultRecord(
            run_id=state.run_id,
            task_id=task.id,
            task_sha256=task.sha256,
            condition=condition.id,
            status=status,  # type: ignore[arg-type]
            reason=reason,  # type: ignore[arg-type]
            task_prompt_sha256=sha256_text(task.prompt),
            target_prompt=target_prompt if transformed else None,
            target_prompt_sha256=sha256_text(target_prompt)
            if transformed and target_prompt
            else None,
            executions=tuple(executions),
            evaluation=evaluation,
        )

    def _not_run(
        self,
        state: _State,
        task: Task,
        condition: Condition,
        reason: str,
        executions: Sequence[ExecutionRecord],
    ) -> ResultRecord:
        return self._record(state, task, condition, "not_run", reason, executions)

    # ── persistence ────────────────────────────────────────────────────────

    def _persist(self, state: _State, task: Task, record: ResultRecord) -> None:
        if state.persistence["database"] == "ok" and state.rows is not None:
            try:
                state.rows.write_record(record, task)
            except (SQLAlchemyError, DatabaseUnavailableError) as exc:
                state.persistence["database"] = "failed"
                self._persistence_failed(state, exc)
                # The record's calls happened, but it is not stored in the database:
                # keep it visible in the files as not evaluated.
                record = record.model_copy(
                    update={"status": "not_run", "reason": "persistence_failed", "evaluation": None}
                )
        state.records.append(record)
        if state.persistence["files"] == "ok":
            try:
                state.files.append_record(record)
            except OSError as exc:
                state.persistence["files"] = "failed"
                self._persistence_failed(state, exc)
        logger.info(
            "benchmark.record",
            extra={
                "forge": {
                    "run_id": state.run_id,
                    "task_id": record.task_id,
                    "condition": record.condition,
                    "status": record.status,
                    "reason": record.reason,
                }
            },
        )

    def _persistence_failed(self, state: _State, exc: BaseException) -> None:
        if state.stop_reason in (None, "budget_exceeded", "cancelled"):
            state.stop_reason = "persistence_failed"
        state.failure = {"reason": "persistence_failed", "error_type": type(exc).__name__}

    def _finalize(
        self,
        state: _State,
        tasks: Sequence[Task],
        conditions: Sequence[Condition],
        manifest: dict[str, Any],
        digest: str,
        created_at: str,
    ) -> str:
        """Bring both stores to one terminal status. No step writes ``completed`` before every
        earlier step succeeded, and the file commit (``run.json``) comes last:

        1. ``run.json`` → ``finalizing`` (records final, run explicitly not complete)
        2. database run → terminal status (a failure makes the run ``failed``)
        3. ``summary.json``/``summary.md`` with that same status
        4. ``run.json`` → terminal status (the commit point)

        If a file step fails after the database recorded a different status, the database
        is corrected to ``failed``; if a later failure leaves the summary stating a different
        status, it is rewritten. These corrections are best effort: there is no atomicity
        across filesystem and database. When a correction fails the run is reported
        ``consistent=False`` and ``run.json`` never says ``completed``.
        """
        condition_ids = [c.id for c in conditions]
        expected = len(tasks) * len(conditions)
        all_attempted = len(state.records) == expected and all(
            r.status in ("evaluated", "failed") for r in state.records
        )
        if state.stop_reason is None and all_attempted:
            status = "completed"
        else:
            status = STOP_STATUS.get(state.stop_reason or "internal_error", "failed")
        if "failed" in state.persistence.values():
            status = "failed"

        def files_step(write: Callable[[], None]) -> bool:
            if state.persistence["files"] != "ok":
                return False
            try:
                write()
                return True
            except OSError as exc:
                state.persistence["files"] = "failed"
                self._persistence_failed(state, exc)
                return False

        usage = self._budget_usage(state)

        def run_document(current: str) -> dict[str, Any]:
            return self._run_document(
                state, manifest, digest, created_at, status=current, final=True, usage=usage
            )

        # 1. Explicitly not complete until the commit point.
        if not files_step(lambda: state.files.write_run(run_document("finalizing"))):
            status = "failed"
        # 2. Database terminal status.
        database_status: str | None = None
        if state.rows is not None:
            try:
                state.rows.finish(status)
                database_status = status
            except (SQLAlchemyError, DatabaseUnavailableError) as exc:
                state.persistence["database"] = "failed"
                self._persistence_failed(state, exc)
                status = "failed"
        # 3. Summary with the same status.
        summary_status = status
        state.summary = summary_document(
            state.records, tasks, condition_ids, status=status, budget_usage=usage
        )
        summary_written = files_step(
            lambda: state.files.write_summary(
                state.summary,
                render_summary(manifest, digest, state.run_id, state.summary),
            )
        )
        if not summary_written:
            status = "failed"
        # 4. Commit point.
        committed = files_step(lambda: state.files.write_run(run_document(status)))
        if not committed:
            status = "failed"
        # Corrections after a late failure.
        if database_status is not None and database_status != status:
            try:
                state.rows.finish(status)  # type: ignore[union-attr]
            except (SQLAlchemyError, DatabaseUnavailableError) as exc:
                state.persistence["database"] = "failed"
                self._persistence_failed(state, exc)
                state.consistent = False
        if summary_written and summary_status != status:
            state.summary = summary_document(
                state.records, tasks, condition_ids, status=status, budget_usage=usage
            )
            try:  # the files store reported a failure, so this may fail too
                state.files.write_summary(
                    state.summary,
                    render_summary(manifest, digest, state.run_id, state.summary),
                )
            except OSError:
                state.consistent = False
        if not state.consistent:
            logger.warning(
                "benchmark.finalization_inconsistent",
                extra={
                    "forge": {
                        "run_id": state.run_id,
                        "status": status,
                        "database_status": database_status,
                        "persistence": dict(state.persistence),
                    }
                },
            )
        return status

    def _budget_usage(self, state: _State) -> dict[str, int] | None:
        budget = state.budget
        if isinstance(budget, MemoryRunBudget):
            return {
                "model_calls_used": budget.model_calls_used,
                "tokens_used": budget.tokens_used,
                "tokens_reserved": budget.tokens_reserved,
                "cache_hits": budget.cache_hits,
            }
        if state.rows is not None:
            try:
                return state.rows.usage()
            except (SQLAlchemyError, DatabaseUnavailableError):
                return None
        return None

    def _run_document(
        self,
        state: _State,
        manifest: dict[str, Any],
        digest: str,
        created_at: str,
        *,
        status: str,
        final: bool = False,
        usage: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        provider_types = {
            p["provider_type"] for p in (state.profiles["target"], state.profiles["rewriter"]) if p
        }
        expected = len(manifest["selection"]["tasks"]) * len(manifest["conditions"])
        document: dict[str, Any] = {
            "run_record_version": RUN_RECORD_VERSION,
            "run_id": state.run_id,
            "status": status,
            "interpretation": INTERPRETATION,
            # Fake providers produce synthetic text: such runs validate the harness only.
            "measurement": "offline_fixture" if "fake" in provider_types else "model_outputs",
            "manifest_sha256": digest,
            "protocol": manifest["protocol"],
            "dataset": {
                "id": manifest["dataset"]["id"],
                "version": manifest["dataset"]["version"],
                "sha256": manifest["dataset"]["sha256"],
            },
            "conditions": [c["id"] for c in manifest["conditions"]],
            "created_at": created_at,
            "finished_at": utc_timestamp(self._now()) if final else None,
            "budget_limits": BudgetLimits.parse(dict(state.options.budget_limits)).to_json(),
            # Budget accounting: provider-reported tokens where both counts were reported,
            # otherwise the pre-call estimate (see target architecture §5.2).
            "budget_usage": usage,
            "budget_usage_tokens_basis": "provider-reported where available, else estimated",
            "cache": {
                "enabled": state.cache_store is not None,
                "scope": state.cache_scope,
                "ttl_seconds": state.options.cache_ttl_seconds if state.cache_store else None,
            },
            "persistence": dict(state.persistence),
            "expected_records": expected,
            "records_written": len(state.records) if final else 0,
            "results_sha256": None,
            "stop_reason": state.stop_reason,
            "failure": state.failure,
        }
        if final and state.persistence["files"] == "ok":
            document["results_sha256"] = state.files.results_sha256()
        return document


class _AttemptMeter:
    """Wraps the run's budget guard for one execution. Every reservation the router makes is
    one provider attempt about to be dispatched (retries included); refusals before dispatch
    (unsupported capability, no concurrency slot, budget refused) never reserve. Settlements
    record whether each attempt was charged provider-reported or estimated tokens."""

    def __init__(self, guard: BudgetGuard) -> None:
        self._guard = guard
        self.attempts = 0
        self.provider_tokens = 0
        self.estimated_tokens = 0

    def reserve(self, request: GenerationRequest) -> Reservation:
        reservation = self._guard.reserve(request)
        self.attempts += 1
        return reservation

    def settle(self, reservation: Reservation, usage: Usage | None) -> Settlement:
        settlement = self._guard.settle(reservation, usage)
        if settlement.source == "provider":
            self.provider_tokens += settlement.tokens_charged
        else:
            self.estimated_tokens += settlement.tokens_charged
        return settlement

    def record_cache_hit(self) -> None:
        self._guard.record_cache_hit()

    def tokens(self) -> BudgetTokens:
        return BudgetTokens(provider=self.provider_tokens, estimated=self.estimated_tokens)


def _provider_usage(result: GenerationResult) -> UsageRecord:
    usage = result.usage
    if usage is None or (usage.input_tokens is None and usage.output_tokens is None):
        return UsageRecord(source="unknown")
    return UsageRecord(
        input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, source="provider"
    )


def _inactive_reason(status: str | None) -> str:
    if status == "cancelled":
        return "cancelled"
    if status == "budget_exceeded":
        return "budget_exceeded"
    return "run_not_active"


def _params_json(request: GenerationRequest) -> dict[str, Any]:
    params = request.params
    return {
        "temperature": params.temperature,
        "top_p": params.top_p,
        "max_output_tokens": params.max_output_tokens,
        "seed": params.seed,
    }


def _best_effort(function: Callable[..., Any], *args: Any) -> None:
    try:
        function(*args)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "benchmark.cleanup_failed", extra={"forge": {"error_type": type(exc).__name__}}
        )
