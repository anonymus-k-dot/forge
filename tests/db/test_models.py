"""Schema constraints, relationships and persistence on a migrated PostgreSQL database."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from forge.db import repositories
from forge.db.models import Evaluation, Execution, Run, Workspace

from .conftest import database_for

pytestmark = pytest.mark.postgres

HASH = hashlib.sha256(b"manifest").hexdigest()
REQUEST_HASH = hashlib.sha256(b"request").hexdigest()


def unique_slug() -> str:
    return f"ws-{uuid.uuid4().hex[:10]}"


def make_execution(run, **overrides):
    values = dict(
        run=run,
        case_id="case-1",
        system="B0",
        role="target",
        provider="fake",
        requested_model="fake-model",
        request_hash=REQUEST_HASH,
        output_text="answer",
    )
    values.update(overrides)
    return Execution(**values)


@pytest.fixture
def run_id(migrated_database):
    with migrated_database.session() as session:
        workspace = repositories.get_or_create_workspace(session, unique_slug(), "Test")
        run = repositories.create_run(
            session,
            workspace=workspace,
            manifest={"cases": 1},
            manifest_hash=HASH,
            forge_version="1.0.0",
        )
        return run.id


class TestPersistence:
    def test_full_graph_round_trip(self, migrated_database):
        manifest = {
            "version": 1,
            "cases": ["a", "b"],
            "note": "ünïcode ✓",
            "nested": {"k": [1, 2.5, None]},
        }
        with migrated_database.session() as session:
            workspace = repositories.get_or_create_workspace(session, unique_slug(), "Pilot")
            run = repositories.create_run(
                session,
                workspace=workspace,
                manifest=manifest,
                manifest_hash=HASH,
                forge_version="1.0.0",
                budget_limits={"max_model_calls": 10},
            )
            execution = make_execution(
                run,
                input_tokens=11,
                output_tokens=4,
                usage_source="provider",
                latency_ms=120,
                reported_model="fake-model-001",
                finish_reason="stop",
                params={"temperature": 0.5},
            )
            session.add(execution)
            session.flush()
            session.add(
                Evaluation(
                    execution=execution,
                    evaluator="l0",
                    evaluator_version="1",
                    results={"checks": {"json": True}},
                    passed=True,
                )
            )
            run_id = run.id

        with migrated_database.session() as session:
            loaded = repositories.get_run(session, run_id)
            assert loaded.manifest == manifest
            assert loaded.budget_limits == {"max_model_calls": 10}
            assert loaded.status == "pending"
            assert loaded.created_at.tzinfo is not None
            (execution,) = loaded.executions
            assert (execution.input_tokens, execution.output_tokens, execution.usage_source) == (
                11,
                4,
                "provider",
            )
            assert execution.params == {"temperature": 0.5} and execution.cache_hit is False
            assert execution.sample_index == 0
            (evaluation,) = execution.evaluations
            assert evaluation.passed is True and evaluation.results == {"checks": {"json": True}}

    def test_server_defaults_apply_to_raw_inserts(self, migrated_database, run_id):
        with migrated_database.session() as session:
            row = session.execute(
                text(
                    "INSERT INTO executions (run_id, case_id, system, role, provider, requested_model, "
                    "request_hash, output_text) VALUES (:r, 'c', 's', 'target', 'p', 'm', :h, '') "
                    "RETURNING id, sample_index, usage_source, cache_hit, params, created_at"
                ),
                {"r": run_id, "h": REQUEST_HASH},
            ).one()
            assert isinstance(row.id, uuid.UUID)
            assert (row.sample_index, row.usage_source, row.cache_hit, row.params) == (
                0,
                "unknown",
                False,
                {},
            )
            assert row.created_at is not None

    def test_get_or_create_workspace_is_idempotent(self, migrated_database):
        slug = unique_slug()
        with migrated_database.session() as session:
            first = repositories.get_or_create_workspace(session, slug, "One").id
        with migrated_database.session() as session:
            second = repositories.get_or_create_workspace(session, slug, "Two")
            assert second.id == first and second.name == "One"

    def test_data_survives_engine_restart(self, migrated_database, run_id):
        fresh = database_for(migrated_database.settings.url)  # new engine and pool
        try:
            with fresh.session() as session:
                assert repositories.get_run(session, run_id) is not None
        finally:
            fresh.dispose()


class TestUniqueness:
    def test_workspace_slug_unique(self, migrated_database):
        slug = unique_slug()
        with migrated_database.session() as session:
            session.add(Workspace(slug=slug, name="a"))
        with pytest.raises(IntegrityError, match="uq_workspaces_slug"):
            with migrated_database.session() as session:
                session.add(Workspace(slug=slug, name="b"))

    def test_execution_slot_unique_but_samples_distinct(self, migrated_database, run_id):
        with migrated_database.session() as session:
            run = session.get(Run, run_id)
            session.add_all([make_execution(run), make_execution(run, sample_index=1)])
        with pytest.raises(
            IntegrityError, match="uq_executions_run_id_case_id_system_role_sample_index"
        ):
            with migrated_database.session() as session:
                session.add(make_execution(session.get(Run, run_id)))

    def test_evaluation_unique_per_evaluator_version(self, migrated_database, run_id):
        with migrated_database.session() as session:
            execution = make_execution(session.get(Run, run_id), case_id="eval-case")
            session.add(execution)
            session.flush()
            session.add(
                Evaluation(execution=execution, evaluator="l0", evaluator_version="1", results={})
            )
            session.add(
                Evaluation(execution=execution, evaluator="l0", evaluator_version="2", results={})
            )
            execution_id = execution.id
        with pytest.raises(
            IntegrityError, match="uq_evaluations_execution_id_evaluator_evaluator_version"
        ):
            with migrated_database.session() as session:
                session.add(
                    Evaluation(
                        execution_id=execution_id, evaluator="l0", evaluator_version="1", results={}
                    )
                )


class TestForeignKeys:
    def test_run_requires_existing_workspace(self, migrated_database):
        with pytest.raises(IntegrityError, match="fk_runs_workspace_id_workspaces"):
            with migrated_database.session() as session:
                session.add(
                    Run(
                        workspace_id=uuid.uuid4(),
                        manifest={},
                        manifest_hash=HASH,
                        forge_version="1",
                    )
                )

    def test_history_is_not_cascade_deleted(self, migrated_database, run_id):
        with migrated_database.session() as session:
            run = session.get(Run, run_id)
            execution = make_execution(run, case_id="restrict")
            session.add(execution)
            session.flush()
            session.add(
                Evaluation(execution=execution, evaluator="l0", evaluator_version="1", results={})
            )
            workspace_id, execution_id = run.workspace_id, execution.id

        for model, key, constraint in [
            (Workspace, workspace_id, "fk_runs_workspace_id_workspaces"),
            (Run, run_id, "fk_executions_run_id_runs"),
            (Execution, execution_id, "fk_evaluations_execution_id_executions"),
        ]:
            with pytest.raises(IntegrityError, match=constraint):
                with migrated_database.session() as session:
                    session.delete(session.get(model, key))

        with migrated_database.session() as session:  # everything is still there
            assert (
                len(
                    session.execute(
                        select(Evaluation).where(Evaluation.execution_id == execution_id)
                    ).all()
                )
                == 1
            )


CHECK_CASES = [
    ("runs", "status", {"status": "done"}, "ck_runs_status_valid"),
    ("runs", "hash", {"manifest_hash": "abc"}, "ck_runs_manifest_hash_sha256"),
    (
        "runs",
        "finished",
        {"finished_at": datetime.now(timezone.utc)},
        "ck_runs_finished_after_started",
    ),
    (
        "runs",
        "order",
        {
            "started_at": datetime.now(timezone.utc),
            "finished_at": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        "ck_runs_finished_after_started",
    ),
    ("executions", "role", {"role": "oracle"}, "ck_executions_role_valid"),
    ("executions", "usage", {"usage_source": "guessed"}, "ck_executions_usage_source_valid"),
    (
        "executions",
        "unknown-usage",
        {"input_tokens": 5},
        "ck_executions_unknown_usage_has_no_counts",
    ),
    (
        "executions",
        "negative-tokens",
        {"usage_source": "provider", "output_tokens": -1},
        "ck_executions_tokens_non_negative",
    ),
    ("executions", "latency", {"latency_ms": -5}, "ck_executions_latency_non_negative"),
    ("executions", "sample", {"sample_index": -1}, "ck_executions_sample_index_non_negative"),
    (
        "executions",
        "error-category",
        {"output_text": None, "error_category": "kaboom"},
        "ck_executions_error_category_valid",
    ),
    ("executions", "nothing", {"output_text": None}, "ck_executions_has_output_or_error"),
    ("executions", "request-hash", {"request_hash": "XYZ"}, "ck_executions_request_hash_sha256"),
]


class TestCheckConstraints:
    @pytest.mark.parametrize(
        ("table", "label", "values", "constraint"),
        CHECK_CASES,
        ids=[f"{c[0]}-{c[1]}" for c in CHECK_CASES],
    )
    def test_invalid_rows_rejected(
        self, migrated_database, run_id, table, label, values, constraint
    ):
        with pytest.raises(IntegrityError, match=constraint):
            with migrated_database.session() as session:
                if table == "runs":
                    run = session.get(Run, run_id)
                    session.add(
                        Run(
                            workspace_id=run.workspace_id,
                            manifest={},
                            forge_version="1",
                            **{"manifest_hash": HASH, **values},
                        )
                    )
                else:
                    session.add(
                        make_execution(session.get(Run, run_id), case_id=f"ck-{label}", **values)
                    )

    def test_error_execution_without_output_is_valid(self, migrated_database, run_id):
        with migrated_database.session() as session:
            session.add(
                make_execution(
                    session.get(Run, run_id),
                    case_id="failed-call",
                    output_text=None,
                    error_category="rate_limit",
                )
            )

    @pytest.mark.parametrize("slug", ["Upper", "-leading", "has space", "x" * 64, ""])
    def test_workspace_slug_format(self, migrated_database, slug):
        with pytest.raises(IntegrityError, match="ck_workspaces_slug_format"):
            with migrated_database.session() as session:
                session.add(Workspace(slug=slug, name="x"))
