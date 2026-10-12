import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from forge.providers import errors
from forge.providers.base import (
    GenerationParams,
    GenerationRequest,
    StreamEnd,
    TextDelta,
    Usage,
)
from forge.providers.openai_compatible import OpenAICompatibleAdapter, iter_lines, iter_sse_events

SECRET = "gsk_test_secret_value_0000000000"
REQUEST = GenerationRequest.from_prompt(
    "hello",
    system="sys",
    params=GenerationParams(temperature=0.5, top_p=0.85, max_output_tokens=64),
)


class TrackingStream(httpx.SyncByteStream):
    """Response body delivered in the given byte chunks; records whether it was closed."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False
        self.delivered = 0

    def __iter__(self):
        for c in self.chunks:
            self.delivered += 1
            yield c

    def close(self):
        self.closed = True


class Server:
    """MockTransport handler that records requests and replays a response factory."""

    def __init__(self, respond):
        self.respond = respond
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.respond(request)


def make_adapter(respond, *, auth="bearer", secret=SECRET, max_tokens_field="max_tokens"):
    server = Server(respond)
    adapter = OpenAICompatibleAdapter(
        "groq",
        base_url="https://llm.example.test/v1",
        auth=auth,
        api_key_env="GROQ_API_KEY" if auth == "bearer" else None,
        get_secret={"GROQ_API_KEY": secret}.get,
        timeout_seconds=5,
        max_tokens_field=max_tokens_field,
        transport=httpx.MockTransport(server),
    )
    return adapter, server


def sse(*payloads, done=True):
    body = "".join(f"data: {json.dumps(p) if not isinstance(p, str) else p}\n\n" for p in payloads)
    return body + ("data: [DONE]\n\n" if done else "")


def delta(text=None, finish=None, **extra):
    d = {} if text is None else {"content": text}
    return {"choices": [{"delta": d, "finish_reason": finish}], "model": "m-reported", **extra}


def stream_response(body, status=200, chunk_size=None, headers=None):
    data = body.encode() if isinstance(body, str) else body
    chunks = (
        [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
        if chunk_size
        else [data]
    )
    stream = TrackingStream(chunks)
    return httpx.Response(
        status, headers={"content-type": "text/event-stream", **(headers or {})}, stream=stream
    ), stream


def collect(adapter, request=REQUEST):
    return list(adapter.stream("m", request))


class TestRequestConstruction:
    def test_payload_headers_and_url(self):
        adapter, server = make_adapter(
            lambda r: httpx.Response(
                200, json={"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
            )
        )
        adapter.generate("llama-x", REQUEST)
        request = server.requests[0]
        assert str(request.url) == "https://llm.example.test/v1/chat/completions"
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        assert json.loads(request.content) == {
            "model": "llama-x",
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
            ],
            "stream": False,
            "temperature": 0.5,
            "top_p": 0.85,
            "max_tokens": 64,
        }

    def test_no_auth_header_for_keyless_endpoint(self):
        adapter, server = make_adapter(
            lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]}),
            auth="none",
        )
        adapter.generate("m", REQUEST)
        assert "Authorization" not in server.requests[0].headers

    def test_configurable_max_tokens_field_and_seed(self):
        adapter, server = make_adapter(
            lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]}),
            max_tokens_field="max_completion_tokens",
        )
        adapter.generate(
            "m",
            GenerationRequest.from_prompt(
                "q", params=GenerationParams(max_output_tokens=9, seed=4)
            ),
        )
        body = json.loads(server.requests[0].content)
        assert body["max_completion_tokens"] == 9 and "max_tokens" not in body
        assert body["seed"] == 4

    def test_missing_key_fails_before_any_request(self):
        adapter, server = make_adapter(lambda r: httpx.Response(200), secret=None)
        with pytest.raises(errors.ProviderConfigurationError, match="GROQ_API_KEY is not set"):
            adapter.generate("m", REQUEST)
        with pytest.raises(errors.ProviderConfigurationError):
            collect(adapter)
        assert server.requests == []


class TestNonStreaming:
    def test_success_with_usage(self):
        adapter, _ = make_adapter(
            lambda r: httpx.Response(
                200,
                json={
                    "model": "llama-x-0001",
                    "choices": [
                        {"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
                },
            )
        )
        result = adapter.generate("llama-x", REQUEST)
        assert (result.provider, result.model, result.text) == ("groq", "llama-x", "hi")
        assert result.reported_model == "llama-x-0001"
        assert result.finish_reason == "stop"
        assert result.usage == Usage(12, 3)

    def test_usage_absent_is_not_invented(self):
        adapter, _ = make_adapter(
            lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})
        )
        assert adapter.generate("m", REQUEST).usage is None

    def test_null_content_is_empty_text(self):
        adapter, _ = make_adapter(
            lambda r: httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
        )
        assert adapter.generate("m", REQUEST).text == ""

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(200, content=b"not json"),
            httpx.Response(200, content=b""),
            httpx.Response(200, json=[1, 2]),
            httpx.Response(200, json={}),
            httpx.Response(200, json={"choices": []}),
            httpx.Response(200, json={"choices": [{"text": "legacy completion"}]}),
            httpx.Response(200, json={"choices": [{"message": {"content": 5}}]}),
        ],
    )
    def test_malformed_or_empty_responses(self, response):
        adapter, _ = make_adapter(lambda r: response)
        with pytest.raises(errors.MalformedResponseError):
            adapter.generate("m", REQUEST)


class TestHttpErrors:
    @pytest.mark.parametrize(
        ("status", "cls"),
        [
            (400, errors.InvalidRequestError),
            (401, errors.AuthenticationError),
            (403, errors.AuthenticationError),
            (404, errors.InvalidRequestError),
            (422, errors.InvalidRequestError),
            (429, errors.RateLimitError),
            (500, errors.UpstreamServerError),
            (502, errors.UpstreamServerError),
            (503, errors.ProviderUnavailableError),
        ],
    )
    @pytest.mark.parametrize("streaming", [False, True])
    def test_status_classification_without_leaking_body(self, status, cls, streaming):
        body = {"error": {"message": f"Invalid API key {SECRET}", "type": "invalid_request_error"}}
        adapter, _ = make_adapter(lambda r: httpx.Response(status, json=body))
        with pytest.raises(cls) as info:
            collect(adapter) if streaming else adapter.generate("m", REQUEST)
        for text in (str(info.value), info.value.safe_message):
            assert SECRET not in text and "Invalid API key" not in text

    def test_429_numeric_retry_after(self):
        adapter, _ = make_adapter(lambda r: httpx.Response(429, headers={"Retry-After": "7"}))
        with pytest.raises(errors.RateLimitError) as info:
            adapter.generate("m", REQUEST)
        assert info.value.retry_after == 7.0

    def test_429_http_date_retry_after(self):
        when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=120), usegmt=True)
        adapter, _ = make_adapter(lambda r: httpx.Response(429, headers={"Retry-After": when}))
        with pytest.raises(errors.RateLimitError) as info:
            adapter.generate("m", REQUEST)
        assert 110 <= info.value.retry_after <= 120

    @pytest.mark.parametrize(
        ("exc", "cls"),
        [
            (httpx.ConnectError("refused"), errors.ProviderUnavailableError),
            (httpx.ReadError("reset"), errors.ProviderUnavailableError),
            (httpx.RemoteProtocolError("incomplete chunked read"), errors.ProviderUnavailableError),
            (httpx.ConnectTimeout("connect"), errors.ProviderTimeoutError),
            (httpx.ReadTimeout("read"), errors.ProviderTimeoutError),
        ],
    )
    @pytest.mark.parametrize("streaming", [False, True])
    def test_transport_failures(self, exc, cls, streaming):
        def raise_(request):
            raise exc

        adapter, _ = make_adapter(raise_)
        with pytest.raises(cls) as info:
            collect(adapter) if streaming else adapter.generate("m", REQUEST)
        assert info.value.__cause__ is exc


class TestStreaming:
    def test_success_with_multiple_chunks(self):
        body = sse(
            {"choices": [{"delta": {"role": "assistant"}}]},
            delta("Hel"),
            delta("lo"),
            delta(None, finish="stop"),
            {"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 2}},
        )
        response, _ = stream_response(body)
        adapter, server = make_adapter(lambda r: response)
        events = collect(adapter)
        assert events == [
            TextDelta("Hel"),
            TextDelta("lo"),
            StreamEnd(reported_model="m-reported", finish_reason="stop", usage=Usage(4, 2)),
        ]
        assert json.loads(server.requests[0].content)["stream"] is True

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 7])
    def test_frames_split_across_arbitrary_byte_boundaries(self, chunk_size):
        body = sse(delta("héllo ✓ "), delta("wörld", finish="stop")).replace("\n", "\r\n")
        response, _ = stream_response(body, chunk_size=chunk_size)
        adapter, _ = make_adapter(lambda r: response)
        assert [e.text for e in collect(adapter) if isinstance(e, TextDelta)] == [
            "héllo ✓ ",
            "wörld",
        ]

    def test_multiline_data_comments_and_event_fields(self):
        payload = json.dumps(delta("x", finish="stop"))
        # Multi-line data is joined with "\n"; splitting after a comma keeps it valid JSON.
        split = payload.index(",") + 1
        head, tail = payload[:split], payload[split:]
        body = f": keep-alive\nevent: message\ndata: {head}\ndata: {tail}\n\ndata: [DONE]\n\n"
        response, _ = stream_response(body)
        adapter, _ = make_adapter(lambda r: response)
        assert collect(adapter)[0] == TextDelta("x")

    def test_done_terminates_and_closes_response(self):
        body = sse(delta("a", finish="stop")) + "data: {not even json\n\n"
        response, stream = stream_response(body)
        adapter, _ = make_adapter(lambda r: response)
        assert [e for e in collect(adapter) if isinstance(e, TextDelta)] == [TextDelta("a")]
        assert stream.closed

    def test_finish_reason_without_done_is_complete(self):
        response, _ = stream_response(sse(delta("a", finish="stop"), done=False))
        adapter, _ = make_adapter(lambda r: response)
        assert collect(adapter)[-1].finish_reason == "stop"

    def test_empty_stream_with_done_is_an_empty_completion(self):
        response, _ = stream_response("data: [DONE]\n\n")
        adapter, _ = make_adapter(lambda r: response)
        assert collect(adapter) == [StreamEnd()]

    @pytest.mark.parametrize(
        "body",
        [
            sse(delta("a"), done=False),  # incomplete: no finish_reason, no [DONE]
            "",  # empty body
            "data: {broken json\n\n",
            sse("[1, 2]"),
            sse({"no_choices": True}),
            sse({"choices": [{"delta": "text"}]}),
            sse({"choices": [{"delta": {"content": 42}}]}),
        ],
    )
    def test_malformed_streams(self, body):
        response, stream = stream_response(body)
        adapter, _ = make_adapter(lambda r: response)
        with pytest.raises(errors.MalformedResponseError):
            collect(adapter)
        assert stream.closed

    @pytest.mark.parametrize(
        "body",
        [
            sse(delta("a"), {"error": {"message": f"overloaded {SECRET}"}}),
            sse(delta("a")).replace(
                "data: [DONE]", f'event: error\ndata: {{"message": "{SECRET}"}}'
            ),
        ],
    )
    def test_upstream_error_event_during_stream(self, body):
        response, _ = stream_response(body)
        adapter, _ = make_adapter(lambda r: response)
        stream = adapter.stream("m", REQUEST)
        assert next(stream) == TextDelta("a")
        with pytest.raises(errors.UpstreamServerError) as info:
            next(stream)
        assert SECRET not in str(info.value)

    def test_consumer_close_closes_http_response(self):
        response, stream = stream_response(
            sse(delta("a"), delta("b"), delta("c", finish="stop")), chunk_size=10
        )
        adapter, _ = make_adapter(lambda r: response)
        events = adapter.stream("m", REQUEST)
        assert next(events) == TextDelta("a")
        events.close()
        assert stream.closed
        assert stream.delivered < len(stream.chunks)

    def test_adapter_close_releases_client(self):
        adapter, _ = make_adapter(
            lambda r: httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})
        )
        adapter.generate("m", REQUEST)
        client = adapter.client
        adapter.close()
        assert client.is_closed


class TestSseParsing:
    def test_iter_lines_handles_all_terminators_and_split_crlf(self):
        assert list(iter_lines(["a\r", "\nb\rc\n", "d"])) == ["a", "b", "c", "d"]
        assert list(iter_lines(["a\r"])) == ["a"]
        assert list(iter_lines(["\n\n"])) == ["", ""]

    def test_crlf_split_after_consumed_lines(self):
        assert list(iter_lines(["a\nb\r", "\nc\r", "\r\n", "d\r"])) == ["a", "b", "c", "", "d"]

    def test_many_lines_in_one_chunk(self):
        # Many lines in a single chunk. The previous splitter rescanned the remaining buffer
        # per line (quadratic: measured 0.67 s for 50k lines vs 0.012 s now).
        lines = [f"data: {i}" for i in range(50_000)]
        assert list(iter_lines(["\n".join(lines) + "\n"])) == lines

    def test_line_length_is_bounded(self, monkeypatch):
        monkeypatch.setattr("forge.providers.openai_compatible.MAX_SSE_LINE_CHARS", 10)
        with pytest.raises(errors.MalformedResponseError):
            list(iter_lines(["x" * 11]))

    def test_iter_sse_events(self):
        lines = ["event: error", "data: a", "data: b", "", ": comment", "data:c", "id: 1", ""]
        assert list(iter_sse_events(lines)) == [("error", "a\nb"), ("message", "c")]
        assert list(iter_sse_events(["data: tail"])) == [("message", "tail")]
