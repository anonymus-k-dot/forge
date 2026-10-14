"""The legacy UI (src/forge/templates/index.html).

Behaviour is tested by running the template's real application script under Node with a
fake DOM (tests/frontend/): literal output, copying, errors, states, cancellation, the
shortcuts dialog and the copy menu. These Python tests run those suites, replay real
Flask /enhance streams (fake provider, no network) into the UI, and check static properties
of the template (contrast, removed behaviours, ids the script needs).
"""

import base64
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from forge.app import create_app
from forge.providers import errors
from forge.providers.config import load_providers_config
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from forge.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND = REPO_ROOT / "tests" / "frontend"
HARNESS = FRONTEND / "legacy_ui_export.mjs"
TEMPLATE = REPO_ROOT / "src" / "forge" / "templates" / "index.html"


def node_or_skip() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed; the UI behavior tests need it")
    return node


def run_node(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [node_or_skip(), *args], capture_output=True, text=True, encoding="utf-8", timeout=120
    )


def app_script() -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r'<script data-forge="app">(.*?)</script>', html, re.S)
    assert match, "application script not found"
    return match.group(1)


# ── Node suites ─────────────────────────────────────────────────────────────


def test_copy_as_json_exports_enhanced_prompt_without_fabricated_metrics():
    result = run_node(str(HARNESS), str(TEMPLATE))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS legacy UI export" in result.stdout


def test_behaviour_suite():
    result = run_node("--test", str(FRONTEND / "legacy_ui_behavior.test.mjs"))
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    passed = re.search(r"(?:ℹ|#) pass (\d+)", output)
    failed = re.search(r"(?:ℹ|#) fail (\d+)", output)
    assert passed and int(passed.group(1)) >= 25, output
    assert failed and failed.group(1) == "0", output


# ── Real Flask streams replayed into the UI ───────────────────────────────────


def app_with(adapter):
    router = ProviderRouter(
        load_providers_config(), adapters={"gemini": adapter}, sleep=lambda s: 0
    )
    return create_app(Settings(), router=router)


def replay(tmp_path, body: bytes, expected_text=None, expected_error=None, piece=5):
    scenario = {
        "pieces_b64": [
            base64.b64encode(body[i : i + piece]).decode() for i in range(0, len(body), piece)
        ],
        "expected_text": expected_text,
        "expected_error": expected_error,
    }
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    result = run_node(str(FRONTEND / "legacy_ui_replay.mjs"), str(TEMPLATE), str(path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS legacy UI replay" in result.stdout


LITERAL_CHUNKS = (
    "Act as a data engineer.\n",
    "Use user_id_field and src/**/*.py; keep <b>tags</b> & **asterisks**.\n",
    "```python\nprint('café ✓')\n```\n  ",
)


def test_flask_stream_is_displayed_literally_and_copied_identically(tmp_path):
    adapter = FakeAdapter("gemini", [FakeResponse(LITERAL_CHUNKS)])
    response = app_with(adapter).test_client().post("/enhance", json={"prompt": "p"})
    assert response.status_code == 200 and response.mimetype == "text/event-stream"
    replay(tmp_path, response.get_data(), expected_text="".join(LITERAL_CHUNKS).strip())


ERRORS = [
    errors.RateLimitError("x"),
    errors.ProviderTimeoutError("x"),
    errors.ProviderUnavailableError("x"),
    errors.UpstreamServerError("x"),
    errors.AuthenticationError("x"),
    errors.InvalidRequestError("x"),
    errors.MalformedResponseError("x"),
    errors.UnknownProviderError("x"),
]


@pytest.mark.parametrize("error", ERRORS, ids=lambda e: type(e).__name__)
def test_flask_error_frame_is_shown_verbatim(tmp_path, error):
    adapter = FakeAdapter("gemini", default=error)
    body = app_with(adapter).test_client().post("/enhance", json={"prompt": "p"}).get_data()
    (frame,) = (
        json.loads(line[6:]) for line in body.decode().splitlines() if line.startswith("data: ")
    )
    assert frame["error"] == error.safe_message
    replay(tmp_path, body, expected_error=error.safe_message)


def test_flask_error_after_partial_output(tmp_path):
    adapter = FakeAdapter(
        "gemini",
        [FakeResponse(("partial",), error_after_chunks=errors.UpstreamServerError("x"))],
    )
    body = app_with(adapter).test_client().post("/enhance", json={"prompt": "p"}).get_data()
    replay(tmp_path, body, expected_error=errors.UpstreamServerError("x").safe_message)


# ── Static properties of the template ─────────────────────────────────────────


def test_template_has_no_fabricated_metric_literals():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '"98%"' not in html
    assert not re.search(r"score\s*:\s*0\.98", html)  # (CSS uses scale(0.98) legitimately)
    assert "defaultMeta" not in html


def test_removed_behaviours_stay_removed():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "innerHTML" not in html  # model output is only ever assigned as text
    assert "cursor: none" not in html and "custom-cursor-dot" not in html  # native cursor
    assert "autosave" not in html  # no fake "Saved" indicator
    assert "SILENT" not in html  # stale footer text
    script = app_script()
    assert not re.search(r"""key(?:\.toLowerCase\(\))?\s*===\s*["']c["']""", script)  # no Ctrl+C
    assert "Plain Text" not in html and 'data-format="markdown"' not in html  # duplicate copy


def test_every_element_the_script_uses_exists_in_the_template():
    html = TEMPLATE.read_text(encoding="utf-8")
    ids = set(re.findall(r'\$\("([a-z0-9-]+)"\)', app_script()))
    created = {"output-text", "error-message", "error-retry"}  # created by the script
    assert ids - created, "no ids found"
    missing = [i for i in sorted(ids - created) if f'id="{i}"' not in html]
    assert not missing, missing


def test_dialog_and_menu_markup():
    html = TEMPLATE.read_text(encoding="utf-8")
    dialog = re.search(r'<dialog id="shortcuts-modal"[^>]*>', html).group(0)
    assert 'aria-labelledby="shortcuts-title"' in dialog
    assert "</dialog>" in html and 'role="dialog"' not in html  # native element, implicit role
    assert "modal.showModal()" in app_script()  # modal: the rest of the page becomes inert
    trigger = re.search(r'<button[^>]*id="shortcuts-trigger"[^>]*>', html).group(0)
    assert 'aria-haspopup="dialog"' in trigger and 'aria-expanded="false"' in trigger
    copy = re.search(r'<button[^>]*id="copy-btn"[^>]*>', html).group(0)
    assert 'aria-haspopup="menu"' in copy and 'aria-expanded="false"' in copy
    # Closed menu uses the hidden attribute (display: none), not a visibility transition,
    # which in Chrome left the first item unfocusable when the menu opened.
    menu = re.search(r'<div id="copy-menu"[^>]*>', html).group(0)
    assert " hidden>" in menu
    assert "copyMenu.hidden = false" in app_script()
    # The script runs after parsing (some elements it uses come after it in the page).
    assert 'addEventListener("DOMContentLoaded", forgeApp)' in app_script()
    assert re.search(r'id="sr-status"[^>]*role="status"[^>]*aria-live="polite"', html)


def test_dialog_scrolls_instead_of_clipping_on_short_viewports():
    # A flex-centred panel taller than the viewport (400% zoom, small phones) overflows
    # upwards, out of scroll reach: in Chrome at 320x256 the title and close button were
    # cut off. Auto margins centre it without that overflow.
    html = TEMPLATE.read_text(encoding="utf-8")
    modal = re.search(r"\n    \.shortcuts-modal \{(.*?)\}", html, re.S).group(1)
    panel = re.search(r"\n    \.shortcuts-panel \{(.*?)\}", html, re.S).group(1)
    assert "align-items: center" not in modal and "justify-content: center" not in modal
    assert "overflow: auto" in modal
    assert re.search(r"margin:\s*auto", panel)


# ── Contrast (WCAG 2.x relative luminance) ────────────────────────────────────


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


def css_variable(html: str, name: str) -> str:
    return re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", html).group(1)


def test_text_contrast_meets_wcag_aa():
    html = TEMPLATE.read_text(encoding="utf-8")
    label = css_variable(html, "label")
    assert re.search(rf'"on-surface-muted":\s*"{label}"', html), "Tailwind muted text = --label"
    surfaces = {
        "page": css_variable(html, "surface-page"),
        "card": css_variable(html, "surface-card"),
        "elevated": css_variable(html, "surface-elevated"),
        "chip hover": "#1c1c24",
    }
    pairs = [(f"muted text on {name}", label, bg) for name, bg in surfaces.items()]
    pairs += [
        ("counter warning on card", "#fbbf24", surfaces["card"]),
        ("counter error on card", "#f87171", surfaces["card"]),
        ("partial-output notice", "#fbbf24", surfaces["elevated"]),
        ("error description", "#e4e4e7", "#1a0f0f"),
        ("output text", "#e4e4e7", surfaces["card"]),
        ("accent on page", css_variable(html, "accent"), surfaces["page"]),
    ]
    failing = {name: round(contrast(fg, bg), 2) for name, fg, bg in pairs if contrast(fg, bg) < 4.5}
    assert not failing, failing
    for color in ("#fbbf24", "#f87171", "#e4e4e7"):  # the colours checked above are the ones used
        assert color in html
    assert "#raw-input::placeholder" in html and "placeholder:text-white/20" not in html
    assert 'style="opacity:.6"' not in html
