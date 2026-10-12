"""Database configuration parsing and secret redaction (no database needed)."""

import pytest

from forge.app import create_app
from forge.db.config import parse_database_settings
from forge.errors import ConfigurationError
from forge.settings import Settings

PASSWORD = "S3cret-Pa55word"
URL = f"postgresql://forge:{PASSWORD}@db.example.test:5432/forge"


def parse(**env):
    return parse_database_settings({"DATABASE_URL": URL, **env})


class TestUrl:
    def test_unset_means_not_configured(self):
        assert parse_database_settings({}) is None
        assert parse_database_settings({"DATABASE_URL": "  "}) is None

    @pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+psycopg"])
    def test_postgres_schemes_use_psycopg3(self, scheme):
        settings = parse_database_settings({"DATABASE_URL": f"{scheme}://u:p@h:5432/d"})
        assert settings.url.drivername == "postgresql+psycopg"
        assert (settings.url.host, settings.url.port, settings.url.database) == ("h", 5432, "d")

    @pytest.mark.parametrize(
        "url",
        [
            "sqlite:///forge.db",
            f"mysql://u:{PASSWORD}@h/d",
            f"postgresql+asyncpg://u:{PASSWORD}@h/d",
        ],
    )
    def test_non_postgres_rejected_without_echoing(self, url):
        with pytest.raises(ConfigurationError, match="must be a PostgreSQL URL") as info:
            parse_database_settings({"DATABASE_URL": url})
        assert PASSWORD not in str(info.value)

    def test_unparseable_url_not_echoed(self):
        with pytest.raises(ConfigurationError, match="not a valid database URL") as info:
            parse_database_settings({"DATABASE_URL": f"::not a url {PASSWORD}"})
        assert PASSWORD not in str(info.value)

    def test_database_name_required(self):
        with pytest.raises(ConfigurationError, match="database name"):
            parse_database_settings({"DATABASE_URL": f"postgresql://u:{PASSWORD}@h:5432"})


class TestOptions:
    def test_defaults(self):
        settings = parse()
        assert (settings.pool_size, settings.max_overflow, settings.pool_timeout) == (5, 5, 10.0)
        assert (settings.connect_timeout, settings.pool_mode) == (5, "session")
        assert settings.connect_args() == {"connect_timeout": 5, "application_name": "forge"}

    def test_sslmode_env_overrides_url(self):
        settings = parse_database_settings(
            {"DATABASE_URL": URL + "?sslmode=disable", "DATABASE_SSLMODE": "require"}
        )
        assert settings.url.query["sslmode"] == "require"

    @pytest.mark.parametrize("env", [{"DATABASE_SSLMODE": "sometimes"}])
    def test_invalid_sslmode(self, env):
        with pytest.raises(ConfigurationError, match="sslmode"):
            parse(**env)

    def test_invalid_sslmode_in_url(self):
        with pytest.raises(ConfigurationError, match="sslmode"):
            parse_database_settings({"DATABASE_URL": URL + "?sslmode=bogus"})

    def test_transaction_pool_mode_disables_prepared_statements(self):
        assert parse(DATABASE_POOL_MODE="transaction").connect_args()["prepare_threshold"] is None
        assert "prepare_threshold" not in parse(DATABASE_POOL_MODE="session").connect_args()

    @pytest.mark.parametrize(
        ("name", "value", "message"),
        [
            ("DATABASE_POOL_SIZE", "0", "between"),
            ("DATABASE_POOL_SIZE", "many", "integer"),
            ("DATABASE_MAX_OVERFLOW", "-1", "between"),
            ("DATABASE_POOL_TIMEOUT", "nan", "between"),
            ("DATABASE_CONNECT_TIMEOUT", "0", "between"),
            ("DATABASE_POOL_MODE", "statement", "DATABASE_POOL_MODE"),
        ],
    )
    def test_invalid_values(self, name, value, message):
        with pytest.raises(ConfigurationError, match=message):
            parse(**{name: value})

    def test_numeric_overrides(self):
        settings = parse(
            DATABASE_POOL_SIZE="2",
            DATABASE_MAX_OVERFLOW="0",
            DATABASE_POOL_TIMEOUT="2.5",
            DATABASE_CONNECT_TIMEOUT="3",
        )
        assert (settings.pool_size, settings.max_overflow) == (2, 0)
        assert (settings.pool_timeout, settings.connect_timeout) == (2.5, 3)


class TestRedaction:
    def test_repr_and_redacted_url_hide_password(self):
        settings = parse()
        for text in (
            repr(settings),
            str(settings),
            settings.redacted_url,
            repr(Settings.from_env({"DATABASE_URL": URL})),
        ):
            assert PASSWORD not in text
        assert "***" in settings.redacted_url

    def test_app_construction_does_not_connect(self):
        app = create_app(Settings.from_env({"DATABASE_URL": URL}))
        database = app.extensions["forge.database"]
        assert database is not None and database._engine is None
        client = app.test_client()
        assert client.get("/health").status_code == 200
        assert client.get("/").status_code == 200
        assert database._engine is None  # neither route touched the database
