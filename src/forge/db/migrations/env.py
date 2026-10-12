"""Alembic environment for FORGE.

The database comes from ``config.attributes["engine"]`` (set by ``forge.db.migrate``) or,
for the ``alembic`` CLI, from ``DATABASE_URL`` via ``forge.settings.Settings``.
"""

from __future__ import annotations

import logging

from alembic import context
from sqlalchemy.engine import Engine

from forge.db.models import Base
from forge.db.session import Database
from forge.errors import ConfigurationError
from forge.settings import Settings

config = context.config
target_metadata = Base.metadata

if config.config_file_name is not None:  # invoked through the alembic CLI
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")


def _engine() -> Engine:
    engine = config.attributes.get("engine")
    if engine is not None:
        return engine
    settings = Settings.from_env()
    if settings.database is None:
        raise ConfigurationError("DATABASE_URL is not set; it is required to run migrations.")
    return Database(settings.database).engine


def run_migrations_offline() -> None:
    settings = Settings.from_env()
    if settings.database is None:
        raise ConfigurationError("DATABASE_URL is not set; it is required to generate SQL.")
    context.configure(
        url=settings.database.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with _engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
