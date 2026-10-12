"""/enhance through the provider layer, using fake adapters (no network)."""

import json

import pytest

from forge.app import create_app
from forge.errors import ConfigurationError
from forge.legacy.enhance import LegacyEnhancer
from forge.providers import errors
from forge.providers.config import load_providers_config
from forge.providers.fake import FakeAdapter, FakeResponse
from forge.providers.router import ProviderRouter
from forge.settings import Settings

RAW_UPSTREAM_TEXT = "upstream said: key=AIza-secret-123 internal stack"


def app_with(adapter, sleep=lambda s: None):
    router = ProviderRouter(load_providers_config(), adapters={"gemini": adapter}, sleep=sleep)
    return create_app(Settings(), router=router)


def sse_events(response):
    return [
        json.loads(line[len("data: ") :])
        for line in response.get_data(as_text=True).splitlines()
        if line.startswith("data: ")
    ]


class TestSuccess:
    def test_streaming_frames(self):
        adapter = FakeAdapter("gemini", [FakeResponse(("Act as ", "an expert."))])
        response = app_with(adapter).test_client().post("/enhance", json={"prompt": "p"})
        assert response.status_code == 200
        assert response.mimetype == "text/event-stream"
        assert response.get_data(as_text=True) == (
            'data: {"chunk": "Act as "}\n\n'
            'data: {"chunk": "an expert."}\n\n'
            'data: {"done": true}\n\n'
        )

    def test_streaming_is_not_cleaned_but_json_is(self):
        raw = "[CONFIDENCE] 99%\nBody text"
        client = app_with(FakeAdapter("gemini", default=FakeResponse((raw,)))).test_client()
        assert sse_events(client.post("/enhance", json={"prompt": "p"}))[0] == {"chunk": raw}
        data = client.post("/enhance", json={"prompt": "p", "stream": False}).get_json()
        assert data["enhanced_prompt"] == "Body text"
        assert data["raw"] == raw

    def test_json_fields_unchanged(self):
        adapter = FakeAdapter("gemini", [FakeResponse(("Enhanced.",))])
        data = (
            app_with(adapter)
            .test_client()
            .post("/enhance", json={"prompt": "p", "stream": False})
            .get_json()
        )
        assert data == {
            "success": True,
            "template_id": "",
            "template_name": "",
            "template_matched": "Direct Enhancement",
            "domain": "General",
            "confidence": None,
            "score": None,
            "enhanced_prompt": "Enhanced.",
            "result": "Enhanced.",
            "raw": "Enhanced.",
        }

    def test_legacy_request_reaches_provider(self):
        adapter = FakeAdapter("gemini", [FakeResponse(("x",))])
        app_with(adapter).test_client().post(
            "/enhance", json={"prompt": "Build AWS infra", "stream": False}
        )
        call = adapter.calls[0]
        assert call.model == "gemma-4-31b-it"
        assert call.request.system.startswith("You are FORGE")
        assert "Build AWS infra" in call.request.messages[0].content
        params = call.request.params
        assert (params.temperature, params.top_p, params.max_output_tokens) == (0.5, 0.85, 1280)


ERROR_CASES = [
    (errors.AuthenticationError(RAW_UPSTREAM_TEXT), "rejected the server's credentials"),
    (errors.InvalidRequestError(RAW_UPSTREAM_TEXT), "rejected the request as invalid"),
    (errors.RateLimitError(RAW_UPSTREAM_TEXT, retry_after=999), "rate_limit"),
    (errors.ProviderTimeoutError(RAW_UPSTREAM_TEXT), "timeout"),
    (errors.UpstreamServerError(RAW_UPSTREAM_TEXT), "server error"),
    (errors.MalformedResponseError(RAW_UPSTREAM_TEXT), "invalid response"),
    (errors.UnknownProviderError(RAW_UPSTREAM_TEXT), "failed unexpectedly"),
]


class TestErrors:
    @pytest.mark.parametrize(("error", "expected"), ERROR_CASES)
    def test_streaming_error_frame(self, error, expected):
        adapter = FakeAdapter("gemini", default=error)
        response = app_with(adapter).test_client().post("/enhance", json={"prompt": "p"})
        assert response.status_code == 200
        events = sse_events(response)
        assert len(events) == 1 and set(events[0]) == {"error"}
        assert expected in events[0]["error"]
        assert "AIza-secret-123" not in response.get_data(as_text=True)

    @pytest.mark.parametrize(("error", "expected"), ERROR_CASES)
    def test_json_error_response(self, error, expected):
        adapter = FakeAdapter("gemini", default=error)
        response = (
            app_with(adapter).test_client().post("/enhance", json={"prompt": "p", "stream": False})
        )
        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False and data["template_id"] == "ERROR"
        assert data["confidence"] is None and data["score"] is None  # deprecated
        assert data["enhanced_prompt"].startswith("Error: ") and expected in data["enhanced_prompt"]
        assert "AIza-secret-123" not in response.get_data(as_text=True)

    def test_error_after_partial_stream_keeps_chunks_then_error(self):
        adapter = FakeAdapter(
            "gemini",
            [
                FakeResponse(
                    ("partial",), error_after_chunks=errors.UpstreamServerError(RAW_UPSTREAM_TEXT)
                ),
            ],
        )
        events = sse_events(app_with(adapter).test_client().post("/enhance", json={"prompt": "p"}))
        assert events[0] == {"chunk": "partial"}
        assert set(events[1]) == {"error"} and len(events) == 2
        assert len(adapter.calls) == 1  # not retried after output

    def test_transient_error_is_retried_transparently(self):
        delays = []
        adapter = FakeAdapter("gemini", [errors.UpstreamServerError("x"), FakeResponse(("ok",))])
        events = sse_events(
            app_with(adapter, sleep=delays.append)
            .test_client()
            .post("/enhance", json={"prompt": "p"})
        )
        assert events == [{"chunk": "ok"}, {"done": True}]
        assert len(delays) == 1

    def test_unexpected_internal_error_is_generic(self, monkeypatch):
        app = app_with(FakeAdapter("gemini", default=FakeResponse(("x",))))

        def explode(self, user_prompt):
            raise RuntimeError(RAW_UPSTREAM_TEXT)

        monkeypatch.setattr("forge.legacy.enhance.LegacyEnhancer.stream", explode)
        data = app.test_client().post("/enhance", json={"prompt": "p", "stream": False}).get_json()
        assert (
            data["enhanced_prompt"]
            == "Error: An internal error occurred while enhancing the prompt."
        )


class TestClientDisconnect:
    def test_closing_response_releases_stream_and_slot(self):
        adapter = FakeAdapter("gemini", default=FakeResponse(("a", "b", "c")))
        app = app_with(adapter)
        response = app.test_client().post("/enhance", json={"prompt": "p"}, buffered=False)
        first = next(response.response)
        assert b'"chunk": "a"' in first
        assert adapter.open_streams == 1
        response.close()  # what the WSGI server does when the client goes away
        assert adapter.open_streams == 0
        slots = app.extensions["forge.provider_router"]._slots["gemini"]
        acquired = [slots.acquire(blocking=False) for _ in range(4)]
        assert acquired == [True] * 4  # every slot (max_concurrency=4) is free again
        for _ in acquired:
            slots.release()

    def test_route_closes_stream_explicitly_not_via_garbage_collection(self, monkeypatch):
        # Keep a strong reference to every enhancer stream so CPython's refcounting cannot
        # finalize it; only an explicit close() by the route releases the provider stream.
        kept = []
        original_stream = LegacyEnhancer.stream

        def tracking_stream(self, user_prompt):
            generator = original_stream(self, user_prompt)
            kept.append(generator)
            return generator

        monkeypatch.setattr(LegacyEnhancer, "stream", tracking_stream)
        adapter = FakeAdapter("gemini", default=FakeResponse(("a", "b", "c")))
        response = (
            app_with(adapter).test_client().post("/enhance", json={"prompt": "p"}, buffered=False)
        )
        next(response.response)
        response.close()
        assert len(kept) == 1
        assert adapter.open_streams == 0


class TestInputValidation:
    INVALID = "Invalid request. Send a JSON object with a string 'prompt' field."
    EMPTY = "Empty prompt. Please send a non-empty 'prompt' field."

    @pytest.mark.parametrize(
        "body", [[1, 2], "text", 7, {"prompt": 123}, {"prompt": {"a": 1}}, {"prompt": ["x"]}]
    )
    def test_type_invalid_input_is_400_json_not_500(self, body):
        adapter = FakeAdapter("gemini", default=FakeResponse(("x",)))
        response = app_with(adapter).test_client().post("/enhance", json=body)
        assert response.status_code == 400
        assert response.get_json() == {"error": self.INVALID}
        assert adapter.calls == []

    @pytest.mark.parametrize("body", [{}, {"prompt": None}, {"prompt": "  "}, [], "", 0, False])
    def test_empty_or_falsy_input_keeps_original_message(self, body):
        response = app_with(FakeAdapter("gemini")).test_client().post("/enhance", json=body)
        assert response.status_code == 400
        assert response.get_json() == {"error": self.EMPTY}

    def test_stream_flag_is_interpreted_by_truthiness_as_before(self):
        adapter = FakeAdapter("gemini", default=FakeResponse(("x",)))
        response = (
            app_with(adapter)
            .test_client()
            .post("/enhance", json={"prompt": "p", "stream": "false"})
        )
        assert response.mimetype == "text/event-stream"


class TestConfigDrivenSelection:
    def test_providers_file_selects_fake_provider(self, tmp_path):
        config_file = tmp_path / "providers.json"
        config_file.write_text(
            json.dumps(
                {
                    "default_model": "offline",
                    "providers": {"local": {"type": "fake", "fake_response": "from config"}},
                    "models": {"offline": {"provider": "local", "model": "fake-model-1"}},
                }
            )
        )
        app = create_app(Settings.from_env({"FORGE_PROVIDERS_FILE": str(config_file)}))
        client = app.test_client()
        assert client.get("/health").get_json()["model"] == "fake-model-1"
        assert sse_events(client.post("/enhance", json={"prompt": "p"})) == [
            {"chunk": "from config"},
            {"done": True},
        ]

    def test_invalid_providers_file_fails_at_startup(self, tmp_path):
        config_file = tmp_path / "providers.json"
        config_file.write_text('{"default_model": "x"}')
        with pytest.raises(ConfigurationError, match="Invalid provider configuration"):
            create_app(Settings.from_env({"FORGE_PROVIDERS_FILE": str(config_file)}))
