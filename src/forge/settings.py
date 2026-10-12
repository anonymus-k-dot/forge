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
            environ=snapshot,
        )

    def get_secret(self, name: str) -> str | None:
        """Value of the credential variable ``name``, or ``None`` if unset or blank."""
        return _optional(self.environ.get(name))


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
