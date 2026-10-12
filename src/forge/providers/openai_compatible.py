"""Adapter for OpenAI-compatible ``/chat/completions`` endpoints, over httpx.

Intended for Groq, Ollama (``/v1``), llama.cpp server, vLLM and similar services. Only the
common chat-completions subset is used; anything beyond it (seed, usage in streams, the
max-tokens field name) is configuration, not an assumption. Verified only against mocked
HTTP responses, not against any real service.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Iterable, Iterator
from typing import Any, Literal

import httpx

from forge.providers.base import (
    Capabilities,
    GenerationRequest,
    GenerationResult,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
)
from forge.providers.errors import (
    MalformedResponseError,
    ProviderConfigurationError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnknownProviderError,
    UpstreamServerError,
    error_for_status,
)
from forge.providers.retry import parse_retry_after

DEFAULT_CAPABILITIES = Capabilities(
    streaming=True, system_instruction=True, seed=False, usage_reporting=False
)

MAX_SSE_LINE_CHARS = 1_000_000
_LINE_END = re.compile(r"\r\n|\r|\n")
_CHAT_PATH = "/chat/completions"


class OpenAICompatibleAdapter:
    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        auth: Literal["bearer", "none"],
        api_key_env: str | None,
        get_secret: Callable[[str], str | None],
        timeout_seconds: float,
        capabilities: Capabilities = DEFAULT_CAPABILITIES,
        max_tokens_field: str = "max_tokens",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.name = name
        self.capabilities = capabilities
        self._base_url = base_url
        self._auth = auth
        self._api_key_env = api_key_env
        self._get_secret = get_secret
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_tokens_field = max_tokens_field
        self._transport = transport
        self._client: httpx.Client | None = None
        self._lock = threading.Lock()

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = httpx.Client(
                        base_url=self._base_url, timeout=self._timeout, transport=self._transport
                    )
        return self._client

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
                self._client = None

    # ── request construction ──────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._auth == "bearer":
            api_key = self._get_secret(self._api_key_env) if self._api_key_env else None
            if not api_key:
                raise ProviderConfigurationError(
                    f"{self._api_key_env} is not set. Add it to your environment or "
                    f".env file (provider '{self.name}').",
                    provider=self.name,
                )
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def build_payload(
        self, model: str, request: GenerationRequest, *, stream: bool
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        params = request.params
        if params.temperature is not None:
            payload["temperature"] = params.temperature
        if params.top_p is not None:
            payload["top_p"] = params.top_p
        if params.max_output_tokens is not None:
            payload[self._max_tokens_field] = params.max_output_tokens
        if params.seed is not None:
            payload["seed"] = params.seed
        return payload

    def _status_error(self, response: httpx.Response) -> ProviderError:
        return error_for_status(
            response.status_code,
            provider=self.name,
            retry_after=parse_retry_after(response.headers.get("Retry-After")),
        )

    def _transport_error(self, exc: httpx.HTTPError) -> ProviderError:
        message = f"{self.name}: {type(exc).__name__}"
        if isinstance(exc, httpx.TimeoutException):
            return ProviderTimeoutError(message, provider=self.name)
        if isinstance(exc, httpx.TransportError):
            return ProviderUnavailableError(message, provider=self.name)
        return UnknownProviderError(message, provider=self.name)

    # ── non-streaming ─────────────────────────────────────────────────────

    def generate(self, model: str, request: GenerationRequest) -> GenerationResult:
        payload = self.build_payload(model, request, stream=False)
        headers = self._headers()
        try:
            response = self.client.post(_CHAT_PATH, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise self._transport_error(exc) from exc
        if response.status_code >= 400:
            raise self._status_error(response)
        try:
            body = response.json()
        except ValueError:
            raise self._malformed("response body is not valid JSON") from None
        if not isinstance(body, dict):
            raise self._malformed("response body is not a JSON object")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise self._malformed("response has no choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise self._malformed("choice has no message")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise self._malformed("message content is not a string")
        return GenerationResult(
            provider=self.name,
            model=model,
            text=content or "",
            reported_model=_optional_str(body.get("model")),
            finish_reason=_optional_str(choices[0].get("finish_reason")),
            usage=_usage(body.get("usage")),
        )

    # ── streaming ─────────────────────────────────────────────────────────

    def stream(self, model: str, request: GenerationRequest) -> Iterator[StreamEvent]:
        payload = self.build_payload(model, request, stream=True)
        return self._stream(payload)

    def _stream(self, payload: dict[str, Any]) -> Iterator[StreamEvent]:
        headers = self._headers()
        try:
            with self.client.stream("POST", _CHAT_PATH, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    raise self._status_error(response)
                yield from self._parse_stream(response.iter_text())
        except httpx.HTTPError as exc:
            raise self._transport_error(exc) from exc

    def _parse_stream(self, text_chunks: Iterable[str]) -> Iterator[StreamEvent]:
        reported_model: str | None = None
        finish_reason: str | None = None
        usage: Usage | None = None
        done = False
        for event, data in iter_sse_events(iter_lines(text_chunks, provider=self.name)):
            if data.strip() == "[DONE]":
                done = True
                break
            if event == "error":
                raise UpstreamServerError(f"{self.name}: error event in stream", provider=self.name)
            try:
                chunk = json.loads(data)
            except ValueError:
                raise self._malformed("stream chunk is not valid JSON") from None
            if not isinstance(chunk, dict):
                raise self._malformed("stream chunk is not a JSON object")
            if "error" in chunk:
                raise UpstreamServerError(
                    f"{self.name}: error object in stream", provider=self.name
                )
            choices = chunk.get("choices")
            if not isinstance(choices, list):
                raise self._malformed("stream chunk has no choices list")
            reported_model = _optional_str(chunk.get("model")) or reported_model
            usage = _usage(chunk.get("usage")) or usage
            if not choices:
                continue  # e.g. a trailing usage-only chunk
            choice = choices[0]
            if not isinstance(choice, dict):
                raise self._malformed("stream choice is not an object")
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                raise self._malformed("stream delta is not an object")
            content = delta.get("content")
            if content is not None and not isinstance(content, str):
                raise self._malformed("stream delta content is not a string")
            if content:
                yield TextDelta(content)
            finish_reason = _optional_str(choice.get("finish_reason")) or finish_reason
        if not done and finish_reason is None:
            raise self._malformed("stream ended before completion")
        yield StreamEnd(reported_model=reported_model, finish_reason=finish_reason, usage=usage)

    def _malformed(self, reason: str) -> MalformedResponseError:
        return MalformedResponseError(f"{self.name}: {reason}", provider=self.name)


def iter_lines(text_chunks: Iterable[str], *, provider: str = "provider") -> Iterator[str]:
    """Split decoded text into lines on ``\\n``, ``\\r\\n`` or ``\\r``, across chunk boundaries.

    Linear in the input size: each chunk is scanned once, starting where new data begins.
    """
    buffer = ""
    for chunk in text_chunks:
        # The carried-over buffer holds no line ending except possibly a trailing CR (the
        # first half of a CRLF split across chunks), so rescanning starts there.
        scan_from = max(0, len(buffer) - 1)
        buffer += chunk
        start = 0
        for match in _LINE_END.finditer(buffer, scan_from):
            if match.group() == "\r" and match.end() == len(buffer):
                break  # wait for the next chunk to see whether LF follows
            yield buffer[start : match.start()]
            start = match.end()
        buffer = buffer[start:]
        if len(buffer) > MAX_SSE_LINE_CHARS:
            raise MalformedResponseError(f"{provider}: stream line too long", provider=provider)
    if buffer.endswith("\r"):
        buffer = buffer[:-1]
    if buffer:
        yield buffer


def iter_sse_events(lines: Iterable[str]) -> Iterator[tuple[str, str]]:
    """Assemble SSE lines into ``(event, data)`` pairs (multi-line data joined with ``\\n``)."""
    event = "message"
    data: list[str] = []
    for line in lines:
        if line == "":
            if data:
                yield event, "\n".join(data)
            event, data = "message", []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data.append(value)
        elif field == "event":
            event = value
    if data:
        yield event, "\n".join(data)


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _usage(value: Any) -> Usage | None:
    if not isinstance(value, dict):
        return None
    prompt = value.get("prompt_tokens")
    completion = value.get("completion_tokens")
    prompt = prompt if isinstance(prompt, int) and not isinstance(prompt, bool) else None
    completion = (
        completion if isinstance(completion, int) and not isinstance(completion, bool) else None
    )
    if prompt is None and completion is None:
        return None
    return Usage(prompt, completion)
