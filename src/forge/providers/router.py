"""ProviderRouter: the single entry point for model calls.

Resolves a model profile to a provider adapter and applies capability checks, per-provider
concurrency limits, and bounded retries. Concurrency limits are enforced **per process**:
with N Gunicorn workers the effective limit per provider is N × ``max_concurrency``.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Generator, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import TypeVar

from forge.infrastructure.budgets import BudgetGuard, Reservation
from forge.infrastructure.cache import CachedResponse, CachePolicy, cache_key, is_cacheable
from forge.providers.base import (
    GenerationParams,
    GenerationRequest,
    GenerationResult,
    ProviderAdapter,
    StreamEnd,
    StreamEvent,
    TextDelta,
    Usage,
)
from forge.providers.config import ProviderConfig, ProvidersConfig
from forge.providers.errors import (
    ConcurrencyLimitError,
    ProviderConfigurationError,
    ProviderError,
    UnknownProviderError,
    UnsupportedCapabilityError,
)
from forge.providers.retry import RetryPolicy

logger = logging.getLogger(__name__)

T = TypeVar("T")
SecretLookup = Callable[[str], str | None]


@dataclass(frozen=True)
class ModelProfile:
    name: str
    provider: str
    model: str
    params: GenerationParams


def build_adapter(name: str, config: ProviderConfig, get_secret: SecretLookup) -> ProviderAdapter:
    """Construct an adapter from configuration. No network I/O happens here."""
    if config.type == "google_genai":
        from forge.providers import google_genai

        assert config.api_key_env is not None  # enforced by ProviderConfig validation
        return google_genai.GoogleGenAIAdapter(
            name,
            api_key_env=config.api_key_env,
            get_secret=get_secret,
            timeout_seconds=config.timeout_seconds,
            capabilities=config.capabilities.apply_to(google_genai.DEFAULT_CAPABILITIES),
        )
    if config.type == "openai_compatible":
        from forge.providers import openai_compatible

        assert config.base_url is not None  # enforced by ProviderConfig validation
        return openai_compatible.OpenAICompatibleAdapter(
            name,
            base_url=config.base_url,
            auth=config.auth,
            api_key_env=config.api_key_env,
            get_secret=get_secret,
            timeout_seconds=config.timeout_seconds,
            capabilities=config.capabilities.apply_to(openai_compatible.DEFAULT_CAPABILITIES),
            max_tokens_field=config.max_tokens_field,
        )
    from forge.providers.fake import FakeAdapter, FakeResponse

    return FakeAdapter(
        name,
        default=FakeResponse(chunks=(config.fake_response or "",)),
    )


class ProviderRouter:
    def __init__(
        self,
        config: ProvidersConfig,
        *,
        get_secret: SecretLookup = lambda _name: None,
        adapters: Mapping[str, ProviderAdapter] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        """``adapters`` overrides configured adapters by provider name (used by tests)."""
        unknown = set(adapters or {}) - set(config.providers)
        if unknown:
            raise ProviderConfigurationError(
                f"Adapters given for unknown providers: {sorted(unknown)}"
            )
        self._config = config
        self._get_secret = get_secret
        self._adapters: dict[str, ProviderAdapter] = dict(adapters or {})
        self._adapters_lock = threading.Lock()
        self._slots = {
            name: threading.BoundedSemaphore(provider.max_concurrency)
            for name, provider in config.providers.items()
        }
        self._sleep = sleep
        self._rng = rng or random.Random()

    @property
    def config(self) -> ProvidersConfig:
        return self._config

    def profile(self, name: str | None = None) -> ModelProfile:
        name = name or self._config.default_model
        profile = self._config.models.get(name)
        if profile is None:
            raise ProviderConfigurationError(f"Unknown model profile '{name}'.")
        return ModelProfile(name, profile.provider, profile.model, profile.params.to_params())

    def adapter(self, provider: str) -> ProviderAdapter:
        with self._adapters_lock:
            adapter = self._adapters.get(provider)
            if adapter is None:
                adapter = build_adapter(
                    provider, self._config.providers[provider], self._get_secret
                )
                self._adapters[provider] = adapter
            return adapter

    def close(self) -> None:
        with self._adapters_lock:
            for adapter in self._adapters.values():
                adapter.close()

    # ── calls ──────────────────────────────────────────────────────────────

    def generate(
        self,
        request: GenerationRequest,
        *,
        model: str | None = None,
        budget: BudgetGuard | None = None,
        cache: CachePolicy | None = None,
    ) -> GenerationResult:
        """One completion.

        ``cache`` (opt-in): a fresh, non-expired cached result for the identical effective
        request is returned with ``cache_hit=True`` and no provider call; otherwise a
        complete, successful result (``is_cacheable``) is stored. ``budget``: every provider
        attempt (including retries)
        reserves budget first and is settled afterwards; cache hits consume none.
        """
        profile, adapter, request = self._prepare(request, model, streaming=False)
        key = None
        if cache is not None:
            key = cache_key(adapter, profile.model, request, cache.namespace)
            cached = cache.store.get(key)
            if cached is not None:
                _log_cache("cache.hit", key, profile)
                if budget is not None:
                    _record_cache_hit(budget)
                return cached.to_result(profile.provider, profile.model)
            _log_cache("cache.miss", key, profile)

        policy = self._policy(profile.provider)
        for attempt in range(1, policy.max_attempts + 1):
            try:
                with self._slot(profile.provider):
                    reservation = budget.reserve(request) if budget is not None else None
                    try:
                        result = _normalized(
                            profile.provider, lambda: adapter.generate(profile.model, request)
                        )
                    except ProviderError:
                        _settle(budget, reservation, None)
                        raise
                    _settle(budget, reservation, result.usage)
                break
            except ProviderError as error:
                self._backoff_or_raise(error, attempt, policy, profile.provider)
        else:  # pragma: no cover - the loop always returns, breaks or raises
            raise AssertionError("unreachable")

        if cache is not None and key is not None:
            if not is_cacheable(result):
                _log_cache("cache.not_stored", key, profile)
                return result
            cache.store.put(
                key,
                CachedResponse.from_result(result),
                ttl_seconds=cache.ttl_seconds,
                provider_type=self._config.providers[profile.provider].type,
                model=profile.model,
            )
            _log_cache("cache.store", key, profile)
        return result

    def stream(
        self,
        request: GenerationRequest,
        *,
        model: str | None = None,
        budget: BudgetGuard | None = None,
    ) -> Generator[StreamEvent, None, None]:
        """Stream events. Retries only happen before the first text has been yielded.

        Streams never use the response cache (no partial or re-chunked replays). With a
        ``budget``, every attempt is reserved and settled, including interrupted streams.
        """
        profile, adapter, request = self._prepare(request, model, streaming=True)
        return self._stream(profile, adapter, request, budget)

    def _stream(
        self,
        profile: ModelProfile,
        adapter: ProviderAdapter,
        request: GenerationRequest,
        budget: BudgetGuard | None = None,
    ) -> Generator[StreamEvent, None, None]:
        policy = self._policy(profile.provider)
        delivered = False
        for attempt in range(1, policy.max_attempts + 1):
            try:
                with self._slot(profile.provider):
                    reservation = budget.reserve(request) if budget is not None else None
                    usage = None
                    try:
                        events = _normalized(
                            profile.provider, lambda: adapter.stream(profile.model, request)
                        )
                        try:
                            while True:
                                event = _normalized(profile.provider, lambda: next(events, None))
                                if event is None:
                                    return
                                if isinstance(event, TextDelta) and event.text:
                                    delivered = True
                                elif isinstance(event, StreamEnd):
                                    usage = event.usage
                                yield event
                        finally:
                            close = getattr(events, "close", None)
                            if callable(close):
                                close()
                    finally:
                        # Completed streams settle with reported usage; failed or
                        # abandoned ones keep the conservative estimate.
                        _settle(budget, reservation, usage)
            except ProviderError as error:
                if delivered:
                    raise
                self._backoff_or_raise(error, attempt, policy, profile.provider)

    # ── helpers ────────────────────────────────────────────────────────────

    def _prepare(
        self, request: GenerationRequest, model: str | None, *, streaming: bool
    ) -> tuple[ModelProfile, ProviderAdapter, GenerationRequest]:
        profile = self.profile(model)
        adapter = self.adapter(profile.provider)
        request = replace(request, params=request.params.merged_over(profile.params))
        caps = adapter.capabilities
        unsupported = [
            feature
            for feature, needed, supported in (
                ("streaming", streaming, caps.streaming),
                ("system_instruction", request.system is not None, caps.system_instruction),
                ("seed", request.params.seed is not None, caps.seed),
            )
            if needed and not supported
        ]
        if unsupported:
            raise UnsupportedCapabilityError(
                f"{profile.provider}: unsupported {', '.join(unsupported)}",
                provider=profile.provider,
            )
        return profile, adapter, request

    def _policy(self, provider: str) -> RetryPolicy:
        return self._config.providers[provider].retry.to_policy()

    @contextmanager
    def _slot(self, provider: str) -> Iterator[None]:
        timeout = self._config.providers[provider].acquire_timeout_seconds
        semaphore = self._slots[provider]
        if not semaphore.acquire(timeout=timeout):
            raise ConcurrencyLimitError(
                f"{provider}: no concurrency slot within {timeout}s", provider=provider
            )
        try:
            yield
        finally:
            semaphore.release()

    def _backoff_or_raise(
        self, error: ProviderError, attempt: int, policy: RetryPolicy, provider: str
    ) -> None:
        delay = (
            None
            if isinstance(error, ConcurrencyLimitError)
            else policy.delay_before_retry(error, attempt, self._rng)
        )
        if delay is None:
            raise error
        logger.warning(
            "provider.retry",
            extra={
                "forge": {
                    "provider": provider,
                    "attempt": attempt,
                    "max_attempts": policy.max_attempts,
                    "category": error.category.value,
                    "status_code": error.status_code,
                    "delay_seconds": round(delay, 3),
                }
            },
        )
        self._sleep(delay)  # the concurrency slot is already released here


def _normalized(provider: str, call: Callable[[], T]) -> T:
    """Run an adapter call; anything that is not a ProviderError becomes UnknownProviderError."""
    try:
        return call()
    except ProviderError:
        raise
    except Exception as exc:
        raise UnknownProviderError(
            f"{provider}: unexpected {type(exc).__name__}", provider=provider
        ) from exc


def _settle(
    budget: BudgetGuard | None, reservation: Reservation | None, usage: Usage | None
) -> None:
    """Settle an attempt's reservation. A failure here keeps the reservation counted
    (conservative), so enforcement is never weakened; the result is still returned."""
    if budget is None or reservation is None or reservation.settled:
        return
    try:
        budget.settle(reservation, usage)
    except Exception as exc:  # noqa: BLE001
        logger.warning("budget.settle_failed", extra={"forge": {"error_type": type(exc).__name__}})


def _record_cache_hit(budget: BudgetGuard) -> None:
    """Cache hits consume no budget; counting them is best-effort statistics."""
    try:
        budget.record_cache_hit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "budget.cache_hit_not_recorded", extra={"forge": {"error_type": type(exc).__name__}}
        )


def _log_cache(event: str, key: str, profile: ModelProfile) -> None:
    # Only a key prefix and identifiers: never prompts, responses or full keys.
    logger.info(
        event,
        extra={
            "forge": {"key_prefix": key[:12], "provider": profile.provider, "model": profile.model}
        },
    )
