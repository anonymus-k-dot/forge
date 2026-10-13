"""Small data-access helpers over an explicit ``Session`` (the caller owns the transaction)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from forge.db.models import Execution, Run, Workspace
from forge.infrastructure.budgets import BudgetLimits


def get_or_create_workspace(session: Session, slug: str, name: str) -> Workspace:
    """Return the workspace with ``slug``, creating it if needed (safe under concurrency)."""
    session.execute(
        insert(Workspace)
        .values(slug=slug, name=name)
        .on_conflict_do_nothing(index_elements=["slug"])
    )
    return session.execute(select(Workspace).where(Workspace.slug == slug)).scalar_one()


def create_run(
    session: Session,
    *,
    workspace: Workspace,
    manifest: dict[str, Any],
    manifest_hash: str,
    forge_version: str,
    budget_limits: Mapping[str, Any],
) -> Run:
    """Create a run. ``budget_limits`` is validated; ``max_model_calls`` is required so that
    no run can make an unbounded number of model calls (ADR-018)."""
    run = Run(
        workspace=workspace,
        manifest=manifest,
        manifest_hash=manifest_hash,
        forge_version=forge_version,
        budget_limits=BudgetLimits.parse(dict(budget_limits)).to_json(),
    )
    session.add(run)
    session.flush()
    return run


def get_run(session: Session, run_id: uuid.UUID) -> Run | None:
    """A run with its executions and their evaluations loaded."""
    return session.execute(
        select(Run)
        .where(Run.id == run_id)
        .options(selectinload(Run.executions).selectinload(Execution.evaluations))
    ).scalar_one_or_none()
