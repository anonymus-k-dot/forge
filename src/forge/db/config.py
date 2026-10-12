"""Database connection settings parsed from the environment.

Only PostgreSQL is supported. The URL (which may contain a password) is never included in
error messages or ``repr``; use ``redacted_url`` when it must be shown.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.engine import URL, make_url

from forge.errors import ConfigurationError

POOL_MODES = ("session", "transaction")
SSL_MODES = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")
_POSTGRES_DRIVERS = ("postgres", "postgresql", "postgresql+psycopg")


@dataclass(frozen=True)
class DatabaseSettings:
    url: URL = field(repr=False)
    pool_size: int = 5
    max_overflow: int = 5
    pool_timeout: float = 10.0
    connect_timeout: int = 5
    # "transaction" for PgBouncer/Supavisor transaction pooling: disables server-side
    # prepared statements, which such poolers cannot track across connections.
    pool_mode: str = "session"

    @property
    def redacted_url(self) -> str:
        return self.url.render_as_string(hide_password=True)

    def __repr__(self) -> str:
        return (
            f"DatabaseSettings(url={self.redacted_url!r}, pool_size={self.pool_size}, "
            f"max_overflow={self.max_overflow}, pool_timeout={self.pool_timeout}, "
            f"connect_timeout={self.connect_timeout}, pool_mode={self.pool_mode!r})"
        )

    def connect_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {
            "connect_timeout": self.connect_timeout,
            "application_name": "forge",
        }
        if self.pool_mode == "transaction":
            args["prepare_threshold"] = None
        return args


def parse_database_settings(environ: Mapping[str, str]) -> DatabaseSettings | None:
    """Return settings, or ``None`` when ``DATABASE_URL`` is unset (database not configured)."""
    raw = (environ.get("DATABASE_URL") or "").strip()
    if not raw:
        return None
    try:
        url = make_url(raw)
    except Exception:  # noqa: BLE001 - the parser's message echoes the URL
        raise ConfigurationError("DATABASE_URL is not a valid database URL.") from None
    if url.drivername not in _POSTGRES_DRIVERS:
        raise ConfigurationError(
            "DATABASE_URL must be a PostgreSQL URL (postgresql://user:password@host:port/db); "
            f"got scheme '{url.drivername}'."
        )
    url = url.set(drivername="postgresql+psycopg")
    if not url.database:
        raise ConfigurationError("DATABASE_URL must include a database name.")

    sslmode = (environ.get("DATABASE_SSLMODE") or "").strip()
    if sslmode:
        url = url.update_query_dict({"sslmode": sslmode})
    url_sslmode = url.query.get("sslmode")
    if url_sslmode is not None and url_sslmode not in SSL_MODES:
        raise ConfigurationError(f"sslmode must be one of {', '.join(SSL_MODES)}.")

    pool_mode = (environ.get("DATABASE_POOL_MODE") or "session").strip().lower()
    if pool_mode not in POOL_MODES:
        raise ConfigurationError(f"DATABASE_POOL_MODE must be one of {', '.join(POOL_MODES)}.")

    return DatabaseSettings(
        url=url,
        pool_size=_int(environ, "DATABASE_POOL_SIZE", 5, 1, 100),
        max_overflow=_int(environ, "DATABASE_MAX_OVERFLOW", 5, 0, 100),
        pool_timeout=_float(environ, "DATABASE_POOL_TIMEOUT", 10.0, 0.1, 300.0),
        connect_timeout=_int(environ, "DATABASE_CONNECT_TIMEOUT", 5, 1, 120),
        pool_mode=pool_mode,
    )


def _int(environ: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer.") from None
    if not low <= value <= high:
        raise ConfigurationError(f"{name} must be between {low} and {high}.")
    return value


def _float(environ: Mapping[str, str], name: str, default: float, low: float, high: float) -> float:
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be a number.") from None
    if not low <= value <= high:
        raise ConfigurationError(f"{name} must be between {low} and {high}.")
    return value
