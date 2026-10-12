"""Runs the legacy UI's real inline script under Node (see tests/frontend/legacy_ui_export.mjs)."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "tests" / "frontend" / "legacy_ui_export.mjs"
TEMPLATE = REPO_ROOT / "src" / "forge" / "templates" / "index.html"


def test_copy_as_json_exports_enhanced_prompt_without_fabricated_metrics():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed; the UI behavior test needs it")
    result = subprocess.run(
        [node, str(HARNESS), str(TEMPLATE)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS legacy UI export" in result.stdout


def test_template_has_no_fabricated_metric_literals():
    html = TEMPLATE.read_text(encoding="utf-8")
    assert '"98%"' not in html
    assert not re.search(r"score\s*:\s*0\.98", html)  # (CSS uses scale(0.98) legitimately)
    assert "defaultMeta" not in html
