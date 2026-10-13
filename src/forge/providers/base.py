"""Provider-independent request/response types and the adapter protocol."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, fields, replace
from typing import Any, Literal, Protocol

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True)
class GenerationParams:
    """Sampling parameters. ``None`` means "not set": the provider's own default applies."""

    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    seed: int | None = None

    def merged_over(self, defaults: GenerationParams) -> GenerationParams:
        """Fill fields that are unset here from ``defaults``."""
        return replace(
            defaults,
            **{
                f.name: getattr(self, f.name)
                for f in fields(self)
                if getattr(self, f.name) is not None
            },
        )


@dataclass(frozen=True)
class GenerationRequest:
    messages: tuple[Message, ...]
    system: str | None = None
    params: GenerationParams = field(default_factory=GenerationParams)

    @classmethod
    def from_prompt(
        cls, prompt: str, *, system: str | None = None, params: GenerationParams | None = None
    ) -> GenerationRequest:
        return cls(
            messages=(Message("user", prompt),),
            system=system,
            params=params or GenerationParams(),
        )


@dataclass(frozen=True)
class Capabilities:
    """What a provider supports. Unsupported features are rejected, never silently dropped."""

    streaming: bool = True
    system_instruction: bool = True
    seed: bool = False
    usage_reporting: bool = False


@dataclass(frozen=True)
class Usage:
    """Token counts exactly as reported by the provider; ``None`` when not reported."""

    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class GenerationResult:
    provider: str
    model: str
    text: str
    reported_model: str | None = None
    finish_reason: str | None = None
    usage: Usage | None = None
    # True when served from the response cache instead of a fresh provider call.
    cache_hit: bool = False


@dataclass(frozen=True)
class TextDelta:
    """A piece of generated text from a stream."""

    text: str


@dataclass(frozen=True)
class StreamEnd:
    """Final stream event: metadata the provider reported, if any."""

    reported_model: str | None = None
    finish_reason: str | None = None
    usage: Usage | None = None


StreamEvent = TextDelta | StreamEnd


class ProviderAdapter(Protocol):
    """One configured provider. Implementations must raise only ``ProviderError`` subclasses."""

    name: str
    capabilities: Capabilities

    def generate(self, model: str, request: GenerationRequest) -> GenerationResult: ...

    def stream(self, model: str, request: GenerationRequest) -> Iterator[StreamEvent]:
        """Yield ``TextDelta`` events, then exactly one ``StreamEnd``.

        Closing the iterator early must release any underlying connection.
        """
        ...

    def cache_identity(self, model: str, request: GenerationRequest) -> dict[str, Any]:
        """JSON-serializable description of exactly what would be sent for this request.

        Used for response-cache keys: it must include every output-affecting input (endpoint,
        model, messages, system, parameters, response format) and must never include
        credentials or headers. Bump the adapter's ``CACHE_IDENTITY_VERSION`` whenever this
        serialization changes.
        """
        ...

    def close(self) -> None: ...
