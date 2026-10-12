"""Guards that keep destructive database tests away from databases that matter.

The PostgreSQL tests CREATE and DROP throwaway databases, so the server named by
``TEST_DATABASE_URL`` must be disposable. Two independent checks:

1. URL (before any connection): the host must be local, and the port must not be 5432 —
   the default port, where a developer's own PostgreSQL usually listens. A URL without a
   port means 5432. Overrides, only for disposable servers: ``FORGE_ALLOW_REMOTE_TEST_DB=1``
   and ``FORGE_ALLOW_TEST_DB_PORT_5432=1``.
2. Inventory (read-only, after connecting): the server may only hold the default databases,
   ``forge``, and ``forge_test_*`` databases; anything else suggests real data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlalchemy.engine import URL, make_url

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "db", "postgres"})
DEFAULT_POSTGRES_PORT = 5432
DISPOSABLE_DATABASES = frozenset({"postgres", "template0", "template1", "forge"})
TEST_DB_PREFIX = "forge_test_"


class UnsafeTestDatabase(Exception):
    """The configured server is not safe for destructive tests."""


def resolve_test_admin_url(environ: Mapping[str, str]) -> URL | None:
    """Parse and check ``TEST_DATABASE_URL``; ``None`` when unset. Never connects."""
    raw = environ.get("TEST_DATABASE_URL", "").strip()
    if not raw:
        return None
    url = make_url(raw).set(drivername="postgresql+psycopg")
    if url.host not in LOCAL_HOSTS and environ.get("FORGE_ALLOW_REMOTE_TEST_DB") != "1":
        raise UnsafeTestDatabase(
            f"host {url.host!r} is not local; set FORGE_ALLOW_REMOTE_TEST_DB=1 only for a "
            "disposable server"
        )
    port = url.port or DEFAULT_POSTGRES_PORT
    if port == DEFAULT_POSTGRES_PORT and environ.get("FORGE_ALLOW_TEST_DB_PORT_5432") != "1":
        raise UnsafeTestDatabase(
            "port 5432 is the default PostgreSQL port, typically a developer's own server; "
            "use the Docker test server (e.g. 127.0.0.1:5433), or set "
            "FORGE_ALLOW_TEST_DB_PORT_5432=1 only for a disposable server"
        )
    return url


def check_server_inventory(database_names: Iterable[str]) -> None:
    unexpected = sorted(
        name
        for name in database_names
        if name not in DISPOSABLE_DATABASES and not name.startswith(TEST_DB_PREFIX)
    )
    if unexpected:
        raise UnsafeTestDatabase(
            f"the server holds databases not created for FORGE tests: {unexpected}"
        )
