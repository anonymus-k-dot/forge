"""Google GenAI (Gemini API) adapter, using the ``google-genai`` SDK."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterator
from typing import Any

from google import genai
from google.genai import errors as genai_errors, types

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
    AuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnknownProviderError,
    error_for_status,
)
from forge.providers.retry import parse_retry_after

DEFAULT_CAPABILITIES = Capabilities(
    streaming=True, system_instruction=True, seed=True, usage_reporting=True
)

_TIMEOUT_ERRORS: tuple[type[BaseException], ...] = (TimeoutError,)
_CONNECTION_ERRORS: tuple[type[BaseException], ...] = (ConnectionError,)
try:  # google-genai 1.x transports over requests; later versions use httpx.
    import requests  # type: ignore[import-untyped]

    _TIMEOUT_ERRORS += (requests.exceptions.Timeout,)
    _CONNECTION_ERRORS += (requests.exceptions.ConnectionError,)
except ImportError:  # pragma: no cover - depends on the installed SDK version
    pass
try:
    import httpx

    _TIMEOUT_ERRORS += (httpx.TimeoutException,)
    _CONNECTION_ERRORS += (httpx.TransportError,)
except ImportError:  # pragma: no cover
    pass

_RETRY_DELAY = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*$")


class GoogleGenAIAdapter:
    """Gemini API adapter. The SDK client is created on first use, never at construction."""

    def __init__(
        self,
        name: str,
        *,
        api_key_env: str,
        get_secret: Callable[[str], str | None],
        timeout_seconds: float,
        capabilities: Capabilities = DEFAULT_CAPABILITIES,
    ) -> None:
        self.name = name
        self.capabilities = capabilities
        self._api_key_env = api_key_env
        self._get_secret = get_secret
        self._timeout_ms = int(timeout_seconds * 1000)
        self._client: genai.Client | None = None
        self._lock = threading.Lock()

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    api_key = self._get_secret(self._api_key_env)
                    if not api_key:
                        raise ProviderConfigurationError(
                            f"{self._api_key_env} is not set. Add it to your environment or "
                            f".env file (provider '{self.name}').",
                            provider=self.name,
                        )
                    self._client = genai.Client(
                        api_key=api_key,
                        http_options=types.HttpOptions(timeout=self._timeout_ms),
                    )
        return self._client

    def build_config(self, request: GenerationRequest) -> types.GenerateContentConfig:
        """SDK config for a request; only fields that are set are passed."""
        options: dict[str, Any] = {}
        if request.system is not None:
            options["system_instruction"] = request.system
        params = request.params
        for field_name in ("temperature", "top_p", "max_output_tokens", "seed"):
            value = getattr(params, field_name)
            if value is not None:
                options[field_name] = value
        return types.GenerateContentConfig(**options)

    @staticmethod
    def build_contents(request: GenerationRequest) -> str | list[types.Content]:
        """A single user message is sent as a plain string, exactly as FORGE 1.x did."""
        messages = request.messages
        if len(messages) == 1 and messages[0].role == "user":
            return messages[0].content
        return [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part(text=m.content)],
            )
            for m in messages
        ]

    def generate(self, model: str, request: GenerationRequest) -> GenerationResult:
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=self.build_contents(request),
                config=self.build_config(request),
            )
            # The SDK's `.text` raises ValueError for non-text parts; keep it inside the
            # try so every failure is normalized here.
            text = getattr(response, "text", None) or ""
        except ProviderError:
            raise
        except Exception as exc:
            raise self.normalize_error(exc) from exc
        end = _metadata(response)
        return GenerationResult(
            provider=self.name,
            model=model,
            text=text,
            reported_model=end.reported_model,
            finish_reason=end.finish_reason,
            usage=end.usage,
        )

    def stream(self, model: str, request: GenerationRequest) -> Iterator[StreamEvent]:
        return self._stream(model, request)

    def _stream(self, model: str, request: GenerationRequest) -> Iterator[StreamEvent]:
        chunks: Any = None
        end = StreamEnd()
        try:
            chunks = self.client.models.generate_content_stream(
                model=model,
                contents=self.build_contents(request),
                config=self.build_config(request),
            )
            for chunk in chunks:
                text = getattr(chunk, "text", None)
                if text:
                    yield TextDelta(text)
                end = _merge_metadata(end, _metadata(chunk))
        except ProviderError:
            raise
        except Exception as exc:
            raise self.normalize_error(exc) from exc
        finally:
            close = getattr(chunks, "close", None)
            if callable(close):
                close()
        yield end

    def close(self) -> None:
        self._client = None

    def normalize_error(self, exc: BaseException) -> ProviderError:
        """Classify an SDK/transport exception. Messages never include upstream text."""
        if isinstance(exc, genai_errors.APIError):
            status = exc.code if isinstance(exc.code, int) else 0
            details = exc.details if isinstance(exc.details, dict) else {}
            if status == 400 and _reports_invalid_api_key(details):
                return AuthenticationError(
                    f"{self.name}: upstream HTTP 400 (API_KEY_INVALID)",
                    provider=self.name,
                    status_code=status,
                )
            return error_for_status(
                status, provider=self.name, retry_after=_retry_after(exc, details)
            )
        if isinstance(exc, _TIMEOUT_ERRORS):
            return ProviderTimeoutError(f"{self.name}: {type(exc).__name__}", provider=self.name)
        if isinstance(exc, _CONNECTION_ERRORS):
            return ProviderUnavailableError(
                f"{self.name}: {type(exc).__name__}", provider=self.name
            )
        return UnknownProviderError(f"{self.name}: {type(exc).__name__}", provider=self.name)


def _error_details(details: dict[str, Any]) -> list[Any]:
    error = details.get("error", details)
    items = error.get("details") if isinstance(error, dict) else None
    return items if isinstance(items, list) else []


def _reports_invalid_api_key(details: dict[str, Any]) -> bool:
    return any(
        isinstance(d, dict) and d.get("reason") == "API_KEY_INVALID"
        for d in _error_details(details)
    )


def _retry_after(exc: genai_errors.APIError, details: dict[str, Any]) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is not None and hasattr(headers, "get"):
        from_header = parse_retry_after(headers.get("Retry-After"))
        if from_header is not None:
            return from_header
    for item in _error_details(details):
        if isinstance(item, dict) and isinstance(item.get("retryDelay"), str):
            match = _RETRY_DELAY.match(item["retryDelay"])
            if match:
                return float(match.group(1))
    return None


def _metadata(response: Any) -> StreamEnd:
    usage = None
    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata is not None:
        input_tokens = getattr(usage_metadata, "prompt_token_count", None)
        output_tokens = getattr(usage_metadata, "candidates_token_count", None)
        if isinstance(input_tokens, int) or isinstance(output_tokens, int):
            usage = Usage(
                input_tokens if isinstance(input_tokens, int) else None,
                output_tokens if isinstance(output_tokens, int) else None,
            )
    finish_reason = None
    candidates = getattr(response, "candidates", None)
    if isinstance(candidates, list) and candidates:
        reason = getattr(candidates[0], "finish_reason", None)
        if reason is not None:
            finish_reason = str(getattr(reason, "value", reason))
    model_version = getattr(response, "model_version", None)
    return StreamEnd(
        reported_model=model_version if isinstance(model_version, str) else None,
        finish_reason=finish_reason,
        usage=usage,
    )


def _merge_metadata(current: StreamEnd, update: StreamEnd) -> StreamEnd:
    return StreamEnd(
        reported_model=update.reported_model or current.reported_model,
        finish_reason=update.finish_reason or current.finish_reason,
        usage=update.usage or current.usage,
    )
