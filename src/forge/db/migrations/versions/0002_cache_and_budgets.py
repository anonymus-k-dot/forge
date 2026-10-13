"""Response cache table and per-run budget counters.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13

Upgrade is additive: a new table, plus four counter columns on ``runs`` with constant
defaults (existing rows get 0) and CHECK constraints. Existing runs must have an object in
``budget_limits`` (the 0001 default ``{}`` satisfies this).

Downgrade drops the cache table (cached responses only; they can be regenerated) and the
budget counters (usage history of runs is lost). Only run it deliberately.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHA256_HEX = "^[0-9a-f]{64}$"


def upgrade() -> None:
    op.create_table(
        "llm_cache_entries",
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cache_key", name=op.f("pk_llm_cache_entries")),
        sa.CheckConstraint(
            f"cache_key ~ '{SHA256_HEX}'", name=op.f("ck_llm_cache_entries_cache_key_sha256")
        ),
        sa.CheckConstraint(
            "key_version >= 1", name=op.f("ck_llm_cache_entries_key_version_positive")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_llm_cache_entries_expires_after_created")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(response) = 'object'", name=op.f("ck_llm_cache_entries_response_object")
        ),
    )
    op.create_index(op.f("ix_llm_cache_entries_expires_at"), "llm_cache_entries", ["expires_at"])

    op.add_column(
        "runs",
        sa.Column("model_calls_used", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "runs",
        sa.Column("tokens_used", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "runs",
        sa.Column("tokens_reserved", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "runs", sa.Column("cache_hits", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    op.create_check_constraint(
        op.f("ck_runs_budget_limits_object"), "runs", "jsonb_typeof(budget_limits) = 'object'"
    )
    op.create_check_constraint(
        op.f("ck_runs_budget_counters_non_negative"),
        "runs",
        "model_calls_used >= 0 AND tokens_used >= 0 AND tokens_reserved >= 0 AND cache_hits >= 0",
    )
    op.create_check_constraint(
        op.f("ck_runs_model_calls_within_limit"),
        "runs",
        "budget_limits->>'max_model_calls' IS NULL "
        "OR model_calls_used <= (budget_limits->>'max_model_calls')::bigint",
    )


def downgrade() -> None:
    # Drops cached responses and per-run usage counters. Only run it deliberately.
    op.drop_constraint(op.f("ck_runs_model_calls_within_limit"), "runs", type_="check")
    op.drop_constraint(op.f("ck_runs_budget_counters_non_negative"), "runs", type_="check")
    op.drop_constraint(op.f("ck_runs_budget_limits_object"), "runs", type_="check")
    op.drop_column("runs", "cache_hits")
    op.drop_column("runs", "tokens_reserved")
    op.drop_column("runs", "tokens_used")
    op.drop_column("runs", "model_calls_used")
    op.drop_index(op.f("ix_llm_cache_entries_expires_at"), table_name="llm_cache_entries")
    op.drop_table("llm_cache_entries")
