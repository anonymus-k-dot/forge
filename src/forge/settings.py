"""Application settings: the single place that reads process configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from dotenv import find_dotenv, load_dotenv

from forge.db.config import DatabaseSettings, parse_database_settings
from forge.errors import ConfigurationError

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration.

    Every field is optional so the web app can start (and serve ``/health``) with no
    credentials. Components that need a value raise ``ConfigurationError`` when used.
    """

    # Path to a provider/model JSON file (FORGE_PROVIDERS_FILE); None = packaged default.
    providers_file: str | None = None
    # FORGE_LOG_LEVEL: DEBUG, INFO, WARNING, ERROR or CRITICAL.
    log_level: str = "INFO"
    # DATABASE_URL and DATABASE_* pool options; None = no database configured.
    database: DatabaseSettings | None = None
    # FORGE_CACHE_TTL_SECONDS: lifetime of response-cache entries (used by runs, not /enhance).
    cache_ttl_seconds: int = 30 * 24 * 3600
    # Process environment snapshot, used only to look up credentials by variable name.
    # Excluded from repr/eq so secrets never end up in logs or tracebacks.
    environ: Mapping[str, str] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Build settings from ``environ``, or from ``os.environ`` plus a ``.env`` file.

        The ``.env`` file is searched for from the current working directory upwards and
        never overrides variables that are already set.
        """
        if environ is None:
            dotenv_path = find_dotenv(usecwd=True)
            if dotenv_path:
                load_dotenv(dotenv_path)
            environ = os.environ
        snapshot = dict(environ)
        log_level = (_optional(snapshot.get("FORGE_LOG_LEVEL")) or "INFO").upper()
        if log_level not in LOG_LEVELS:
            raise ConfigurationError(f"FORGE_LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")
        return cls(
            providers_file=_optional(snapshot.get("FORGE_PROVIDERS_FILE")),
            log_level=log_level,
            database=parse_database_settings(snapshot),
            cache_ttl_seconds=_cache_ttl(snapshot.get("FORGE_CACHE_TTL_SECONDS")),
            environ=snapshot,
        )

    def get_secret(self, name: str) -> str | None:
        """Value of the credential variable ``name``, or ``None`` if unset or blank."""
        return _optional(self.environ.get(name))


def _cache_ttl(raw: str | None) -> int:
    from forge.infrastructure.cache import DEFAULT_TTL_SECONDS, validate_ttl

    value = _optional(raw)
    if value is None:
        return DEFAULT_TTL_SECONDS
    try:
        seconds = int(value)
    except ValueError:
        raise ConfigurationError("FORGE_CACHE_TTL_SECONDS must be an integer.") from None
    try:
        return validate_ttl(seconds)
    except ConfigurationError as exc:
        raise ConfigurationError(f"FORGE_CACHE_TTL_SECONDS: {exc}") from None


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
