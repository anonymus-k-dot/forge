"""
Compatibility entry point.

Keeps ``gunicorn app:app`` (Render, Dockerfile, docs) and ``python app.py`` working, and
re-exports the FORGE 1.x helper names. The implementation lives in ``src/forge``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import forge  # noqa: F401
except ModuleNotFoundError as exc:  # source checkout without `pip install -e .`
    if exc.name != "forge":
        raise
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from forge.api.health import ROUTER_EXTENSION  # noqa: E402
from forge.api.legacy import ENHANCER_EXTENSION  # noqa: E402
from forge.app import create_app  # noqa: E402
from forge.legacy.enhance import (  # noqa: E402, F401
    LegacyEnhancer,
    build_forge_prompt,
    clean_output as _clean_output,
)
from forge.providers.router import ProviderRouter  # noqa: E402

app = create_app()


def _router() -> ProviderRouter:
    router: ProviderRouter = app.extensions[ROUTER_EXTENSION]
    return router


def _enhancer() -> LegacyEnhancer:
    enhancer: LegacyEnhancer = app.extensions[ENHANCER_EXTENSION]
    return enhancer


# Model ID of the default profile (gemma-4-31b-it unless FORGE_PROVIDERS_FILE changes it).
GEMMA_MODEL = _router().profile().model


def enhance_prompt(user_prompt: str) -> dict[str, Any]:
    """Full pipeline: enhancement → parsed result (non-streaming fallback)."""
    return _enhancer().enhance(user_prompt)


def __getattr__(name: str) -> Any:
    # `app.client` used to be a module-level Google GenAI client created at import. It is
    # now the default provider adapter's client, created on first access (requires
    # GEMINI_API_KEY at that point). Only Google GenAI adapters expose `client`.
    if name == "client":
        router = _router()
        return getattr(router.adapter(router.profile().provider), "client")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
