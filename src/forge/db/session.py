"""Engine and session lifecycle.

Nothing connects at import or construction time: the engine is created on first use, so
each Gunicorn worker builds its own pool after forking. Sessions are explicit and short:
use ``with database.session() as session:`` around one unit of work; it commits on success,
rolls back on any exception, and always closes (returning the connection to the pool).
Never hold a session open across a model call or an SSE stream.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from forge.db import migrate
from forge.db.config import DatabaseSettings
from forge.errors import DatabaseUnavailableError

logger = logging.getLogger(__name__)

Readiness = Literal["ok", "unavailable", "migrations_pending"]

# Connections are recycled before typical idle timeouts of hosted poolers/load balancers.
POOL_RECYCLE_SECONDS = 300


class Database:
    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self._engine: Engine | None = None
        self._sessions: sessionmaker[Session] | None = None
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"Database({self.settings.redacted_url!r})"

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    self._engine = create_engine(
                        self.settings.url,
                        pool_size=self.settings.pool_size,
                        max_overflow=self.settings.max_overflow,
                        pool_timeout=self.settings.pool_timeout,
                        pool_pre_ping=True,
                        pool_recycle=POOL_RECYCLE_SECONDS,
                        connect_args=self.settings.connect_args(),
                        hide_parameters=True,
                    )
                    self._sessions = sessionmaker(self._engine, expire_on_commit=False)
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        """One transaction: commit on success, roll back on error, always close.

        Connection-level failures are raised as ``DatabaseUnavailableError``; other database
        errors (e.g. constraint violations) propagate unchanged after rollback.
        """
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except BaseException as exc:
            try:
                session.rollback()
            except SQLAlchemyError:
                pass  # the connection is already broken; report the original error
            if isinstance(exc, OperationalError | InterfaceError):
                logger.warning(
                    "db.unavailable", extra={"forge": {"error_type": type(exc).__name__}}
                )
                raise DatabaseUnavailableError() from exc
            raise
        finally:
            session.close()

    @property
    def _session_factory(self) -> sessionmaker[Session]:
        self.engine  # noqa: B018 - creates the engine and sessionmaker on first use
        if self._sessions is None:  # pragma: no cover - set together with the engine
            raise RuntimeError("session factory not initialised")
        return self._sessions

    def readiness(self) -> Readiness:
        """``ok`` only if the database answers and is migrated to the packaged head."""
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                current = migrate.current_revision(connection)
        except SQLAlchemyError as exc:
            logger.warning("db.unavailable", extra={"forge": {"error_type": type(exc).__name__}})
            return "unavailable"
        if current != migrate.head_revision():
            return "migrations_pending"
        return "ok"

    def dispose(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
