"""Request IDs and structured logging."""

import io
import json
import logging
import re

import pytest

from forge.app import create_app
from forge.errors import ConfigurationError
from forge.logging import configure_logging, incoming_request_id
from forge.providers import errors
from forge.providers.config import load_providers_config
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from forge.settings import Settings

SECRET = "AIza-observability-secret-value"
PROMPT_MARKER = "CONFIDENTIAL-PROMPT-MARKER-7731"
OUTPUT_MARKER = "MODEL-OUTPUT-MARKER-9054"
GENERATED_ID = re.compile(r"^[0-9a-f]{32}$")


@pytest.fixture
def log_stream():
    stream = io.StringIO()
    yield stream
    configure_logging("INFO")  # restore the default stderr handler for other tests


def make_app(log_stream, script=(), default=None, level="INFO"):
    adapter = FakeAdapter("gemini", list(script), default=default)
    router = ProviderRouter(
        load_providers_config(), adapters={"gemini": adapter}, sleep=lambda s: None
    )
    app = create_app(Settings(environ={"GEMINI_API_KEY": SECRET}, log_level=level), router=router)
    configure_logging(level, stream=log_stream)
    return app


def records(log_stream):
    return [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]


class TestRequestIds:
    @pytest.mark.parametrize(
        ("method", "path", "body", "status"),
        [
            ("GET", "/health", None, 200),
            ("GET", "/", None, 200),
            ("POST", "/enhance", {}, 400),
            ("GET", "/enhance", None, 405),
            ("GET", "/missing", None, 404),
            ("POST", "/enhance", {"prompt": "p", "stream": False}, 200),
            ("POST", "/enhance", {"prompt": "p"}, 200),
        ],
    )
    def test_every_response_has_a_generated_id(self, log_stream, method, path, body, status):
        client = make_app(log_stream, default=FakeResponse(("ok",))).test_client()
        response = client.open(path, method=method, json=body)
        assert response.status_code == status
        assert GENERATED_ID.match(response.headers["X-Request-ID"])

    def test_ids_are_unique(self, log_stream):
        client = make_app(log_stream).test_client()
        ids = {client.get("/health").headers["X-Request-ID"] for _ in range(20)}
        assert len(ids) == 20

    def test_well_formed_client_id_is_echoed(self, log_stream):
        client = make_app(log_stream).test_client()
        response = client.get("/health", headers={"X-Request-ID": "trace-abc_123.4"})
        assert response.headers["X-Request-ID"] == "trace-abc_123.4"

    @pytest.mark.parametrize(
        "bad",
        ["", "has space", "x" * 129, "semi;colon", "ünicode", 'quote"d'],
    )
    def test_malformed_client_id_is_replaced(self, bad):
        assert GENERATED_ID.match(incoming_request_id(bad))

    def test_id_appears_in_logs_for_the_request(self, log_stream):
        client = make_app(log_stream, default=FakeResponse(("ok",))).test_client()
        response = client.post(
            "/enhance", json={"prompt": "p", "stream": False}, headers={"X-Request-ID": "req-42"}
        )
        assert response.headers["X-Request-ID"] == "req-42"
        completed = [r for r in records(log_stream) if r["event"] == "request.completed"]
        assert completed[-1]["request_id"] == "req-42"
        assert completed[-1]["path"] == "/enhance" and completed[-1]["status"] == 200

    def test_response_body_contract_is_unchanged(self, log_stream):
        client = make_app(log_stream, default=FakeResponse(("ok",))).test_client()
        body = client.post("/enhance", json={"prompt": "p"}).get_data(as_text=True)
        assert body == 'data: {"chunk": "ok"}\n\ndata: {"done": true}\n\n'


class TestStructuredLogs:
    def test_lines_are_json_with_required_fields(self, log_stream):
        make_app(log_stream).test_client().get("/health")
        (entry,) = records(log_stream)
        assert {"ts", "level", "logger", "event", "request_id"} <= set(entry)
        assert entry["event"] == "request.completed"
        assert entry["method"] == "GET" and entry["status"] == 200
        assert isinstance(entry["duration_ms"], float)

    @pytest.mark.parametrize("stream", [True, False])
    def test_no_prompt_output_or_secret_in_logs(self, log_stream, stream):
        app = make_app(
            log_stream,
            script=[
                errors.UpstreamServerError(f"upstream says {OUTPUT_MARKER} {SECRET}"),
                FakeResponse((f"{OUTPUT_MARKER} result",)),
            ],
        )
        app.test_client().post("/enhance", json={"prompt": PROMPT_MARKER, "stream": stream})
        logged = log_stream.getvalue()
        assert "provider.retry" in logged  # something was logged on this path
        for forbidden in (PROMPT_MARKER, OUTPUT_MARKER, SECRET):
            assert forbidden not in logged

    def test_provider_retry_event_is_structured(self, log_stream):
        app = make_app(
            log_stream,
            script=[
                errors.RateLimitError("429", status_code=429, retry_after=2.0),
                FakeResponse(("ok",)),
            ],
        )
        app.test_client().post("/enhance", json={"prompt": "p", "stream": False})
        (retry,) = (r for r in records(log_stream) if r["event"] == "provider.retry")
        assert retry["level"] == "WARNING"
        assert retry["provider"] == "gemini" and retry["category"] == "rate_limit"
        assert retry["attempt"] == 1 and retry["delay_seconds"] == 2.0
        assert retry["request_id"]

    def test_failure_is_logged_by_category_only(self, log_stream):
        app = make_app(
            log_stream, default=errors.AuthenticationError(f"bad key {SECRET}", status_code=401)
        )
        response = app.test_client().post("/enhance", json={"prompt": PROMPT_MARKER})
        (failed,) = (r for r in records(log_stream) if r["event"] == "enhance.failed")
        assert failed["category"] == "authentication" and failed["status_code"] == 401
        assert failed["request_id"] == response.headers["X-Request-ID"]
        assert SECRET not in log_stream.getvalue()

    def test_level_filters_info(self, log_stream):
        make_app(log_stream, level="WARNING").test_client().get("/health")
        assert records(log_stream) == []

    def test_only_forge_logger_is_configured(self, log_stream):
        make_app(log_stream)
        assert logging.getLogger("forge").propagate is False
        assert not any(getattr(h, "_forge_handler", False) for h in logging.getLogger().handlers)

    def test_repeated_configuration_does_not_duplicate_handlers(self, log_stream):
        for _ in range(3):
            make_app(log_stream)
        marked = [
            h for h in logging.getLogger("forge").handlers if getattr(h, "_forge_handler", False)
        ]
        assert len(marked) == 1


class TestLogLevelSetting:
    def test_default_and_case_insensitive(self):
        assert Settings.from_env({}).log_level == "INFO"
        assert Settings.from_env({"FORGE_LOG_LEVEL": "debug"}).log_level == "DEBUG"

    def test_invalid_level_is_a_configuration_error(self):
        with pytest.raises(ConfigurationError, match="FORGE_LOG_LEVEL"):
            Settings.from_env({"FORGE_LOG_LEVEL": "LOUD"})
