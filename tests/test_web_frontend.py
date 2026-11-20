"""The React web frontend (web/) and its Flask integration at /app/.

- Flask serving (/app/, assets, headers, missing build) against a stand-in build in a
  temporary directory, so these run without Node or a real build.
- The frontend unit tests (web/tests/unit, Node's test runner with type stripping).
- The real production build, when web/dist exists (`npm run build`).
- The Docker build configuration (statically: the frontend stage and the copied path).
- A headless-browser check of the real build against Flask with a scripted fake provider:
  opt-in (FORGE_BROWSER_TESTS=1) because it starts Chrome; needs the build.

Without Node or a build, the Node and build tests skip; FORGE_REQUIRE_WEB_BUILD=1 (CI's
frontend job) turns those skips into failures, so they cannot be skipped there.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import NoReturn

import pytest
from flask import jsonify
from werkzeug.serving import make_server

from forge.api.web import CONTENT_SECURITY_POLICY, DEFAULT_DIST, DIST_CONFIG_KEY
from forge.app import create_app
from forge.providers import errors
from forge.providers.base import StreamEnd, TextDelta
from forge.providers.config import load_providers_config
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from forge.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB = REPO_ROOT / "web"
BUILT_INDEX = DEFAULT_DIST / "index.html"


def unavailable(reason: str) -> NoReturn:
    """Skip, or fail when FORGE_REQUIRE_WEB_BUILD=1 (never silently skipped in CI)."""
    if os.environ.get("FORGE_REQUIRE_WEB_BUILD") == "1":
        pytest.fail(f"{reason} (FORGE_REQUIRE_WEB_BUILD=1)")
    pytest.skip(reason)


def make_app(adapter=None, dist=None):
    adapter = adapter or FakeAdapter("gemini", [FakeResponse(("ok",))])
    router = ProviderRouter(
        load_providers_config(), adapters={"gemini": adapter}, sleep=lambda s: None
    )
    app = create_app(Settings(), router=router)
    if dist is not None:
        app.config[DIST_CONFIG_KEY] = str(dist)
    return app


@pytest.fixture
def fake_dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        '<!doctype html><title>FORGE</title><div id="root"></div>'
        '<script type="module" src="/app/assets/index-abc123.js"></script>',
        encoding="utf-8",
    )
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "assets" / "index-abc123.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return tmp_path


# ── Flask serving ───────────────────────────────────────────────────────────


def test_app_redirects_to_trailing_slash(fake_dist):
    response = make_app(dist=fake_dist).test_client().get("/app")
    assert response.status_code == 308
    assert response.headers["Location"].endswith("/app/")


def test_index_is_served_with_security_headers(fake_dist):
    response = make_app(dist=fake_dist).test_client().get("/app/")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.get_data() == (fake_dist / "index.html").read_bytes()
    assert response.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    assert "script-src 'self'" in CONTENT_SECURITY_POLICY
    assert "'unsafe-inline'" not in CONTENT_SECURITY_POLICY
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-cache"


def test_hashed_assets_are_cached_and_other_files_revalidated(fake_dist):
    client = make_app(dist=fake_dist).test_client()
    js = client.get("/app/assets/index-abc123.js")
    assert js.status_code == 200
    assert js.mimetype in {"text/javascript", "application/javascript"}
    assert js.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert js.headers["Content-Security-Policy"] == CONTENT_SECURITY_POLICY
    css = client.get("/app/assets/index-abc123.css")
    assert css.status_code == 200 and css.mimetype == "text/css"
    icon = client.get("/app/favicon.svg")
    assert icon.status_code == 200 and icon.mimetype == "image/svg+xml"
    assert icon.headers["Cache-Control"] == "no-cache"


def test_missing_files_and_paths_outside_the_build_are_404(fake_dist):
    (fake_dist.parent / "secret.txt").write_text("outside the build", encoding="utf-8")
    client = make_app(dist=fake_dist).test_client()
    for path in (
        "/app/assets/missing.js",
        "/app/../secret.txt",
        "/app/%2e%2e/secret.txt",
        "/app/assets/..%2f..%2fsecret.txt",
    ):
        response = client.get(path)
        assert response.status_code == 404, path
        assert b"outside the build" not in response.get_data()


def test_only_get_is_allowed(fake_dist):
    client = make_app(dist=fake_dist).test_client()
    assert client.post("/app/").status_code == 405
    assert client.post("/app/assets/index-abc123.js").status_code == 405


def test_missing_build_explains_how_to_build(tmp_path):
    client = make_app(dist=tmp_path / "no-build").test_client()
    response = client.get("/app/")
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_data(as_text=True)
    assert "npm run build" in body and 'href="/"' in body
    assert "http" not in body.replace('href="/"', "")  # no external resources
    assert client.get("/app/assets/index.js").status_code == 404


def test_legacy_ui_and_api_are_unchanged_alongside_the_new_frontend(fake_dist):
    client = make_app(dist=fake_dist).test_client()
    legacy = client.get("/")
    assert legacy.status_code == 200
    assert 'data-forge="app"' in legacy.get_data(as_text=True)  # the classic template
    assert "Content-Security-Policy" not in legacy.headers  # /app headers stay on /app
    assert client.get("/health").get_json()["status"] == "ok"
    stream = client.post("/enhance", json={"prompt": "p"})
    assert stream.mimetype == "text/event-stream"
    assert stream.get_data(as_text=True) == 'data: {"chunk": "ok"}\n\ndata: {"done": true}\n\n'
    assert client.post("/enhance", json={"prompt": ""}).status_code == 400


def test_route_table_only_adds_the_app_routes():
    rules = {
        (rule.rule, tuple(sorted(rule.methods - {"HEAD", "OPTIONS"})))
        for rule in make_app().url_map.iter_rules()
    }
    assert rules == {
        ("/", ("GET",)),
        ("/enhance", ("POST",)),
        ("/health", ("GET",)),
        ("/ready", ("GET",)),
        ("/static/<path:filename>", ("GET",)),
        ("/app/", ("GET",)),
        ("/app/<path:filename>", ("GET",)),
    }


# ── Frontend source checks ─────────────────────────────────────────────────


def frontend_sources():
    return [p for p in (WEB / "src").rglob("*") if p.suffix in {".ts", ".tsx", ".css"}]


def test_frontend_never_renders_model_output_as_html():
    for path in frontend_sources():
        text = path.read_text(encoding="utf-8")
        assert "dangerouslySetInnerHTML" not in text, path
        assert "innerHTML" not in text, path
        assert "insertAdjacentHTML" not in text, path


def test_frontend_loads_nothing_from_other_origins():
    for path in [*frontend_sources(), WEB / "index.html"]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"""(?:src|href|url)\s*[=(]\s*["']?https?://""", text), path
        assert "@import" not in text, path
        assert "fonts.googleapis" not in text and "cdn." not in text, path


def test_frontend_does_not_intercept_copy_or_hide_the_cursor():
    for path in frontend_sources():
        text = path.read_text(encoding="utf-8")
        assert "cursor: none" not in text, path
        assert not re.search(r"""key(?:\.toLowerCase\(\))?\s*===\s*["']c["']""", text), path
        assert not re.search(r"""addEventListener\(\s*["'](?:copy|cut)["']""", text), path


def luminance(hex_color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_text_colours_meet_wcag_aa():
    tokens = (WEB / "src" / "styles" / "tokens.css").read_text(encoding="utf-8")

    def token(name: str) -> str:
        return re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", tokens).group(1)

    surfaces = [
        token(n) for n in ("surface-page", "surface-card", "surface-elevated", "surface-hover")
    ]
    foregrounds = [token(n) for n in ("label", "accent", "text", "text-output", "warning", "error")]
    failing = {
        (fg, bg): round(contrast(fg, bg), 2)
        for fg in foregrounds
        for bg in surfaces
        if contrast(fg, bg) < 4.5
    }
    assert not failing, failing
    assert contrast(token("text-output"), token("error-surface")) >= 4.5


# ── Frontend unit tests (Node) ─────────────────────────────────────────────


def node_with_type_stripping() -> str:
    node = shutil.which("node")
    if node is None:
        unavailable("Node.js is not installed")
    probe = subprocess.run(
        [node, "-e", "process.exit(process.features.typescript ? 0 : 1)"], capture_output=True
    )
    if probe.returncode != 0:
        unavailable("this Node.js cannot run TypeScript directly (needs Node 22.18+ or 23.6+)")
    return node


def test_frontend_unit_tests():
    node = node_with_type_stripping()
    result = subprocess.run(
        [node, "--test", "tests/unit/*.test.mjs"],
        cwd=WEB,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    passed = re.search(r"(?:ℹ|#) pass (\d+)", output)
    assert passed and int(passed.group(1)) >= 40, output
    assert re.search(r"(?:ℹ|#) fail 0", output), output


# ── The real production build (web/dist) ──────────────────────────────────


def require_build() -> None:
    if not BUILT_INDEX.is_file():
        unavailable("web/dist is not built (npm run build in web/)")


def test_production_build_is_served_with_all_its_assets():
    require_build()
    client = make_app().test_client()
    index = client.get("/app/")
    assert index.status_code == 200
    html = index.get_data(as_text=True)
    assert not re.search(r"""(?:src|href)=["']https?://""", html), "external resource in build"
    # The CSP allows only same-origin files: no inline scripts, styles or style attributes.
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "inline script"
    assert "<style" not in html and " style=" not in html, "inline style"
    assets = re.findall(r"""(?:src|href)=["'](/app/[^"']+)["']""", html)
    assert any(a.endswith(".js") for a in assets) and any(a.endswith(".css") for a in assets)
    for asset in assets:
        response = client.get(asset)
        assert response.status_code == 200, asset
        if asset.endswith(".js"):
            assert response.mimetype in {"text/javascript", "application/javascript"}
        if asset.endswith(".css"):
            assert response.mimetype == "text/css"
            # The minifier keeps the last of a prefixed/unprefixed pair; a lone -webkit-
            # backdrop-filter does nothing in Chrome or Firefox (this happened once).
            for rule in re.findall(r"\{[^}]*\}", response.get_data(as_text=True)):
                if "-webkit-backdrop-filter" in rule:
                    assert re.search(r"[;{]backdrop-filter:", rule), rule


def test_production_build_exposes_no_source_maps_or_build_settings():
    require_build()
    files = [p for p in DEFAULT_DIST.rglob("*") if p.is_file()]
    assert not [p for p in files if p.suffix == ".map"], "source maps in the build"
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        assert "sourceMappingURL" not in text, path
        # Build-time settings (the dev proxy target, env names) must not reach the browser.
        for leaked in ("FORGE_API_ORIGIN", "VITE_", "127.0.0.1", "localhost:5000"):
            assert leaked not in text, (path, leaked)


# ── Docker build configuration (checked statically; CI does not build the image) ──


def dockerignored(path: str, patterns: list[str]) -> bool:
    """Docker's .dockerignore rules (later patterns win, "!" re-includes, parents count)."""

    def matches(pattern: str, candidate: str) -> bool:
        regex = ""
        i = 0
        while i < len(pattern):
            if pattern.startswith("**/", i):
                regex += "(?:.*/)?"
                i += 3
            elif pattern.startswith("**", i):
                regex += ".*"
                i += 2
            elif pattern[i] == "*":
                regex += "[^/]*"
                i += 1
            elif pattern[i] == "?":
                regex += "[^/]"
                i += 1
            else:
                regex += re.escape(pattern[i])
                i += 1
        return re.fullmatch(regex, candidate) is not None

    parts = path.split("/")
    candidates = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    ignored = False
    for raw in patterns:
        negate = raw.startswith("!")
        pattern = (raw[1:] if negate else raw).strip("/")
        if any(matches(pattern, candidate) for candidate in candidates):
            ignored = not negate
    return ignored


def test_docker_image_builds_the_frontend_and_ships_only_its_output():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    stages = re.split(r"^FROM ", dockerfile, flags=re.M)[1:]
    assert len(stages) == 2, "a frontend build stage, then the Python runtime"
    web_stage, runtime = stages
    assert web_stage.startswith("node:") and " AS web" in web_stage.splitlines()[0]
    assert "COPY web/package.json web/package-lock.json ./" in web_stage
    assert re.search(r"RUN npm ci\b", web_stage)  # the locked dependency graph
    assert "npm test" in web_stage and "npm run build" in web_stage  # build type-checks
    # The runtime takes only the build output from that stage, at the path Flask serves
    # (DEFAULT_DIST is web/dist under the application root, WORKDIR /app).
    assert DEFAULT_DIST == REPO_ROOT / "web" / "dist"
    assert re.search(r"^WORKDIR /app$", runtime, re.M)
    assert re.findall(r"^COPY --from=(\S+) (\S+) (\S+)$", runtime, re.M) == [
        ("web", "/web/dist", "./web/dist")
    ]
    assert runtime.index("COPY . .") < runtime.index("COPY --from=web") < runtime.index("chown")
    # Unchanged runtime: Python base, port, health check, Gunicorn command.
    assert runtime.startswith("python:3.11-slim AS base")
    assert "EXPOSE 10000" in runtime and "/health" in runtime
    assert "gunicorn --bind 0.0.0.0:${PORT:-10000}" in runtime and "app:app" in runtime
    # Same Node version in the image and in CI.
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    image_node = re.match(r"node:([\d.]+)", web_stage).group(1)
    assert f'node-version: "{image_node}"' in ci


def test_docker_context_excludes_dependencies_builds_and_secrets():
    patterns = [
        line.strip()
        for line in (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    for path in (
        ".env",
        ".env.local",
        "web/.env",
        "web/.env.local",
        "web/node_modules/react/index.js",
        "web/dist/index.html",
        ".git/config",
        ".mypy_cache/3.11/cache.db",  # host tool caches (100+ MB)
        ".ruff_cache/content",
    ):
        assert dockerignored(path, patterns), path
    for path in (
        "web/package.json",
        "web/package-lock.json",
        "web/index.html",
        "web/src/main.tsx",
        "web/tests/unit/sse.test.mjs",  # the build stage runs the unit tests
        "web/public/favicon.svg",
        "app.py",
        "requirements.txt",
        "src/forge/api/web.py",
        "src/forge/templates/index.html",
    ):
        assert not dockerignored(path, patterns), path


# ── Headless browser check (opt-in) ─────────────────────────────────────────

LITERAL = (
    "Act as a senior data engineer.\n",
    "Use user_id_field and src/**/*.py; keep <b>tags</b> & **asterisks** _as typed_.\n",
    "```python\nprint('café ✓')\n```\n",
    "IMPORTANT: copy exactly.",
)


class ScriptedAdapter(FakeAdapter):
    """Fake provider whose behaviour is chosen by markers in the prompt."""

    def __init__(self):
        super().__init__("gemini")
        self.flaky_seen: set[str] = set()

    def stream(self, model, request):
        text = request.messages[-1].content
        with self._lock:
            self.calls.append(("stream", model))
        return self._scripted(text)

    def _scripted(self, text):
        with self._lock:
            self.open_streams += 1
        try:
            if "MARK-ERROR" in text:
                raise errors.ProviderUnavailableError("scripted", provider=self.name)
            if "MARK-FLAKY" in text:
                first = text not in self.flaky_seen
                self.flaky_seen.add(text)
                if first:  # not retried by the router
                    raise errors.AuthenticationError("scripted", provider=self.name)
                yield TextDelta("Recovered after retry.")
            elif "MARK-PARTIAL" in text:
                yield TextDelta("Partial line one.\n")
                yield TextDelta("Partial line two.")
                time.sleep(0.2)
                raise errors.AuthenticationError("scripted", provider=self.name)
            elif "MARK-SLOW" in text:
                for i in range(40):
                    yield TextDelta(f"slow-{i:02d} ")
                    time.sleep(0.2)
            else:
                for chunk in LITERAL:
                    yield TextDelta(chunk)
            yield StreamEnd(None, "stop", None)
        finally:
            with self._lock:
                self.open_streams -= 1


def find_chrome() -> str | None:
    candidates = [
        os.environ.get("FORGE_CHROME"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    return next((c for c in candidates if c and Path(c).is_file()), None)


@pytest.fixture
def live_server() -> Iterator[str]:
    adapter = ScriptedAdapter()
    app = make_app(adapter)

    @app.get("/__test/state")
    def state():  # test-only route: provider streams still open, calls made
        return jsonify({"open_streams": adapter.open_streams, "calls": len(adapter.calls)})

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.mark.skipif(
    os.environ.get("FORGE_BROWSER_TESTS") != "1", reason="set FORGE_BROWSER_TESTS=1 to run"
)
def test_frontend_in_headless_chrome(live_server, tmp_path):
    require_build()
    chrome = find_chrome()
    if chrome is None:
        pytest.skip("no Chrome/Chromium/Edge found (set FORGE_CHROME)")
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    out_dir = os.environ.get("FORGE_BROWSER_OUT") or str(tmp_path)
    result = subprocess.run(
        [node, str(WEB / "tests" / "browser" / "app.browser.mjs"), chrome, live_server, out_dir],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    output = result.stdout + result.stderr
    (Path(out_dir) / "browser.log").write_text(output, encoding="utf-8")
    assert result.returncode == 0, output
    assert re.search(r"^(\d+)/\1 checks passed", output, re.M), output
