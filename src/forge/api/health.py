"""Liveness (``/health``) and readiness (``/ready``) endpoints."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify

from forge.db.session import Database
from forge.providers.router import ProviderRouter

bp = Blueprint("health", __name__)

ROUTER_EXTENSION = "forge.provider_router"
DATABASE_EXTENSION = "forge.database"


@bp.route("/health", methods=["GET"])
def health() -> Response:
    """Process liveness only; does not contact the model provider or the database.

    ``model`` is the default profile's configured model ID. ``templates_loaded`` is a
    deprecated field kept for compatibility and is always 0.
    """
    router: ProviderRouter = current_app.extensions[ROUTER_EXTENSION]
    return jsonify(
        {
            "status": "ok",
            "templates_loaded": 0,
            "model": router.profile().model,
        }
    )


@bp.route("/ready", methods=["GET"])
def ready() -> tuple[Response, int]:
    """Readiness: 200 only when PostgreSQL is reachable and migrated to the code's head.

    ``checks.database`` is one of ``ok``, ``not_configured``, ``unavailable``,
    ``migrations_pending``. No connection details or error text are returned.
    """
    database: Database | None = current_app.extensions.get(DATABASE_EXTENSION)
    state = "not_configured" if database is None else database.readiness()
    ready_ = state == "ok"
    body = {"status": "ready" if ready_ else "not_ready", "checks": {"database": state}}
    return jsonify(body), 200 if ready_ else 503
