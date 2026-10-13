"""Pilot benchmark persistence on real PostgreSQL (throwaway databases only)."""

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from forge.benchmark.runner import BenchmarkRunner, RunFiles, RunRows
from forge.benchmark.verify import verify_run
from forge.db import migrate
from forge.errors import ConfigurationError
from forge.providers import errors
from forge.providers.base import Usage
from forge.providers.fake import FakeResponse
from tests.benchmark.helpers import (
    GOOD_ANSWER,
    Responder,
    make_dataset,
    make_router,
    make_task,
    options,
    read_records,
    read_run,
    text_reply,
)

pytestmark = pytest.mark.postgres


def two_tasks():
    return make_dataset(make_task("task-001"), make_task("task-002"))


def run_row(database, run_id):
    with database.session() as session:
        return session.execute(
            text(
                "SELECT status, manifest, manifest_hash, model_calls_used, cache_hits, "
                "started_at IS NOT NULL AS started, finished_at IS NOT NULL AS finished "
                "FROM runs WHERE id = :id"
            ),
            {"id": uuid.UUID(run_id)},
        ).one()


def count(database, sql, run_id):
    with database.session() as session:
        return session.scalar(text(sql), {"id": uuid.UUID(run_id)})


def start(database, tmp_path, router=None, **overrides):
    runner_kwargs = {k: overrides.pop(k) for k in ("should_stop",) if k in overrides}
    runner = BenchmarkRunner(router or make_router(), database, **runner_kwargs)
    return runner.run(options(tmp_path, dataset=overrides.pop("dataset", two_tasks()), **overrides))


def test_completed_run_is_persisted_consistently(migrated_database, tmp_path):
    outcome = start(migrated_database, tmp_path)
    assert outcome.status == "completed"
    assert outcome.persistence == {"files": "ok", "database": "ok"}
    row = run_row(migrated_database, outcome.run_id)
    assert (row.status, row.started, row.finished, row.model_calls_used) == (
        "completed",
        True,
        True,
        10,
    )
    assert row.manifest_hash == outcome.manifest_sha256
    assert row.manifest == json.loads((outcome.directory / "manifest.json").read_bytes())
    executions = "SELECT count(*) FROM executions WHERE run_id = :id"
    assert count(migrated_database, executions, outcome.run_id) == 10  # 2 x (1 + 2 + 2)
    evaluations = (
        "SELECT count(*) FROM evaluations v JOIN executions e ON e.id = v.execution_id "
        "WHERE e.run_id = :id AND v.evaluator = 'forge.l0' AND v.passed"
    )
    assert count(migrated_database, evaluations, outcome.run_id) == 6
    with migrated_database.session() as session:
        roles = session.execute(
            text(
                "SELECT system, role, count(*) FROM executions WHERE run_id = :id "
                "GROUP BY system, role ORDER BY system, role"
            ),
            {"id": uuid.UUID(outcome.run_id)},
        ).all()
        stored = session.scalar(
            text(
                "SELECT v.results FROM evaluations v JOIN executions e ON e.id = v.execution_id "
                "WHERE e.run_id = :id AND e.case_id = 'task-001' AND e.system = 'B0'"
            ),
            {"id": uuid.UUID(outcome.run_id)},
        )
    assert [tuple(r) for r in roles] == [
        ("B0", "target", 2),
        ("B1", "generator", 2),
        ("B1", "target", 2),
        ("F-legacy", "generator", 2),
        ("F-legacy", "target", 2),
    ]
    assert stored == read_records(outcome.directory)[0]["evaluation"]
    assert verify_run(outcome.directory, two_tasks()).complete


def test_postgres_budget_stops_the_run(migrated_database, tmp_path):
    attempts = {"n": 0}

    def flaky_once(_model, _request):
        attempts["n"] += 1
        return (
            errors.UpstreamServerError("503")
            if attempts["n"] == 1
            else FakeResponse((GOOD_ANSWER,))
        )

    rewriter = Responder("rw", text_reply("Rewritten"))
    target = Responder("tg", flaky_once)
    outcome = start(
        migrated_database,
        tmp_path,
        make_router(rewriter, target),
        budget_limits={"max_model_calls": 10},
    )
    assert outcome.status == "budget_exceeded"
    assert len(rewriter.calls) + len(target.calls) == 10
    row = run_row(migrated_database, outcome.run_id)
    assert (row.status, row.model_calls_used, row.finished) == ("budget_exceeded", 10, True)
    assert read_records(outcome.directory)[-1]["reason"] == "budget_exceeded"


def test_cancelling_the_run_row_stops_scheduling(migrated_database, tmp_path, monkeypatch):
    state = {"run_id": None}

    def cancel_after_first_call(_model, _request):
        with migrated_database.session() as session:
            session.execute(
                text("UPDATE runs SET status = 'cancelled' WHERE status = 'running' AND id = :id"),
                {"id": state["run_id"]},
            )
        return FakeResponse((GOOD_ANSWER,))

    original = RunRows.mark_running

    def remember(self):
        state["run_id"] = self.run_uuid
        original(self)

    target = Responder("tg", cancel_after_first_call)
    monkeypatch.setattr(RunRows, "mark_running", remember)
    outcome = start(migrated_database, tmp_path, make_router(target=target))
    assert outcome.status == "cancelled"
    assert len(target.calls) == 1
    records = read_records(outcome.directory)
    assert [r["status"] for r in records] == ["evaluated"] + ["not_run"] * 5
    assert run_row(migrated_database, outcome.run_id).status == "cancelled"


def test_postgres_cache_isolation_and_flagged_replay(migrated_database, tmp_path):
    def same_text():
        return make_router(
            Responder("rw", text_reply("IDENTICAL REWRITE")),
            Responder("tg", text_reply(GOOD_ANSWER)),
        )

    scope = f"scope-{uuid.uuid4().hex}"
    first = start(migrated_database, tmp_path / "a", same_text(), cache=True, cache_scope=scope)
    other = start(migrated_database, tmp_path / "b", same_text(), cache=True)
    replay_router = same_text()
    replay = start(migrated_database, tmp_path / "c", replay_router, cache=True, cache_scope=scope)
    hits = "SELECT count(*) FROM executions WHERE run_id = :id AND cache_hit"
    assert count(migrated_database, hits, first.run_id) == 0
    assert count(migrated_database, hits, other.run_id) == 0  # default scope = its own run
    assert count(migrated_database, hits, replay.run_id) == 10
    assert replay_router.adapter("tg").calls == [] and replay_router.adapter("rw").calls == []
    row = run_row(migrated_database, replay.run_id)
    assert (row.model_calls_used, row.cache_hits) == (0, 10)
    assert read_run(replay.directory)["cache"] == {
        "enabled": True,
        "scope": scope,
        "ttl_seconds": options(tmp_path).cache_ttl_seconds,
    }
    assert verify_run(replay.directory, two_tasks()).complete


def test_database_write_failure_marks_the_run_failed_everywhere(
    migrated_database, tmp_path, monkeypatch
):
    original = RunRows.write_record
    writes = {"n": 0}

    def flaky(self, record, task):
        writes["n"] += 1
        if writes["n"] == 2:
            raise OperationalError("INSERT", {}, Exception("connection lost"))
        original(self, record, task)

    monkeypatch.setattr(RunRows, "write_record", flaky)
    outcome = start(migrated_database, tmp_path)
    assert outcome.status == "failed"
    assert outcome.persistence == {"files": "ok", "database": "failed"}
    run_doc = read_run(outcome.directory)
    assert (run_doc["status"], run_doc["stop_reason"]) == ("failed", "persistence_failed")
    records = read_records(outcome.directory)
    assert records[1]["reason"] == "persistence_failed" and records[1]["executions"]
    assert all(r["status"] == "not_run" for r in records[1:])
    report = verify_run(outcome.directory, two_tasks())
    assert report.valid and not report.complete
    # The DB only holds what was written before the failure, and says the run failed.
    assert run_row(migrated_database, outcome.run_id).status == "failed"
    executions = "SELECT count(*) FROM executions WHERE run_id = :id"
    assert count(migrated_database, executions, outcome.run_id) == 1


def test_unmigrated_database_is_refused(empty_database, tmp_path):
    migrate.upgrade(empty_database.engine, "0001")
    with pytest.raises(ConfigurationError, match="not ready"):
        start(empty_database, tmp_path)
    assert not (tmp_path / "runs").exists()


def usage_router():
    reply = FakeResponse((GOOD_ANSWER,), usage=Usage(7, 5))
    return make_router(
        Responder("rw", lambda _m, _r: FakeResponse(("Rewritten",), usage=Usage(3, 2))),
        Responder("tg", lambda _m, _r: reply),
    )


def test_cache_hit_rows_are_not_new_provider_usage(migrated_database, tmp_path):
    scope = f"scope-{uuid.uuid4().hex}"
    fresh = start(migrated_database, tmp_path / "a", usage_router(), cache=True, cache_scope=scope)
    replay = start(migrated_database, tmp_path / "b", usage_router(), cache=True, cache_scope=scope)
    totals = (
        "SELECT count(*) FILTER (WHERE cache_hit), coalesce(sum(input_tokens), 0), "
        "coalesce(sum(output_tokens), 0), count(*) FILTER (WHERE usage_source = 'provider') "
        "FROM executions WHERE run_id = :id"
    )
    with migrated_database.session() as session:
        fresh_row = session.execute(text(totals), {"id": uuid.UUID(fresh.run_id)}).one()
        replay_row = session.execute(text(totals), {"id": uuid.UUID(replay.run_id)}).one()
        sources = session.scalars(
            text("SELECT DISTINCT usage_source FROM executions WHERE run_id = :id AND cache_hit"),
            {"id": uuid.UUID(replay.run_id)},
        ).all()
    # Fresh run: 2 tasks x (3 target calls x 7/5 + 2 rewrites x 3/2) provider-reported tokens.
    assert tuple(fresh_row) == (0, 2 * (3 * 7 + 2 * 3), 2 * (3 * 5 + 2 * 2), 10)
    # Replay: every row is a cache hit with no token counts, so sums cannot double count.
    assert tuple(replay_row) == (10, 0, 0, 0)
    assert sources == ["unknown"]
    assert replay.summary["conditions"]["B0"]["tokens"]["provider_reported_input"] == 0
    replayed = read_records(replay.directory)[0]["executions"][0]["replayed_usage"]
    assert replayed == {"input_tokens": 7, "output_tokens": 5, "source": "provider"}  # provenance
    assert verify_run(replay.directory, two_tasks(), migrated_database).complete


def test_verify_cross_checks_the_database(migrated_database, tmp_path):
    outcome = start(migrated_database, tmp_path)
    assert verify_run(outcome.directory, two_tasks(), migrated_database).complete
    with migrated_database.session() as session:
        session.execute(
            text("UPDATE runs SET status = 'failed' WHERE id = :id"),
            {"id": uuid.UUID(outcome.run_id)},
        )
    report = verify_run(outcome.directory, two_tasks(), migrated_database)
    assert not report.complete
    assert "database status 'failed' differs from run.json 'completed'" in report.problems


def test_database_finalization_failure_never_completes(migrated_database, tmp_path, monkeypatch):
    def broken_finish(self, status):
        raise OperationalError("UPDATE", {}, Exception("connection lost"))

    monkeypatch.setattr(RunRows, "finish", broken_finish)
    outcome = start(migrated_database, tmp_path)
    assert outcome.status == "failed"
    assert outcome.persistence["database"] == "failed"
    # The summary is written after the database step, so it agrees with run.json.
    assert read_run(outcome.directory)["status"] == "failed"
    summary = json.loads((outcome.directory / "summary.json").read_bytes())
    assert summary["status"] == "failed"
    assert run_row(migrated_database, outcome.run_id).status == "running"
    report = verify_run(outcome.directory, two_tasks(), migrated_database)
    assert not report.complete
    assert any("database status 'running'" in p for p in report.problems)


def test_database_and_file_double_failure(migrated_database, tmp_path, monkeypatch):
    """The database finish fails and the final run.json cannot be written either: the
    files stay 'finalizing' (explicitly incomplete) and nothing says completed."""

    def broken_finish(self, status):
        raise OperationalError("UPDATE", {}, Exception("connection lost"))

    original_write = RunFiles.write_run

    def failing_commit(self, document):
        if document["status"] not in ("running", "finalizing"):
            raise OSError("disk full")
        original_write(self, document)

    monkeypatch.setattr(RunRows, "finish", broken_finish)
    monkeypatch.setattr(RunFiles, "write_run", failing_commit)
    outcome = start(migrated_database, tmp_path)
    assert outcome.status == "failed"
    assert read_run(outcome.directory)["status"] == "finalizing"
    assert run_row(migrated_database, outcome.run_id).status == "running"
    assert not verify_run(outcome.directory, two_tasks()).complete


def test_late_file_failure_after_database_completion_is_flagged(
    migrated_database, tmp_path, monkeypatch
):
    """The database records 'completed', then the file commit fails and correcting the
    database also fails: no cross-store atomicity, so the run is reported inconsistent,
    the files never claim completion, and verify --database exposes the mismatch."""
    original_finish = RunRows.finish
    calls = {"n": 0}

    def finish_once(self, status):
        calls["n"] += 1
        if calls["n"] > 1:
            raise OperationalError("UPDATE", {}, Exception("connection lost"))
        original_finish(self, status)

    original_write = RunFiles.write_run

    def failing_commit(self, document):
        if document["status"] not in ("running", "finalizing"):
            raise OSError("disk full")
        original_write(self, document)

    monkeypatch.setattr(RunRows, "finish", finish_once)
    monkeypatch.setattr(RunFiles, "write_run", failing_commit)
    outcome = start(migrated_database, tmp_path)
    assert outcome.status == "failed" and outcome.consistent is False
    assert read_run(outcome.directory)["status"] == "finalizing"
    assert run_row(migrated_database, outcome.run_id).status == "completed"
    report = verify_run(outcome.directory, two_tasks(), migrated_database)
    assert not report.complete
    assert any("database status 'completed'" in p for p in report.problems)
