import json
from types import SimpleNamespace

import pytest
import requests
from google.genai import errors as genai_errors, types

from forge.legacy.enhance import _FORGE_ROLE, build_forge_prompt, build_request
from forge.providers import errors
from forge.providers.base import (
    GenerationParams,
    GenerationRequest,
    Message,
    StreamEnd,
    TextDelta,
    Usage,
)
from forge.providers.google_genai import GoogleGenAIAdapter

SECRET = "AIza-test-secret-value-000"


class StubModels:
    def __init__(self, response=None, chunks=(), error=None):
        self.response, self.chunks, self.error = response, list(chunks), error
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(("generate_content", kwargs))
        if self.error:
            raise self.error
        return self.response

    def generate_content_stream(self, **kwargs):
        self.calls.append(("generate_content_stream", kwargs))
        if self.error:
            raise self.error
        return iter(self.chunks)


def make_adapter(models=None, secret=SECRET):
    adapter = GoogleGenAIAdapter(
        "gemini",
        api_key_env="GEMINI_API_KEY",
        get_secret={"GEMINI_API_KEY": secret}.get,
        timeout_seconds=60,
    )
    if models is not None:
        adapter._client = SimpleNamespace(models=models)
    return adapter


def chunk(text=None, *, finish=None, usage=None, model_version=None):
    candidates = [SimpleNamespace(finish_reason=SimpleNamespace(value=finish))] if finish else None
    return SimpleNamespace(
        text=text, candidates=candidates, usage_metadata=usage, model_version=model_version
    )


def api_error(status, body, headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(body).encode()
    response.headers.update(headers or {})
    cls = genai_errors.ClientError if status < 500 else genai_errors.ServerError
    return cls(status, response)


class TestClientLifecycle:
    def test_client_is_created_lazily_with_key_and_timeout(self, monkeypatch):
        created = []
        monkeypatch.setattr(
            "forge.providers.google_genai.genai.Client",
            lambda **kwargs: created.append(kwargs) or SimpleNamespace(models=None),
        )
        adapter = make_adapter()
        assert created == []
        adapter.client
        adapter.client
        assert len(created) == 1
        assert created[0]["api_key"] == SECRET
        assert created[0]["http_options"].timeout == 60_000  # milliseconds

    def test_missing_credentials(self):
        adapter = make_adapter(secret=None)
        with pytest.raises(errors.ProviderConfigurationError, match="GEMINI_API_KEY is not set"):
            list(adapter.stream("m", GenerationRequest.from_prompt("x")))


class TestLegacyEquivalence:
    def test_config_matches_original_llm_config(self):
        original = types.GenerateContentConfig(
            system_instruction=_FORGE_ROLE, temperature=0.5, top_p=0.85, max_output_tokens=1280
        )
        built = make_adapter().build_config(build_request("Build AWS infra"))
        assert built.model_dump() == original.model_dump()

    def test_single_prompt_is_sent_as_plain_string(self):
        models = StubModels(chunks=[chunk("x")])
        list(make_adapter(models).stream("gemma-4-31b-it", build_request("Build AWS infra")))
        _, kwargs = models.calls[0]
        assert kwargs["model"] == "gemma-4-31b-it"
        assert kwargs["contents"] == build_forge_prompt("Build AWS infra")

    def test_multi_turn_messages_become_contents(self):
        request = GenerationRequest(messages=(Message("user", "a"), Message("assistant", "b")))
        contents = GoogleGenAIAdapter.build_contents(request)
        assert [c.role for c in contents] == ["user", "model"]


class TestNormalization:
    def test_generate(self):
        usage = SimpleNamespace(prompt_token_count=11, candidates_token_count=7)
        response = SimpleNamespace(
            text="hello",
            candidates=[SimpleNamespace(finish_reason="STOP")],
            usage_metadata=usage,
            model_version="gemma-4-31b-it-001",
        )
        models = StubModels(response=response)
        request = GenerationRequest.from_prompt("q", params=GenerationParams(seed=3))
        result = make_adapter(models).generate("gemma-4-31b-it", request)
        assert (result.provider, result.model, result.text) == ("gemini", "gemma-4-31b-it", "hello")
        assert result.usage == Usage(11, 7)
        assert result.reported_model == "gemma-4-31b-it-001"
        assert result.finish_reason == "STOP"
        assert models.calls[0][1]["config"].seed == 3

    def test_generate_without_text_or_usage(self):
        response = SimpleNamespace(
            text=None, candidates=None, usage_metadata=None, model_version=None
        )
        result = make_adapter(StubModels(response=response)).generate(
            "m", GenerationRequest.from_prompt("q")
        )
        assert result.text == "" and result.usage is None

    def test_stream(self):
        usage = SimpleNamespace(prompt_token_count=5, candidates_token_count=None)
        models = StubModels(
            chunks=[
                chunk("Act "),
                chunk(None),
                chunk(""),
                chunk("now.", finish="STOP", usage=usage, model_version="v1"),
            ]
        )
        events = list(make_adapter(models).stream("m", GenerationRequest.from_prompt("q")))
        assert events == [
            TextDelta("Act "),
            TextDelta("now."),
            StreamEnd(reported_model="v1", finish_reason="STOP", usage=Usage(5, None)),
        ]


class TestErrors:
    @pytest.mark.parametrize(
        ("error", "cls"),
        [
            (
                api_error(401, {"error": {"code": 401, "status": "UNAUTHENTICATED"}}),
                errors.AuthenticationError,
            ),
            (
                api_error(403, {"error": {"code": 403, "status": "PERMISSION_DENIED"}}),
                errors.AuthenticationError,
            ),
            (
                api_error(
                    400,
                    {
                        "error": {
                            "code": 400,
                            "status": "INVALID_ARGUMENT",
                            "message": f"API key not valid {SECRET}",
                            "details": [{"reason": "API_KEY_INVALID"}],
                        }
                    },
                ),
                errors.AuthenticationError,
            ),
            (
                api_error(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT"}}),
                errors.InvalidRequestError,
            ),
            (
                api_error(404, {"error": {"code": 404, "status": "NOT_FOUND"}}),
                errors.InvalidRequestError,
            ),
            (
                api_error(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}),
                errors.RateLimitError,
            ),
            (
                api_error(500, {"error": {"code": 500, "status": "INTERNAL"}}),
                errors.UpstreamServerError,
            ),
            (
                api_error(503, {"error": {"code": 503, "status": "UNAVAILABLE"}}),
                errors.ProviderUnavailableError,
            ),
            (requests.exceptions.ReadTimeout("read timed out"), errors.ProviderTimeoutError),
            (requests.exceptions.ConnectTimeout("connect timed out"), errors.ProviderTimeoutError),
            (requests.exceptions.ConnectionError("refused"), errors.ProviderUnavailableError),
            (TimeoutError("t"), errors.ProviderTimeoutError),
            (ValueError(f"weird {SECRET}"), errors.UnknownProviderError),
        ],
    )
    @pytest.mark.parametrize("method", ["generate", "stream"])
    def test_classification(self, error, cls, method):
        adapter = make_adapter(StubModels(error=error))
        request = GenerationRequest.from_prompt("q")
        with pytest.raises(cls) as info:
            adapter.generate("m", request) if method == "generate" else list(
                adapter.stream("m", request)
            )
        assert info.value.__cause__ is error
        assert SECRET not in str(info.value)
        assert SECRET not in info.value.safe_message

    def test_retry_after_header(self):
        error = api_error(429, {"error": {"code": 429}}, headers={"Retry-After": "12"})
        assert make_adapter().normalize_error(error).retry_after == 12.0

    def test_retry_info_delay(self):
        body = {
            "error": {
                "code": 429,
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"}
                ],
            }
        }
        assert make_adapter().normalize_error(api_error(429, body)).retry_after == 37.0

    def test_mid_stream_failure_after_output(self):
        def chunks():
            yield chunk("partial")
            raise requests.exceptions.ConnectionError("dropped")

        models = StubModels()
        models.generate_content_stream = lambda **kwargs: chunks()
        stream = make_adapter(models).stream("m", GenerationRequest.from_prompt("q"))
        assert next(stream) == TextDelta("partial")
        with pytest.raises(errors.ProviderUnavailableError):
            next(stream)

    def test_closing_stream_closes_sdk_iterator(self):
        closed = []

        def chunks():
            try:
                yield chunk("a")
                yield chunk("b")
            finally:
                closed.append(True)

        models = StubModels()
        models.generate_content_stream = lambda **kwargs: chunks()
        stream = make_adapter(models).stream("m", GenerationRequest.from_prompt("q"))
        next(stream)
        stream.close()
        assert closed == [True]
