"""Initial Phase 0 schema: workspaces, runs, executions, evaluations.

Revision ID: 0001
Revises:
Create Date: 2026-10-12

Values in CHECK constraints are a snapshot taken at this revision; changing them in
``forge.db.models`` requires a new migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256_HEX = "^[0-9a-f]{64}$"


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _jsonb(name: str, *, default_empty: bool) -> sa.Column:
    return sa.Column(
        name,
        postgresql.JSONB(),
        server_default=sa.text("'{}'::jsonb") if default_empty else None,
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "workspaces",
        _uuid_pk(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
        sa.UniqueConstraint("slug", name=op.f("uq_workspaces_slug")),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{0,62}$'", name=op.f("ck_workspaces_slug_format")
        ),
    )

    op.create_table(
        "runs",
        _uuid_pk(),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        _jsonb("manifest", default_empty=False),
        sa.Column("manifest_hash", sa.Text(), nullable=False),
        sa.Column("forge_version", sa.Text(), nullable=False),
        _jsonb("budget_limits", default_empty=True),
        _created_at(),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_runs_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled', "
            "'budget_exceeded')",
            name=op.f("ck_runs_status_valid"),
        ),
        sa.CheckConstraint(
            f"manifest_hash ~ '{SHA256_HEX}'", name=op.f("ck_runs_manifest_hash_sha256")
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at)",
            name=op.f("ck_runs_finished_after_started"),
        ),
    )
    op.create_index(op.f("ix_runs_workspace_id_created_at"), "runs", ["workspace_id", "created_at"])
    op.create_index(op.f("ix_runs_manifest_hash"), "runs", ["manifest_hash"])

    op.create_table(
        "executions",
        _uuid_pk(),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Text(), nullable=False),
        sa.Column("system", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("sample_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("requested_model", sa.Text(), nullable=False),
        sa.Column("reported_model", sa.Text(), nullable=True),
        _jsonb("params", default_empty=True),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("finish_reason", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_source", sa.Text(), server_default="unknown", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error_category", sa.Text(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_executions")),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_executions_run_id_runs"), ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "run_id",
            "case_id",
            "system",
            "role",
            "sample_index",
            name=op.f("uq_executions_run_id_case_id_system_role_sample_index"),
        ),
        sa.CheckConstraint(
            "role IN ('generator', 'critic', 'judge', 'target')",
            name=op.f("ck_executions_role_valid"),
        ),
        sa.CheckConstraint(
            "usage_source IN ('provider', 'estimated', 'unknown')",
            name=op.f("ck_executions_usage_source_valid"),
        ),
        sa.CheckConstraint(
            "error_category IS NULL OR error_category IN ('configuration', 'authentication', "
            "'invalid_request', 'rate_limit', 'unavailable', 'timeout', 'server_error', "
            "'malformed_response', 'unsupported_capability', 'unknown')",
            name=op.f("ck_executions_error_category_valid"),
        ),
        sa.CheckConstraint(
            f"request_hash ~ '{SHA256_HEX}'", name=op.f("ck_executions_request_hash_sha256")
        ),
        sa.CheckConstraint(
            "sample_index >= 0", name=op.f("ck_executions_sample_index_non_negative")
        ),
        sa.CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND "
            "(output_tokens IS NULL OR output_tokens >= 0)",
            name=op.f("ck_executions_tokens_non_negative"),
        ),
        sa.CheckConstraint(
            "usage_source <> 'unknown' OR (input_tokens IS NULL AND output_tokens IS NULL)",
            name=op.f("ck_executions_unknown_usage_has_no_counts"),
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0", name=op.f("ck_executions_latency_non_negative")
        ),
        sa.CheckConstraint(
            "output_text IS NOT NULL OR error_category IS NOT NULL",
            name=op.f("ck_executions_has_output_or_error"),
        ),
    )

    op.create_table(
        "evaluations",
        _uuid_pk(),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator", sa.Text(), nullable=False),
        sa.Column("evaluator_version", sa.Text(), nullable=False),
        _jsonb("config", default_empty=True),
        _jsonb("results", default_empty=False),
        sa.Column("passed", sa.Boolean(), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluations")),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name=op.f("fk_evaluations_execution_id_executions"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "execution_id",
            "evaluator",
            "evaluator_version",
            name=op.f("uq_evaluations_execution_id_evaluator_evaluator_version"),
        ),
    )


def downgrade() -> None:
    # Drops all Phase 0 tables and their data. Only run deliberately (e.g. on a test database).
    op.drop_table("evaluations")
    op.drop_table("executions")
    op.drop_index(op.f("ix_runs_manifest_hash"), table_name="runs")
    op.drop_index(op.f("ix_runs_workspace_id_created_at"), table_name="runs")
    op.drop_table("runs")
    op.drop_table("workspaces")
