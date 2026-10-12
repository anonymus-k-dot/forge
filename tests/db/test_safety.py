"""Regression tests for the destructive-test guards (no database connection needed).

Before this guard existed, TEST_DATABASE_URL=postgresql://...@127.0.0.1:5432/... (a
developer's own PostgreSQL) was accepted and tests would have created/dropped databases there.
"""

import pytest

from .safety import UnsafeTestDatabase, check_server_inventory, resolve_test_admin_url

USER = "postgresql://forge:pw"


def resolve(url, **env):
    return resolve_test_admin_url({"TEST_DATABASE_URL": url, **env})


class TestUrlGuard:
    @pytest.mark.parametrize(
        "url",
        [
            f"{USER}@127.0.0.1:5433/postgres",
            f"{USER}@localhost:55433/postgres",
            f"{USER}@db:5433/postgres",
        ],
    )
    def test_local_non_default_port_is_accepted(self, url):
        assert resolve(url).drivername == "postgresql+psycopg"

    @pytest.mark.parametrize(
        "url",
        [
            f"{USER}@127.0.0.1:5432/postgres",
            f"{USER}@localhost:5432/postgres",
            f"{USER}@localhost/postgres",
        ],
    )
    def test_default_port_is_refused(self, url):
        with pytest.raises(UnsafeTestDatabase, match="port 5432"):
            resolve(url)

    def test_default_port_override_for_disposable_servers(self):
        assert (
            resolve(f"{USER}@127.0.0.1:5432/postgres", FORGE_ALLOW_TEST_DB_PORT_5432="1").port
            == 5432
        )

    @pytest.mark.parametrize(
        "host",
        ["ep-cool-name-123456.eu-central-1.aws.neon.tech", "db.abcdefgh.supabase.co", "10.0.0.5"],
    )
    def test_non_local_host_is_refused(self, host):
        with pytest.raises(UnsafeTestDatabase, match="not local"):
            resolve(f"{USER}@{host}:5433/postgres")

    def test_remote_override_still_applies_port_rule(self):
        with pytest.raises(UnsafeTestDatabase, match="port 5432"):
            resolve(f"{USER}@10.0.0.5/postgres", FORGE_ALLOW_REMOTE_TEST_DB="1")
        assert (
            resolve(f"{USER}@10.0.0.5:5433/postgres", FORGE_ALLOW_REMOTE_TEST_DB="1").host
            == "10.0.0.5"
        )

    def test_unset_returns_none(self):
        assert resolve_test_admin_url({}) is None
        assert resolve_test_admin_url({"TEST_DATABASE_URL": "  "}) is None

    def test_refusal_message_has_no_password(self):
        with pytest.raises(UnsafeTestDatabase) as info:
            resolve("postgresql://forge:VerySecret123@127.0.0.1:5432/postgres")
        assert "VerySecret123" not in str(info.value)


class TestInventoryGuard:
    def test_disposable_server_is_accepted(self):
        check_server_inventory(["postgres", "template0", "template1", "forge", "forge_test_abc123"])

    def test_server_with_other_databases_is_refused(self):
        with pytest.raises(UnsafeTestDatabase, match="customers"):
            check_server_inventory(["postgres", "template0", "template1", "customers"])
