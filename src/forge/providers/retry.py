"""Bounded retry policy: exponential backoff with full jitter and ``Retry-After`` support."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from forge.providers.errors import ProviderError


@dataclass(frozen=True)
class RetryPolicy:
    """
    ``max_attempts`` counts the first call, so 3 means at most 2 retries. Only retryable
    error categories are retried. An upstream ``Retry-After`` is honored when it is at most
    ``max_retry_after_seconds``; a longer requested delay ends retrying immediately rather
    than holding the request open.
    """

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    max_retry_after_seconds: float = 20.0

    def delay_before_retry(
        self, error: ProviderError, attempt: int, rng: random.Random
    ) -> float | None:
        """Seconds to wait before the attempt after ``attempt`` (1-based), or ``None`` to stop."""
        if not error.retryable or attempt >= self.max_attempts:
            return None
        if error.retry_after is not None:
            if error.retry_after > self.max_retry_after_seconds:
                return None
            return error.retry_after
        ceiling = min(self.max_delay_seconds, self.base_delay_seconds * 2 ** (attempt - 1))
        return rng.uniform(0.0, ceiling)


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Parse an HTTP ``Retry-After`` value (delta-seconds or HTTP-date) into seconds.

    Returns ``None`` for missing or invalid values; dates in the past give ``0.0``.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        if math.isnan(seconds) or math.isinf(seconds) or seconds < 0:
            return None
        return seconds
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0.0, (when - now).total_seconds())
