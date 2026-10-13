"""Response cache and run budgets on real PostgreSQL (throwaway databases only)."""

import hashlib
import io
import json
import socket
import threading
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from forge.db import migrate, repositories
from forge.db.config import parse_database_settings
from forge.db.session import Database
from forge.errors import DatabaseUnavailableError
from forge.infrastructure import budgets
from forge.infrastructure.budgets import (
    BudgetExceededError,
    InvalidBudgetError,
    PostgresRunBudget,
    RunNotActiveError,
)
from forge.infrastructure.cache import CachedResponse, CachePolicy, PostgresCacheStore
from forge.logging import configure_logging
from forge.providers.base import GenerationParams, GenerationRequest, Usage
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from tests.providers.helpers import RecordingSleep, make_config

from .conftest import temporary_database

pytestmark = pytest.mark.postgres

HASH = hashlib.sha256(b"manifest").hexdigest()
REQUEST = GenerationRequest.from_prompt(
    "x" * 40, system="y" * 40, params=GenerationParams(max_output_tokens=100)
)  # token estimate 120


def key(n: int) -> str:
    return hashlib.sha256(f"k{n}".encode()).hexdigest()


def new_run(database, limits=None, status="pending"):
    with database.session() as session:
        workspace = repositories.get_or_create_workspace(session, f"ws-{uuid.uuid4().hex[:8]}", "t")
        run = repositories.create_run(
            session,
            workspace=workspace,
            manifest={},
            manifest_hash=HASH,
            forge_version="1",
            budget_limits=limits or {"max_model_calls": 5},
        )
        run.status = status
        return run.id


def run_row(database, run_id):
    with database.session() as session:
        return session.execute(
            text(
                "SELECT status, model_calls_used, tokens_used, tokens_reserved, cache_hits "
                "FROM runs WHERE id = :id"
            ),
            {"id": run_id},
        ).one()


def unreachable_database():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return Database(
        parse_database_settings(
            {
                "DATABASE_URL": f"postgresql://forge:pw@127.0.0.1:{port}/forge",
                "DATABASE_CONNECT_TIMEOUT": "1",
            }
        )
    )


def router_with(adapter, **overrides):
    return ProviderRouter(make_config(**overrides), adapters={"p": adapter}, sleep=RecordingSleep())


class TestMigration0002:
    def test_upgrade_from_0001_preserves_data_and_downgrade_round_trips(self, pg_admin_url):
        with temporary_database(pg_admin_url) as url:
            engine = create_engine(url, poolclass=NullPool)
            try:
                migrate.upgrade(engine, "0001")
                with engine.begin() as c:
                    ws = c.execute(
                        text("INSERT INTO workspaces (slug, name) VALUES ('w', 'w') RETURNING id")
                    ).scalar()
                    run = c.execute(
                        text(
                            "INSERT INTO runs (workspace_id, manifest, manifest_hash, forge_version) "
                            "VALUES (:ws, '{\"a\": 1}', :h, '1') RETURNING id"
                        ),
                        {"ws": ws, "h": HASH},
                    ).scalar()
                migrate.upgrade(engine)
                with engine.connect() as c:
                    assert migrate.current_revision(c) == "0002"
                    row = c.execute(
                        text(
                            "SELECT manifest, model_calls_used, tokens_used, tokens_reserved, "
                            "cache_hits FROM runs WHERE id = :id"
                        ),
                        {"id": run},
                    ).one()
                    assert row == ({"a": 1}, 0, 0, 0, 0)
                assert "llm_cache_entries" in inspect(engine).get_table_names()
                migrate.upgrade(engine)  # repeat: no-op
                migrate.check(engine)
                migrate.downgrade(engine, "0001")
                inspector = inspect(engine)
                assert "llm_cache_entries" not in inspector.get_table_names()
                assert "model_calls_used" not in {c["name"] for c in inspector.get_columns("runs")}
                with engine.connect() as c:
                    assert c.execute(text("SELECT count(*) FROM runs")).scalar() == 1  # data kept
                migrate.upgrade(engine)
                with engine.connect() as c:
                    assert migrate.current_revision(c) == "0002"
            finally:
                engine.dispose()


class TestPostgresCacheStore:
    def test_put_get_and_first_writer_wins(self, migrated_database):
        store = PostgresCacheStore(migrated_database)
        k = key(1)
        assert store.get(k) is None
        store.put(
            k,
            CachedResponse("first", "m-001", "stop", 3, 2),
            ttl_seconds=60,
            provider_type="fake",
            model="m",
        )
        store.put(k, CachedResponse("second"), ttl_seconds=60, provider_type="fake", model="m")
        assert store.get(k) == CachedResponse("first", "m-001", "stop", 3, 2)

    def test_expired_entry_is_a_miss_and_is_replaced(self, migrated_database):
        store = PostgresCacheStore(migrated_database)
        k = key(2)
        store.put(k, CachedResponse("old"), ttl_seconds=60, provider_type="fake", model="m")
        with migrated_database.session() as session:
            session.execute(
                text(
                    "UPDATE llm_cache_entries SET created_at = now() - interval '2 hours', "
                    "expires_at = now() - interval '1 hour' WHERE cache_key = :k"
                ),
                {"k": k},
            )
        assert store.get(k) is None
        store.put(k, CachedResponse("new"), ttl_seconds=60, provider_type="fake", model="m")
        assert store.get(k).text == "new"

    def test_purge_removes_only_expired_entries(self, migrated_database):
        store = PostgresCacheStore(migrated_database)
        live, dead = key(3), key(4)
        for k in (live, dead):
            store.put(k, CachedResponse("x"), ttl_seconds=60, provider_type="fake", model="m")
        with migrated_database.session() as session:
            session.execute(
                text(
                    "UPDATE llm_cache_entries SET created_at = now() - interval '2 hours', "
                    "expires_at = now() - interval '1 hour' WHERE cache_key = :k"
                ),
                {"k": dead},
            )
        assert store.purge_expired() >= 1
        assert store.get(live) is not None
        with migrated_database.session() as session:
            assert (
                session.scalar(
                    text("SELECT count(*) FROM llm_cache_entries WHERE cache_key = :k"), {"k": dead}
                )
                == 0
            )

    def test_constraints(self, migrated_database):
        for bad in ("not-a-hash", key(5).upper()):
            with pytest.raises(IntegrityError, match="ck_llm_cache_entries_cache_key_sha256"):
                with migrated_database.session() as session:
                    session.execute(
                        text(
                            "INSERT INTO llm_cache_entries (cache_key, key_version, provider_type, model, response, expires_at) "
                            "VALUES (:k, 1, 'fake', 'm', '{}', now() + interval '1 hour')"
                        ),
                        {"k": bad},
                    )
        with pytest.raises(IntegrityError, match="ck_llm_cache_entries_expires_after_created"):
            with migrated_database.session() as session:
                session.execute(
                    text(
                        "INSERT INTO llm_cache_entries (cache_key, key_version, provider_type, model, response, expires_at) "
                        "VALUES (:k, 1, 'fake', 'm', '{}', now() - interval '1 hour')"
                    ),
                    {"k": key(6)},
                )

    def test_concurrent_writers_produce_one_consistent_entry(self, migrated_database):
        store = PostgresCacheStore(migrated_database)
        k, start = key(7), threading.Barrier(12)
        seen = []

        def worker(i):
            start.wait()
            store.put(
                k, CachedResponse(f"writer-{i}"), ttl_seconds=60, provider_type="fake", model="m"
            )
            seen.append(store.get(k).text)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        with migrated_database.session() as session:
            assert (
                session.scalar(
                    text("SELECT count(*) FROM llm_cache_entries WHERE cache_key = :k"), {"k": k}
                )
                == 1
            )
        assert len(set(seen)) == 1 and len(seen) == 12  # every reader saw the single winner

    def test_unavailable_database_fails_open_and_logs_safely(self):
        stream = io.StringIO()
        configure_logging("INFO", stream=stream)
        try:
            store = PostgresCacheStore(unreachable_database())
            assert store.get(key(8)) is None
            store.put(key(8), CachedResponse("x"), ttl_seconds=60, provider_type="fake", model="m")
        finally:
            configure_logging("INFO")
        logged = stream.getvalue()
        assert logged.count('"cache.unavailable"') == 2 and "pw@" not in logged

    @pytest.mark.parametrize(
        "response",
        [
            "{}",
            '{"text": 5}',
            '{"text": "x", "input_tokens": "3"}',
            '{"text": "x", "output_tokens": true}',
            '{"text": "x", "finish_reason": []}',
        ],
    )
    def test_malformed_entry_is_a_logged_miss_not_an_error(self, migrated_database, response):
        k = hashlib.sha256(response.encode()).hexdigest()
        with migrated_database.session() as session:
            session.execute(
                text(
                    "INSERT INTO llm_cache_entries (cache_key, key_version, provider_type, model, response, expires_at) "
                    "VALUES (:k, 1, 'fake', 'm', CAST(:r AS jsonb), now() + interval '1 hour')"
                ),
                {"k": k, "r": response},
            )
        stream = io.StringIO()
        configure_logging("INFO", stream=stream)
        try:
            assert PostgresCacheStore(migrated_database).get(k) is None
        finally:
            configure_logging("INFO")
        assert '"cache.invalid_entry"' in stream.getvalue()

    def test_missing_table_fails_open(self, empty_database):
        migrate.upgrade(empty_database.engine, "0001")  # cache table not created yet
        store = PostgresCacheStore(empty_database)
        assert store.get(key(9)) is None
        store.put(key(9), CachedResponse("x"), ttl_seconds=60, provider_type="fake", model="m")


class TestPostgresRunBudget:
    def test_reserve_settle_and_exhaustion_marks_the_run(self, migrated_database):
        run_id = new_run(migrated_database, {"max_model_calls": 2, "max_estimated_tokens": 1000})
        budget = PostgresRunBudget(migrated_database, run_id)
        r1 = budget.reserve(REQUEST)
        assert run_row(migrated_database, run_id)[1:4] == (1, 0, 120)
        budget.settle(r1, Usage(30, 12))
        budget.settle(budget.reserve(REQUEST), None)
        assert run_row(migrated_database, run_id) == ("pending", 2, 42 + 120, 0, 0)
        with pytest.raises(BudgetExceededError, match="model_calls"):
            budget.reserve(REQUEST)
        assert run_row(migrated_database, run_id)[0] == "budget_exceeded"
        with pytest.raises(RunNotActiveError):  # an exhausted run stays stopped
            budget.reserve(REQUEST)

    def test_token_budget_rejects_a_reservation_that_does_not_fit(self, migrated_database):
        run_id = new_run(migrated_database, {"max_model_calls": 10, "max_estimated_tokens": 200})
        budget = PostgresRunBudget(migrated_database, run_id)
        budget.settle(budget.reserve(REQUEST), Usage(60, 40))
        with pytest.raises(BudgetExceededError, match="tokens"):
            budget.reserve(REQUEST)
        assert run_row(migrated_database, run_id)[:4] == ("budget_exceeded", 1, 100, 0)

    @pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "budget_exceeded"])
    def test_inactive_runs_cannot_spend(self, migrated_database, status):
        run_id = new_run(migrated_database, status=status)
        with pytest.raises(RunNotActiveError):
            PostgresRunBudget(migrated_database, run_id).reserve(REQUEST)
        assert run_row(migrated_database, run_id)[1] == 0

    def test_concurrent_workers_cannot_overspend(self, migrated_database):
        run_id = new_run(migrated_database, {"max_model_calls": 5})
        outcomes, start = [], threading.Barrier(20)

        def worker():
            budget = PostgresRunBudget(migrated_database, run_id)  # one guard per worker
            start.wait()
            try:
                budget.reserve(REQUEST)
                outcomes.append("ok")
            except (BudgetExceededError, RunNotActiveError):
                outcomes.append("refused")

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert outcomes.count("ok") == 5 and outcomes.count("refused") == 15
        assert run_row(migrated_database, run_id)[1] == 5

    def test_failed_update_is_rechecked_under_the_row_lock(self, migrated_database, monkeypatch):
        # Simulates the window between the conditional UPDATE (which saw another worker's
        # outstanding token reservation) and the row lock (taken after that worker settled).
        # The run has budget at decision time, so the reservation is granted and the run is
        # not wrongly marked budget_exceeded.
        run_id = new_run(migrated_database, {"max_model_calls": 5, "max_estimated_tokens": 1000})
        monkeypatch.setattr(budgets, "_RESERVE_SQL", text("SELECT NULL::bigint WHERE false"))
        reservation = PostgresRunBudget(migrated_database, run_id).reserve(REQUEST)
        assert reservation.tokens == 120
        assert run_row(migrated_database, run_id) == ("pending", 1, 0, 120, 0)

    def test_recheck_still_refuses_an_exhausted_budget(self, migrated_database, monkeypatch):
        run_id = new_run(migrated_database, {"max_model_calls": 5, "max_estimated_tokens": 100})
        monkeypatch.setattr(budgets, "_RESERVE_SQL", text("SELECT NULL::bigint WHERE false"))
        with pytest.raises(BudgetExceededError, match="tokens"):
            PostgresRunBudget(migrated_database, run_id).reserve(REQUEST)  # needs 120 > 100
        assert run_row(migrated_database, run_id) == ("budget_exceeded", 0, 0, 0, 0)

    def test_database_rejects_counter_above_limit_even_without_the_guard(self, migrated_database):
        run_id = new_run(migrated_database, {"max_model_calls": 2})
        with pytest.raises(IntegrityError, match="ck_runs_model_calls_within_limit"):
            with migrated_database.session() as session:
                session.execute(
                    text("UPDATE runs SET model_calls_used = 3 WHERE id = :id"), {"id": run_id}
                )

    def test_invalid_stored_limits_fail_closed(self, migrated_database):
        run_id = new_run(migrated_database)
        with migrated_database.session() as session:
            session.execute(
                text("UPDATE runs SET budget_limits = '{}' WHERE id = :id"), {"id": run_id}
            )
        adapter = FakeAdapter("p", default=FakeResponse(("x",)))
        with pytest.raises(InvalidBudgetError):
            router_with(adapter).generate(
                REQUEST, budget=PostgresRunBudget(migrated_database, run_id)
            )
        assert adapter.calls == []

    def test_create_run_requires_a_valid_budget(self, migrated_database):
        with pytest.raises(InvalidBudgetError):
            new_run(migrated_database, {"max_model_calls": 0})


class TestRouterWithPostgres:
    def test_cache_and_budget_end_to_end(self, migrated_database):
        run_id = new_run(migrated_database, {"max_model_calls": 1})
        budget = PostgresRunBudget(migrated_database, run_id)
        cache = CachePolicy(
            PostgresCacheStore(migrated_database), ttl_seconds=60, namespace={"t": run_id.hex}
        )
        adapter = FakeAdapter("p", default=FakeResponse(("fresh",), usage=Usage(5, 5)))
        router = router_with(adapter)
        assert router.generate(REQUEST, budget=budget, cache=cache).cache_hit is False
        hit = router.generate(REQUEST, budget=budget, cache=cache)
        assert (hit.cache_hit, hit.text, hit.usage) == (True, "fresh", Usage(5, 5))
        assert run_row(migrated_database, run_id) == ("pending", 1, 10, 0, 1)
        assert len(adapter.calls) == 1

    def test_stored_entry_holds_no_request_content(self, migrated_database):
        request = GenerationRequest.from_prompt(
            "PROMPT-MARKER", system="SYSTEM-MARKER", params=GenerationParams(max_output_tokens=9)
        )
        cache = CachePolicy(
            PostgresCacheStore(migrated_database), ttl_seconds=60, namespace={"run": "NS-MARKER"}
        )
        router_with(FakeAdapter("p", default=FakeResponse(("ANSWER-MARKER",)))).generate(
            request, cache=cache
        )
        with migrated_database.session() as session:
            row = session.scalar(
                text(
                    "SELECT row_to_json(e)::text FROM llm_cache_entries e "
                    "WHERE response->>'text' = 'ANSWER-MARKER'"
                )
            )
        assert row is not None
        for marker in ("PROMPT-MARKER", "SYSTEM-MARKER", "NS-MARKER"):
            assert marker not in row

    def test_unavailable_database_never_bypasses_the_budget(self):
        adapter = FakeAdapter("p", default=FakeResponse(("x",)))
        budget = PostgresRunBudget(unreachable_database(), uuid.uuid4())
        with pytest.raises(DatabaseUnavailableError):
            router_with(adapter).generate(REQUEST, budget=budget)
        assert adapter.calls == []

    def test_cache_outage_still_enforces_the_budget(self, migrated_database):
        run_id = new_run(migrated_database, {"max_model_calls": 1})
        budget = PostgresRunBudget(migrated_database, run_id)
        cache = CachePolicy(PostgresCacheStore(unreachable_database()), ttl_seconds=60)
        adapter = FakeAdapter("p", default=FakeResponse(("x",)))
        router = router_with(adapter)
        router.generate(REQUEST, budget=budget, cache=cache)  # cache fails open (miss)
        with pytest.raises(BudgetExceededError):
            router.generate(REQUEST, budget=budget, cache=cache)
        assert len(adapter.calls) == 1
        assert json.dumps(run_row(migrated_database, run_id)[:2]) == '["budget_exceeded", 1]'
