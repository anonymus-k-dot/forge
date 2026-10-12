"""Session lifecycle, failure handling and /ready."""

import io
import json
import socket
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from forge.app import create_app
from forge.db.config import parse_database_settings
from forge.db.models import Workspace
from forge.db.session import Database
from forge.errors import DatabaseUnavailableError
from forge.logging import configure_logging
from forge.providers.config import load_providers_config
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from forge.settings import Settings

from .conftest import database_for

SECRET_PASSWORD = "Wr0ng-Secret-Pw"


def closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def unreachable_database() -> Database:
    settings = parse_database_settings(
        {
            "DATABASE_URL": f"postgresql://forge:{SECRET_PASSWORD}@127.0.0.1:{closed_port()}/forge",
            "DATABASE_CONNECT_TIMEOUT": "1",
        }
    )
    return Database(settings)


@pytest.fixture
def log_stream():
    stream = io.StringIO()
    yield stream
    configure_logging("INFO")


def ready(database, log_stream=None):
    app = create_app(Settings(), database=database)
    if log_stream is not None:
        configure_logging("INFO", stream=log_stream)
    return app.test_client().get("/ready")


class TestWithoutPostgres:
    def test_not_configured(self):
        response = create_app(Settings()).test_client().get("/ready")
        assert response.status_code == 503
        assert response.get_json() == {
            "status": "not_ready",
            "checks": {"database": "not_configured"},
        }

    def test_unreachable_database_is_safe(self, log_stream):
        response = ready(unreachable_database(), log_stream)
        assert response.status_code == 503
        assert response.get_json()["checks"]["database"] == "unavailable"
        for output in (response.get_data(as_text=True), log_stream.getvalue()):
            assert SECRET_PASSWORD not in output and "127.0.0.1" not in output
        assert '"db.unavailable"' in log_stream.getvalue()

    def test_session_on_unreachable_database_raises_safe_error(self):
        with pytest.raises(DatabaseUnavailableError) as info:
            with unreachable_database().session() as session:
                session.execute(text("SELECT 1"))
        assert str(info.value) == "The database is unavailable."
        assert isinstance(info.value.__cause__, OperationalError)
        assert SECRET_PASSWORD not in repr(info.value)

    def test_construction_never_connects(self):
        database = unreachable_database()
        assert database._engine is None
        assert SECRET_PASSWORD not in repr(database)

    def test_enhance_does_not_depend_on_the_database(self):
        database = unreachable_database()
        router = ProviderRouter(
            load_providers_config(),
            adapters={"gemini": FakeAdapter("gemini", default=FakeResponse(("ok",)))},
        )
        client = create_app(Settings(), router=router, database=database).test_client()
        streamed = client.post("/enhance", json={"prompt": "p"})
        assert (
            streamed.get_data(as_text=True) == 'data: {"chunk": "ok"}\n\ndata: {"done": true}\n\n'
        )
        assert client.post("/enhance", json={"prompt": "p", "stream": False}).status_code == 200
        assert database._engine is None  # the database was never touched


@pytest.mark.postgres
class TestSessionLifecycle:
    def count_workspaces(self, database, slug):
        with database.session() as session:
            return session.scalar(
                select(func.count()).select_from(Workspace).where(Workspace.slug == slug)
            )

    def test_commit_on_success_and_connection_returned(self, migrated_database):
        slug = f"ok-{uuid.uuid4().hex[:8]}"
        with migrated_database.session() as session:
            session.add(Workspace(slug=slug, name="x"))
        assert self.count_workspaces(migrated_database, slug) == 1
        assert migrated_database.engine.pool.checkedout() == 0

    def test_rollback_on_exception(self, migrated_database):
        slug = f"rb-{uuid.uuid4().hex[:8]}"
        with pytest.raises(RuntimeError):
            with migrated_database.session() as session:
                session.add(Workspace(slug=slug, name="x"))
                session.flush()  # the row exists inside the transaction...
                raise RuntimeError("boom")
        assert self.count_workspaces(migrated_database, slug) == 0  # ...and was rolled back
        assert migrated_database.engine.pool.checkedout() == 0

    def test_integrity_errors_propagate_unchanged(self, migrated_database):
        with pytest.raises(IntegrityError):
            with migrated_database.session() as session:
                session.add(Workspace(slug="BAD SLUG", name="x"))
        assert migrated_database.engine.pool.checkedout() == 0

    def test_no_transaction_left_open(self, migrated_database):
        with migrated_database.session() as session:
            session.execute(text("SELECT 1"))
        with migrated_database.engine.connect() as connection:
            idle_in_tx = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND application_name = 'forge' AND state LIKE 'idle in transaction%' "
                    "AND pid <> pg_backend_pid()"
                )
            )
        assert idle_in_tx == 0

    def test_application_name_is_set(self, migrated_database):
        with migrated_database.session() as session:
            assert session.scalar(text("SHOW application_name")) == "forge"


@pytest.mark.postgres
class TestReadiness:
    def test_ready_when_migrated(self, migrated_database):
        response = ready(migrated_database)
        assert response.status_code == 200
        assert response.get_json() == {"status": "ready", "checks": {"database": "ok"}}

    def test_migrations_pending_on_empty_database(self, empty_database):
        response = ready(empty_database)
        assert response.status_code == 503
        assert response.get_json()["checks"]["database"] == "migrations_pending"

    def test_rejected_credentials_are_unavailable_and_not_leaked(
        self, migrated_database, log_stream
    ):
        # A nonexistent role fails under every pg_hba method; a wrong password alone does
        # not (the postgres image trusts loopback connections inside its own network).
        role = "forge_no_such_role"
        url = migrated_database.settings.url.set(username=role, password=SECRET_PASSWORD)
        response = ready(database_for(url), log_stream)
        assert response.status_code == 503
        assert response.get_json()["checks"]["database"] == "unavailable"
        for output in (response.get_data(as_text=True), log_stream.getvalue()):
            assert SECRET_PASSWORD not in output and role not in output

    def test_health_and_home_unaffected_by_database_state(self, empty_database):
        client = create_app(Settings(), database=empty_database).test_client()
        assert client.get("/health").status_code == 200
        assert client.get("/").status_code == 200
        assert (
            json.loads(client.get("/ready").get_data())["checks"]["database"]
            == "migrations_pending"
        )
