"""Deterministic in-process provider for tests and offline runs. Makes no network calls."""

from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from typing import Any

from forge.providers.base import (
    Capabilities,
    GenerationRequest,
    GenerationResult,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
)
from forge.providers.errors import ProviderError, UnknownProviderError


@dataclass(frozen=True)
class FakeResponse:
    """One scripted reply. ``error_after_chunks`` is raised once all ``chunks`` are emitted."""

    chunks: tuple[str, ...] = ()
    finish_reason: str | None = "stop"
    usage: Usage | None = None
    reported_model: str | None = None
    error_after_chunks: ProviderError | None = None


FakeStep = FakeResponse | ProviderError


@dataclass(frozen=True)
class FakeCall:
    method: str
    model: str
    request: GenerationRequest


class FakeAdapter:
    """Replays a script of responses/errors, one step per call, then ``default``.

    Errors in the script are raised when the call starts; ``FakeResponse.error_after_chunks``
    simulates a failure part-way through a stream. Calls are recorded in ``calls``.
    """

    def __init__(
        self,
        name: str = "fake",
        script: Iterable[FakeStep] = (),
        *,
        default: FakeStep | None = None,
        capabilities: Capabilities | None = None,
    ) -> None:
        self.name = name
        self.capabilities = capabilities or Capabilities(
            streaming=True, system_instruction=True, seed=True, usage_reporting=True
        )
        self._script = list(script)
        self._default = default
        self._lock = threading.Lock()
        self.calls: list[FakeCall] = []
        self.open_streams = 0
        self.closed = False

    def _next_step(self, method: str, model: str, request: GenerationRequest) -> FakeStep:
        with self._lock:
            self.calls.append(FakeCall(method, model, request))
            if self._script:
                return self._script.pop(0)
        if self._default is None:
            return UnknownProviderError(f"{self.name}: fake script exhausted", provider=self.name)
        return self._default

    def generate(self, model: str, request: GenerationRequest) -> GenerationResult:
        step = self._next_step("generate", model, request)
        if isinstance(step, ProviderError):
            raise step
        if step.error_after_chunks is not None:
            raise step.error_after_chunks
        return GenerationResult(
            provider=self.name,
            model=model,
            text="".join(step.chunks),
            reported_model=step.reported_model,
            finish_reason=step.finish_reason,
            usage=step.usage,
        )

    def stream(self, model: str, request: GenerationRequest) -> Iterator[StreamEvent]:
        step = self._next_step("stream", model, request)
        return self._stream(step)

    def _stream(self, step: FakeStep) -> Iterator[StreamEvent]:
        with self._lock:
            self.open_streams += 1
        try:
            if isinstance(step, ProviderError):
                raise step
            for chunk in step.chunks:
                yield TextDelta(chunk)
            if step.error_after_chunks is not None:
                raise step.error_after_chunks
            yield StreamEnd(step.reported_model, step.finish_reason, step.usage)
        finally:
            with self._lock:
                self.open_streams -= 1

    def cache_identity(self, model: str, request: GenerationRequest) -> dict[str, Any]:
        return {
            "type": "fake",
            "version": 1,
            "name": self.name,
            "model": model,
            "system": request.system,
            "messages": [asdict(m) for m in request.messages],
            "params": asdict(request.params),
        }

    def close(self) -> None:
        self.closed = True
