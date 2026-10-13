"""Phase 0 schema (docs/architecture/target-architecture.md §6).

History tables reference their parents with ``ON DELETE RESTRICT``: deleting a workspace,
run, or execution that still has dependent rows fails instead of silently erasing
experiment history. Raw model output (``executions``) is stored separately from derived
results (``evaluations``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from forge.providers.errors import ErrorCategory

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

RUN_STATUSES = ("pending", "running", "completed", "failed", "cancelled", "budget_exceeded")
EXECUTION_ROLES = ("generator", "critic", "judge", "target")
USAGE_SOURCES = ("provider", "estimated", "unknown")
ERROR_CATEGORIES = tuple(category.value for category in ErrorCategory)
SHA256_HEX = "^[0-9a-f]{64}$"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        uuid.UUID: Uuid(),
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB(),
        str: Text(),
    }


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now())


class Workspace(Base):
    """Isolation boundary for all user content."""

    __tablename__ = "workspaces"
    __table_args__ = (CheckConstraint("slug ~ '^[a-z0-9][a-z0-9-]{0,62}$'", name="slug_format"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    created_at: Mapped[datetime] = _created_at()

    runs: Mapped[list[Run]] = relationship(back_populates="workspace", passive_deletes="all")


class Run(Base):
    """One benchmark or evaluation run, defined by an immutable, hashed manifest."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="status_valid"),
        CheckConstraint(f"manifest_hash ~ '{SHA256_HEX}'", name="manifest_hash_sha256"),
        CheckConstraint(
            "finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at)",
            name="finished_after_started",
        ),
        Index(None, "workspace_id", "created_at"),
        Index(None, "manifest_hash"),
        # Budget counters (revision 0002). The call limit is also enforced by the database;
        # token usage may legitimately exceed the pre-call estimate, so it is not.
        CheckConstraint("jsonb_typeof(budget_limits) = 'object'", name="budget_limits_object"),
        CheckConstraint(
            "model_calls_used >= 0 AND tokens_used >= 0 AND tokens_reserved >= 0 "
            "AND cache_hits >= 0",
            name="budget_counters_non_negative",
        ),
        CheckConstraint(
            "budget_limits->>'max_model_calls' IS NULL "
            "OR model_calls_used <= (budget_limits->>'max_model_calls')::bigint",
            name="model_calls_within_limit",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(default="pending", server_default="pending")
    manifest: Mapped[dict[str, Any]]
    manifest_hash: Mapped[str]
    forge_version: Mapped[str]
    budget_limits: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    model_calls_used: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    tokens_used: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    tokens_reserved: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    cache_hits: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))

    workspace: Mapped[Workspace] = relationship(back_populates="runs")
    executions: Mapped[list[Execution]] = relationship(back_populates="run", passive_deletes="all")


class Execution(Base):
    """One model call: its exact configuration and raw output, never derived scores."""

    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", "system", "role", "sample_index"),
        CheckConstraint(_in("role", EXECUTION_ROLES), name="role_valid"),
        CheckConstraint(_in("usage_source", USAGE_SOURCES), name="usage_source_valid"),
        CheckConstraint(
            f"error_category IS NULL OR {_in('error_category', ERROR_CATEGORIES)}",
            name="error_category_valid",
        ),
        CheckConstraint(f"request_hash ~ '{SHA256_HEX}'", name="request_hash_sha256"),
        CheckConstraint("sample_index >= 0", name="sample_index_non_negative"),
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0)",
            name="tokens_non_negative",
        ),
        CheckConstraint(
            "usage_source <> 'unknown' OR (input_tokens IS NULL AND output_tokens IS NULL)",
            name="unknown_usage_has_no_counts",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_non_negative"),
        CheckConstraint(
            "output_text IS NOT NULL OR error_category IS NOT NULL",
            name="has_output_or_error",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="RESTRICT"))
    case_id: Mapped[str]
    system: Mapped[str]
    role: Mapped[str]
    sample_index: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    provider: Mapped[str]
    requested_model: Mapped[str]
    reported_model: Mapped[str | None]
    params: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    request_hash: Mapped[str]
    output_text: Mapped[str | None]
    finish_reason: Mapped[str | None]
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    usage_source: Mapped[str] = mapped_column(default="unknown", server_default="unknown")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    error_category: Mapped[str | None]
    created_at: Mapped[datetime] = _created_at()

    run: Mapped[Run] = relationship(back_populates="executions")
    evaluations: Mapped[list[Evaluation]] = relationship(
        back_populates="execution", passive_deletes="all"
    )


class Evaluation(Base):
    """A derived result for one execution from one versioned evaluator.

    Re-scoring with changed evaluator logic must use a new ``evaluator_version`` (a new row),
    never overwrite an existing evaluation.
    """

    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("execution_id", "evaluator", "evaluator_version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("executions.id", ondelete="RESTRICT")
    )
    evaluator: Mapped[str]
    evaluator_version: Mapped[str]
    config: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))
    results: Mapped[dict[str, Any]]
    # NULL when the evaluator could not decide (e.g. invalid judgment); never guessed.
    passed: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = _created_at()

    execution: Mapped[Execution] = relationship(back_populates="evaluations")


class LlmCacheEntry(Base):
    """A cached successful model response (revision 0002). The key is the SHA-256 of the
    canonical request document (``forge.infrastructure.cache``); the request itself is not
    stored. Expired rows are ignored by lookups and replaced by the next successful call."""

    __tablename__ = "llm_cache_entries"
    __table_args__ = (
        CheckConstraint(f"cache_key ~ '{SHA256_HEX}'", name="cache_key_sha256"),
        CheckConstraint("key_version >= 1", name="key_version_positive"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint("jsonb_typeof(response) = 'object'", name="response_object"),
        Index(None, "expires_at"),
    )

    cache_key: Mapped[str] = mapped_column(primary_key=True)
    key_version: Mapped[int] = mapped_column(Integer)
    provider_type: Mapped[str]
    model: Mapped[str]
    response: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime]
