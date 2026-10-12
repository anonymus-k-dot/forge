"""Flask application factory."""

from __future__ import annotations

from flask import Flask

from forge.api import health, legacy
from forge.db.session import Database
from forge.legacy.enhance import LegacyEnhancer
from forge.logging import configure_logging, init_request_ids
from forge.providers.config import load_providers_config
from forge.providers.router import ProviderRouter
from forge.settings import Settings

SETTINGS_EXTENSION = "forge.settings"


def create_app(
    settings: Settings | None = None,
    *,
    router: ProviderRouter | None = None,
    database: Database | None = None,
) -> Flask:
    """Build the FORGE web application.

    Reads and validates the provider configuration file and configures logging, but
    performs no network or database I/O: provider clients and the database engine are
    created on first use. The app starts without a database; only ``/ready`` (and future
    persistence features) need one. ``router`` and ``database`` may be injected (tests).
    """
    settings = settings if settings is not None else Settings.from_env()
    configure_logging(settings.log_level)
    if router is None:
        router = ProviderRouter(
            load_providers_config(settings.providers_file), get_secret=settings.get_secret
        )

    app = Flask(__name__)
    app.extensions[SETTINGS_EXTENSION] = settings
    app.extensions[health.ROUTER_EXTENSION] = router
    if database is None and settings.database is not None:
        database = Database(settings.database)
    app.extensions[health.DATABASE_EXTENSION] = database
    app.extensions[legacy.ENHANCER_EXTENSION] = LegacyEnhancer(router)

    init_request_ids(app)
    app.register_blueprint(health.bp)
    app.register_blueprint(legacy.bp)
    return app
