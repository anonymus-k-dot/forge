"""PostgreSQL test fixtures.

Tests that need PostgreSQL use ``TEST_DATABASE_URL`` (a superuser-capable URL, typically the
``postgres`` maintenance database of the local Docker service) only to CREATE and DROP
throwaway databases named ``forge_test_<random>``. Nothing else on that server is touched.

- Unset ``TEST_DATABASE_URL``: PostgreSQL tests are skipped (reason shown), unless
  ``FORGE_REQUIRE_DB_TESTS=1`` (set in CI), which turns the skip into a failure.
- Non-local hosts, port 5432 (usually a developer's own PostgreSQL) and servers holding
  unexpected databases are refused; see ``tests/db/safety.py``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

from forge.db import migrate
from forge.db.config import parse_database_settings
from forge.db.session import Database

from .safety import (
    TEST_DB_PREFIX,
    UnsafeTestDatabase,
    check_server_inventory,
    resolve_test_admin_url,
)


@pytest.fixture(scope="session")
def pg_admin_url() -> URL:
    try:
        url = resolve_test_admin_url(os.environ)
    except UnsafeTestDatabase as exc:
        pytest.fail(f"Refusing destructive database tests: {exc}")
    if url is None:
        message = "TEST_DATABASE_URL is not set; PostgreSQL tests need a local PostgreSQL"
        if os.environ.get("FORGE_REQUIRE_DB_TESTS") == "1":
            pytest.fail(message + " (FORGE_REQUIRE_DB_TESTS=1)")
        pytest.skip(message)
    engine = create_engine(
        url, poolclass=NullPool, connect_args={"options": "-c default_transaction_read_only=on"}
    )
    try:
        with engine.connect() as connection:
            names = connection.execute(text("SELECT datname FROM pg_database")).scalars().all()
    finally:
        engine.dispose()
    try:
        check_server_inventory(names)
    except UnsafeTestDatabase as exc:
        pytest.fail(f"Refusing destructive database tests: {exc}")
    return url


@contextmanager
def temporary_database(admin_url: URL) -> Iterator[URL]:
    """Create an empty database for one test (or module) and drop it afterwards."""
    name = f"{TEST_DB_PREFIX}{uuid.uuid4().hex[:12]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield admin_url.set(database=name)
    finally:
        assert name.startswith(TEST_DB_PREFIX)
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def database_for(url: URL, **extra_env: str) -> Database:
    env = {"DATABASE_URL": url.render_as_string(hide_password=False), **extra_env}
    settings = parse_database_settings(env)
    assert settings is not None
    return Database(settings)


@pytest.fixture
def empty_database(pg_admin_url: URL) -> Iterator[Database]:
    with temporary_database(pg_admin_url) as url:
        database = database_for(url)
        try:
            yield database
        finally:
            database.dispose()


@pytest.fixture(scope="module")
def migrated_database(pg_admin_url: URL) -> Iterator[Database]:
    with temporary_database(pg_admin_url) as url:
        database = database_for(url)
        migrate.upgrade(database.engine)
        try:
            yield database
        finally:
            database.dispose()
