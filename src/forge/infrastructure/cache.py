"""Response cache: canonical keys, TTL policy, and stores.

Key construction
    ``sha256(canonical_json(document))`` where the document is::

        {"key_version": CACHE_KEY_VERSION,
         "request": adapter.cache_identity(model, request),   # exactly what would be sent
         "namespace": {...}}                                   # optional caller context

    Canonical JSON: keys sorted, no insignificant whitespace, UTF-8, no ASCII escaping,
    NaN/Infinity rejected, values kept with their JSON types (``1`` and ``1.0`` differ;
    strings are not Unicode-normalized). Equal documents always give equal keys; any
    behavior-affecting difference changes the document and therefore the key. Credentials
    and headers are never part of ``cache_identity``.

Policy
    Only successful, complete, non-streaming results are stored (``is_cacheable``: non-empty
    text and a normal finish reason; blocked, filtered or empty results are returned to the
    caller but never stored). Entries expire after
    ``ttl_seconds`` (default 30 days, ``FORGE_CACHE_TTL_SECONDS``); expired entries are misses
    and are replaced by the next successful call. Store failures fail open (miss, no write).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from forge.db.session import Database
from forge.errors import ConfigurationError, DatabaseUnavailableError
from forge.providers.base import GenerationRequest, GenerationResult, ProviderAdapter, Usage

logger = logging.getLogger(__name__)

# Bump to invalidate every existing entry (e.g. when the document layout changes).
CACHE_KEY_VERSION = 1
DEFAULT_TTL_SECONDS = 30 * 24 * 3600
MAX_TTL_SECONDS = 365 * 24 * 3600
# Finish reasons of a normal completion (compared lower-case): Gemini ``STOP``/``MAX_TOKENS``,
# OpenAI-compatible ``stop``/``length``. Truncation at max_output_tokens is the request's own
# deterministic outcome. ``None`` is accepted because some OpenAI-compatible servers omit it.
# Anything else (safety, recitation, content filter, tool calls, unspecified, ...) is not
# stored.
CACHEABLE_FINISH_REASONS = frozenset({"stop", "length", "max_tokens"})


def is_cacheable(result: GenerationResult) -> bool:
    """True for a complete, successful result: non-empty text and a normal finish reason."""
    if not result.text:
        return False
    reason = result.finish_reason
    return reason is None or reason.lower() in CACHEABLE_FINISH_REASONS


def canonical_json(document: Any) -> bytes:
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def cache_key_document(
    adapter: ProviderAdapter,
    model: str,
    request: GenerationRequest,
    namespace: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key_version": CACHE_KEY_VERSION,
        "request": adapter.cache_identity(model, request),
        "namespace": dict(namespace or {}),
    }


def cache_key(
    adapter: ProviderAdapter,
    model: str,
    request: GenerationRequest,
    namespace: Mapping[str, Any] | None = None,
) -> str:
    return hashlib.sha256(
        canonical_json(cache_key_document(adapter, model, request, namespace))
    ).hexdigest()


@dataclass(frozen=True)
class CachedResponse:
    """Everything needed to rebuild a ``GenerationResult``; nothing about the request."""

    text: str
    reported_model: str | None = None
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @classmethod
    def from_result(cls, result: GenerationResult) -> CachedResponse:
        usage = result.usage
        return cls(
            text=result.text,
            reported_model=result.reported_model,
            finish_reason=result.finish_reason,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
        )

    def to_result(self, provider: str, model: str) -> GenerationResult:
        usage = (
            Usage(self.input_tokens, self.output_tokens)
            if self.input_tokens is not None or self.output_tokens is not None
            else None
        )
        return GenerationResult(
            provider=provider,
            model=model,
            text=self.text,
            reported_model=self.reported_model,
            finish_reason=self.finish_reason,
            usage=usage,
            cache_hit=True,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "reported_model": self.reported_model,
            "finish_reason": self.finish_reason,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }

    @classmethod
    def from_json(cls, data: Any) -> CachedResponse:
        """Parse a stored entry; raises ``ValueError`` if it is not a valid response."""
        if not isinstance(data, Mapping) or not isinstance(data.get("text"), str):
            raise ValueError("cache entry has no text")
        for name in ("reported_model", "finish_reason"):
            if data.get(name) is not None and not isinstance(data[name], str):
                raise ValueError(f"cache entry field {name} is not a string")
        for name in ("input_tokens", "output_tokens"):
            value = data.get(name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"cache entry field {name} is not an integer")
        return cls(
            text=data["text"],
            reported_model=data.get("reported_model"),
            finish_reason=data.get("finish_reason"),
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
        )


class CacheStore(Protocol):
    def get(self, key: str) -> CachedResponse | None:
        """Return a non-expired entry or ``None``. Must not raise on store failure."""
        ...

    def put(
        self,
        key: str,
        response: CachedResponse,
        *,
        ttl_seconds: int,
        provider_type: str,
        model: str,
    ) -> None:
        """Store unless a non-expired entry exists. Must not raise on store failure."""
        ...


def validate_ttl(ttl_seconds: int) -> int:
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise ConfigurationError("Cache TTL must be an integer number of seconds.")
    if not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
        raise ConfigurationError(f"Cache TTL must be between 1 and {MAX_TTL_SECONDS} seconds.")
    return ttl_seconds


@dataclass(frozen=True)
class CachePolicy:
    """Opt-in caching for one call site. ``namespace`` adds caller context to the key
    (e.g. ``{"evaluator": "l1", "evaluator_version": "3"}``)."""

    store: CacheStore
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    namespace: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_ttl(self.ttl_seconds)
        canonical_json(dict(self.namespace))  # must be JSON-serializable


class MemoryCacheStore:
    """Process-local store for tests and runs without a database."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, tuple[CachedResponse, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> CachedResponse | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry[1] <= self._clock():
                return None
            return entry[0]

    def put(
        self,
        key: str,
        response: CachedResponse,
        *,
        ttl_seconds: int,
        provider_type: str,
        model: str,
    ) -> None:
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None and existing[1] > self._clock():
                return  # first valid writer wins
            self._entries[key] = (response, self._clock() + ttl_seconds)

    def __len__(self) -> int:
        return len(self._entries)


class PostgresCacheStore:
    """``llm_cache_entries``. Expiry uses the database clock. Failures fail open."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def get(self, key: str) -> CachedResponse | None:
        try:
            with self._database.session() as session:
                row = session.execute(
                    text(
                        "SELECT response FROM llm_cache_entries "
                        "WHERE cache_key = :key AND expires_at > now()"
                    ),
                    {"key": key},
                ).scalar_one_or_none()
        except (DatabaseUnavailableError, SQLAlchemyError) as exc:
            _log_unavailable("get", exc)
            return None
        if row is None:
            return None
        try:
            return CachedResponse.from_json(row)
        except ValueError:
            # Fail open: a corrupt entry is a miss. It is not overwritten until it expires.
            logger.warning("cache.invalid_entry", extra={"forge": {"key_prefix": key[:12]}})
            return None

    def put(
        self,
        key: str,
        response: CachedResponse,
        *,
        ttl_seconds: int,
        provider_type: str,
        model: str,
    ) -> None:
        try:
            with self._database.session() as session:
                session.execute(
                    text(
                        "INSERT INTO llm_cache_entries "
                        "(cache_key, key_version, provider_type, model, response, created_at, expires_at) "
                        "VALUES (:key, :version, :provider_type, :model, CAST(:response AS jsonb), "
                        "now(), now() + make_interval(secs => :ttl)) "
                        "ON CONFLICT (cache_key) DO UPDATE SET "
                        "key_version = EXCLUDED.key_version, provider_type = EXCLUDED.provider_type, "
                        "model = EXCLUDED.model, response = EXCLUDED.response, "
                        "created_at = EXCLUDED.created_at, expires_at = EXCLUDED.expires_at "
                        "WHERE llm_cache_entries.expires_at <= now()"
                    ),
                    {
                        "key": key,
                        "version": CACHE_KEY_VERSION,
                        "provider_type": provider_type,
                        "model": model,
                        "response": json.dumps(response.to_json(), ensure_ascii=False),
                        "ttl": ttl_seconds,
                    },
                )
        except (DatabaseUnavailableError, SQLAlchemyError) as exc:
            _log_unavailable("put", exc)

    def purge_expired(self) -> int:
        """Delete expired entries (they are already ignored by ``get``). Returns the count."""
        with self._database.session() as session:
            result = session.execute(
                text("DELETE FROM llm_cache_entries WHERE expires_at <= now()")
            )
            return int(getattr(result, "rowcount", 0) or 0)


def postgres_cache_policy(
    database: Database, ttl_seconds: int, namespace: Mapping[str, Any] | None = None
) -> CachePolicy:
    """The standard policy for run executions: PostgreSQL store, configured TTL."""
    return CachePolicy(PostgresCacheStore(database), ttl_seconds, dict(namespace or {}))


def _log_unavailable(operation: str, exc: BaseException) -> None:
    logger.warning(
        "cache.unavailable",
        extra={"forge": {"operation": operation, "error_type": type(exc).__name__}},
    )
