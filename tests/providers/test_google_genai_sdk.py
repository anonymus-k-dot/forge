"""Google adapter driven through the real google-genai SDK, with HTTP intercepted.

The SDK (1.x) sends every request through ``requests.Session.request``; replacing that
method exercises the SDK's own request building, SSE parsing and error raising without any
network access.
"""

import io
import json

import pytest
import requests
from google import genai
from google.genai import types

from forge.legacy.enhance import _FORGE_ROLE, build_forge_prompt, build_request
from forge.providers import errors
from forge.providers.base import StreamEnd, TextDelta, Usage
from forge.providers.google_genai import GoogleGenAIAdapter

MODEL = "gemma-4-31b-it"


class FakeHttp:
    """Records requests made by the SDK and answers with a scripted response."""

    def __init__(self, monkeypatch, status=200, body=b"", headers=None, exc=None):
        self.calls = []
        self.status, self.body, self.headers, self.exc = status, body, headers or {}, exc
        monkeypatch.setattr(requests.Session, "request", self._request)

    # Installed on the class as a bound method, so the Session instance is not passed.
    def _request(self, method, url, headers=None, data=None, timeout=None, stream=False, **_):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "body": json.loads(data) if data else None,
                "timeout": timeout,
            }
        )
        if self.exc is not None:
            raise self.exc
        response = requests.Response()
        response.status_code = self.status
        response.headers.update(self.headers)
        response.encoding = "utf-8"
        if stream:
            response.raw = io.BytesIO(self.body)
        else:
            response._content = self.body
        return response


def candidate_chunk(text, finish=None, usage=None):
    chunk = {
        "candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}],
        "modelVersion": MODEL,
    }
    if finish:
        chunk["candidates"][0]["finishReason"] = finish
    if usage:
        chunk["usageMetadata"] = usage
    return chunk


def sse_body(*chunks):
    return b"".join(b"data: " + json.dumps(c).encode() + b"\r\n\r\n" for c in chunks)


@pytest.fixture
def adapter():
    return GoogleGenAIAdapter(
        "gemini",
        api_key_env="GEMINI_API_KEY",
        get_secret=lambda _: "dummy-key-no-network",
        timeout_seconds=60,
    )


def test_wire_request_matches_original_forge_call(monkeypatch, adapter):
    http = FakeHttp(monkeypatch, body=sse_body(candidate_chunk("x", "STOP")))
    # The original FORGE 1.x call, reproduced literally.
    original = genai.Client(api_key="dummy-key-no-network")
    list(
        original.models.generate_content_stream(
            model=MODEL,
            contents=build_forge_prompt("Build AWS infra"),
            config=types.GenerateContentConfig(
                system_instruction=_FORGE_ROLE, temperature=0.5, top_p=0.85, max_output_tokens=1280
            ),
        )
    )
    list(adapter.stream(MODEL, build_request("Build AWS infra")))
    before, after = http.calls
    assert after["url"] == before["url"]
    assert after["url"].endswith(f"/v1beta/models/{MODEL}:streamGenerateContent?alt=sse")
    assert after["body"] == before["body"]
    assert after["body"]["generationConfig"] == {
        "temperature": 0.5,
        "topP": 0.85,
        "maxOutputTokens": 1280,
    }
    # Only intended difference: a request timeout (seconds) where the original had none.
    assert (before["timeout"], after["timeout"]) == (None, 60.0)


def test_stream_through_sdk(monkeypatch, adapter):
    FakeHttp(
        monkeypatch,
        body=sse_body(
            candidate_chunk("Act as "),
            candidate_chunk(
                "an expert.", "STOP", {"promptTokenCount": 11, "candidatesTokenCount": 4}
            ),
        ),
    )
    assert list(adapter.stream(MODEL, build_request("x"))) == [
        TextDelta("Act as "),
        TextDelta("an expert."),
        StreamEnd(reported_model=MODEL, finish_reason="STOP", usage=Usage(11, 4)),
    ]


def test_generate_through_sdk(monkeypatch, adapter):
    FakeHttp(
        monkeypatch,
        body=json.dumps(
            candidate_chunk("whole", "STOP", {"promptTokenCount": 3, "candidatesTokenCount": 1})
        ).encode(),
    )
    result = adapter.generate(MODEL, build_request("x"))
    assert (result.text, result.finish_reason, result.usage) == ("whole", "STOP", Usage(3, 1))


def test_non_text_part_is_normalized(monkeypatch, adapter):
    body = {
        "candidates": [
            {"content": {"role": "model", "parts": [{"functionCall": {"name": "f", "args": {}}}]}}
        ]
    }
    FakeHttp(monkeypatch, body=json.dumps(body).encode())
    try:
        result = adapter.generate(MODEL, build_request("x"))
    except errors.ProviderError as exc:
        assert isinstance(exc, errors.UnknownProviderError)
    else:  # SDK versions that return None for non-text parts
        assert result.text == ""


@pytest.mark.parametrize("method", ["stream", "generate"])
@pytest.mark.parametrize(
    ("status", "body", "headers", "cls", "retry_after"),
    [
        (
            429,
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [
                        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"}
                    ],
                }
            },
            {},
            errors.RateLimitError,
            7.0,
        ),
        (
            400,
            {
                "error": {
                    "code": 400,
                    "status": "INVALID_ARGUMENT",
                    "message": "API key not valid",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                            "reason": "API_KEY_INVALID",
                        }
                    ],
                }
            },
            {},
            errors.AuthenticationError,
            None,
        ),
        (
            400,
            {"error": {"code": 400, "status": "INVALID_ARGUMENT"}},
            {},
            errors.InvalidRequestError,
            None,
        ),
        (
            403,
            {"error": {"code": 403, "status": "PERMISSION_DENIED"}},
            {},
            errors.AuthenticationError,
            None,
        ),
        (
            503,
            {"error": {"code": 503, "status": "UNAVAILABLE"}},
            {"Retry-After": "3"},
            errors.ProviderUnavailableError,
            3.0,
        ),
        (500, b"<html>gateway</html>", {}, errors.UpstreamServerError, None),
    ],
)
def test_http_errors_through_sdk(
    monkeypatch, adapter, method, status, body, headers, cls, retry_after
):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    FakeHttp(monkeypatch, status=status, body=raw, headers=headers)
    with pytest.raises(cls) as info:
        if method == "stream":
            list(adapter.stream(MODEL, build_request("x")))
        else:
            adapter.generate(MODEL, build_request("x"))
    assert info.value.retry_after == retry_after
    assert "API key not valid" not in str(info.value)


@pytest.mark.parametrize(
    ("exc", "cls"),
    [
        (requests.exceptions.ReadTimeout("t"), errors.ProviderTimeoutError),
        (requests.exceptions.ConnectionError("refused"), errors.ProviderUnavailableError),
    ],
)
def test_transport_errors_through_sdk(monkeypatch, adapter, exc, cls):
    FakeHttp(monkeypatch, exc=exc)
    with pytest.raises(cls):
        list(adapter.stream(MODEL, build_request("x")))
