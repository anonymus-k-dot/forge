"""The React web frontend (``web/``), served from its production build at ``/app/``.

``npm run build`` in ``web/`` writes the build to ``web/dist``; Flask only serves it:
``/app/`` returns ``index.html`` and ``/app/<file>`` the files beside it (content-hashed
bundles under ``assets/``). The classic interface (``/``) and the API routes are not
affected. Without a build, ``/app/`` answers 404 with instructions rather than failing.
"""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, current_app, send_from_directory

bp = Blueprint("web", __name__)

DIST_CONFIG_KEY = "FORGE_WEB_DIST"
"""Flask config key overriding the build directory (tests; default: ``DEFAULT_DIST``)."""

# src/forge/api/web.py -> repository root. Matches the source-tree layout used by
# `python app.py`, `gunicorn app:app` and the Docker image (which copies the repository).
DEFAULT_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"

ONE_YEAR = 365 * 24 * 60 * 60

# Every /app response. The build loads only same-origin scripts and styles, and model
# output is rendered as text, so nothing inline or third-party is allowed.
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)

NOT_BUILT_PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>FORGE web frontend not built</title></head>
<body>
<h1>The FORGE web frontend has not been built</h1>
<p>Build it with <code>npm ci</code> and <code>npm run build</code> in the <code>web/</code>
directory, then reload this page. The classic interface is at <a href="/">/</a>.</p>
</body>
</html>
"""


def dist_dir() -> Path:
    configured = current_app.config.get(DIST_CONFIG_KEY)
    return Path(configured) if configured else DEFAULT_DIST


@bp.route("/app/", methods=["GET"])
def index() -> Response:
    dist = dist_dir()
    if not (dist / "index.html").is_file():
        response = Response(NOT_BUILT_PAGE, status=404, mimetype="text/html")
        response.headers["Cache-Control"] = "no-store"
        return response
    response = send_from_directory(dist, "index.html", max_age=0)
    response.headers["Cache-Control"] = "no-cache"  # always revalidate: it names the bundles
    return response


@bp.route("/app/<path:filename>", methods=["GET"])
def asset(filename: str) -> Response:
    # send_from_directory refuses paths outside the build directory (404).
    response = send_from_directory(dist_dir(), filename, max_age=0)
    if filename.startswith("assets/"):  # content-hashed names: safe to cache for good
        response.headers["Cache-Control"] = f"public, max-age={ONE_YEAR}, immutable"
    else:
        response.headers["Cache-Control"] = "no-cache"
    return response


@bp.after_request
def security_headers(response: Response) -> Response:
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response
