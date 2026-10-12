"""Tests for the src/forge package structure, app factory, and the root entry point."""

import json
import os
import subprocess
import sys
from importlib import resources
from pathlib import Path

import pytest
from flask import Flask

import forge
from forge.app import create_app
from forge.errors import ConfigurationError
from forge.providers import google_genai
from forge.settings import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_HEALTH = {"status": "ok", "templates_loaded": 0, "model": "gemma-4-31b-it"}


@pytest.fixture
def keyless_client(monkeypatch):
    """App built with no API key; constructing a GenAI client fails the test."""

    def forbidden_client(*args, **kwargs):
        raise AssertionError("google.genai.Client must not be constructed")

    monkeypatch.setattr(google_genai.genai, "Client", forbidden_client)
    return create_app(Settings()).test_client()


class TestPackage:
    def test_version_is_exposed(self):
        assert isinstance(forge.__version__, str) and forge.__version__

    def test_template_is_package_data(self):
        template = resources.files("forge").joinpath("templates/index.html")
        assert template.is_file()
        assert b"<!DOCTYPE html>" in template.read_bytes()


class TestSettings:
    def test_from_explicit_environ(self):
        settings = Settings.from_env({"GEMINI_API_KEY": "k", "FORGE_PROVIDERS_FILE": "p.json"})
        assert settings.get_secret("GEMINI_API_KEY") == "k"
        assert settings.providers_file == "p.json"

    @pytest.mark.parametrize("environ", [{}, {"GEMINI_API_KEY": ""}, {"GEMINI_API_KEY": "  "}])
    def test_missing_or_blank_key_is_none(self, environ):
        assert Settings.from_env(environ).get_secret("GEMINI_API_KEY") is None

    def test_secrets_not_in_repr(self):
        settings = Settings.from_env({"GEMINI_API_KEY": "super-secret-value"})
        assert "super-secret-value" not in repr(settings)


class TestAppFactoryWithoutApiKey:
    def test_create_app_returns_flask_app(self):
        assert isinstance(create_app(Settings()), Flask)

    def test_health(self, keyless_client):
        response = keyless_client.get("/health")
        assert response.status_code == 200
        assert response.get_json() == EXPECTED_HEALTH

    def test_home_page(self, keyless_client):
        response = keyless_client.get("/")
        assert response.status_code == 200
        assert b"FORGE" in response.data

    def test_empty_prompt_still_400(self, keyless_client):
        response = keyless_client.post("/enhance", json={})
        assert response.status_code == 400

    def test_enhance_non_streaming_reports_missing_key(self, keyless_client):
        response = keyless_client.post("/enhance", json={"prompt": "x", "stream": False})
        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False
        assert data["template_id"] == "ERROR"
        assert "GEMINI_API_KEY is not set" in data["enhanced_prompt"]

    def test_enhance_streaming_reports_missing_key(self, keyless_client):
        response = keyless_client.post("/enhance", json={"prompt": "x", "stream": True})
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["Content-Type"]
        events = [
            json.loads(line[len("data: ") :])
            for line in response.data.decode().splitlines()
            if line.startswith("data: ")
        ]
        assert len(events) == 1
        assert "GEMINI_API_KEY is not set" in events[0]["error"]

    def test_client_access_raises_configuration_error(self):
        adapter = google_genai.GoogleGenAIAdapter(
            "gemini", api_key_env="GEMINI_API_KEY", get_secret=lambda _: None, timeout_seconds=1
        )
        with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is not set"):
            adapter.client


def _run_python(code: str, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run code in a fresh interpreter with no GEMINI_API_KEY and no reachable .env file."""
    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT), str(REPO_ROOT / "src")])
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestRootEntryPoint:
    def test_import_and_health_without_api_key(self, tmp_path):
        code = (
            "import json, app\n"
            "from flask import Flask\n"
            "assert isinstance(app.app, Flask)\n"
            "r = app.app.test_client().get('/health')\n"
            "print(json.dumps({'status': r.status_code, 'body': r.get_json(),\n"
            "    'client_created': 'gemini' in app._router()._adapters}))\n"
        )
        result = _run_python(code, tmp_path)
        assert result.returncode == 0, result.stderr
        output = json.loads(result.stdout.strip().splitlines()[-1])
        assert output == {"status": 200, "body": EXPECTED_HEALTH, "client_created": False}

    def test_legacy_names_are_reexported(self):
        import app as root_app

        for name in ("app", "GEMMA_MODEL", "build_forge_prompt", "_clean_output", "enhance_prompt"):
            assert hasattr(root_app, name), name

    def test_gunicorn_loads_app_app(self, monkeypatch):
        try:
            from gunicorn.util import import_app
        except ImportError as exc:  # gunicorn imports fcntl, which is POSIX-only
            pytest.skip(f"gunicorn loader unavailable on this platform: {exc}")
        monkeypatch.chdir(REPO_ROOT)
        assert isinstance(import_app("app:app"), Flask)
