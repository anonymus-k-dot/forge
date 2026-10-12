import random
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from forge.errors import ConfigurationError
from forge.providers import errors
from forge.providers.retry import RetryPolicy, parse_retry_after

from .helpers import MaxRng


class TestErrorForStatus:
    @pytest.mark.parametrize(
        ("status", "cls", "retryable"),
        [
            (400, errors.InvalidRequestError, False),
            (401, errors.AuthenticationError, False),
            (403, errors.AuthenticationError, False),
            (404, errors.InvalidRequestError, False),
            (408, errors.ProviderTimeoutError, True),
            (422, errors.InvalidRequestError, False),
            (429, errors.RateLimitError, True),
            (500, errors.UpstreamServerError, True),
            (502, errors.UpstreamServerError, True),
            (503, errors.ProviderUnavailableError, True),
            (504, errors.UpstreamServerError, True),
            (302, errors.UnknownProviderError, False),
        ],
    )
    def test_mapping(self, status, cls, retryable):
        error = errors.error_for_status(status, provider="p", retry_after=3.0)
        assert type(error) is cls
        assert error.retryable is retryable
        assert error.status_code == status
        assert error.retry_after == 3.0
        assert error.provider == "p"

    def test_internal_message_has_no_upstream_text(self):
        assert str(errors.error_for_status(500, provider="p")) == "p: upstream HTTP 500"


class TestSafeMessages:
    def test_every_category_has_a_stable_message(self):
        for cls in (
            errors.AuthenticationError,
            errors.InvalidRequestError,
            errors.RateLimitError,
            errors.ProviderUnavailableError,
            errors.ConcurrencyLimitError,
            errors.ProviderTimeoutError,
            errors.UpstreamServerError,
            errors.MalformedResponseError,
            errors.UnsupportedCapabilityError,
            errors.UnknownProviderError,
        ):
            error = cls("internal detail: secret-token-123")
            assert error.safe_message and "secret-token-123" not in error.safe_message

    def test_frontend_keywords_are_present(self):
        # The legacy UI maps messages containing these words to friendly text.
        assert "rate_limit" in errors.RateLimitError("x").safe_message
        assert "timeout" in errors.ProviderTimeoutError("x").safe_message

    def test_configuration_error_message_is_shown_and_is_a_configuration_error(self):
        error = errors.ProviderConfigurationError("GEMINI_API_KEY is not set.")
        assert error.safe_message == "GEMINI_API_KEY is not set."
        assert isinstance(error, ConfigurationError)
        assert not error.retryable

    def test_concurrency_error_is_unavailable_category(self):
        assert errors.ConcurrencyLimitError("x").category is errors.ErrorCategory.UNAVAILABLE


class TestParseRetryAfter:
    NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("5", 5.0),
            (" 2.5 ", 2.5),
            ("0", 0.0),
            (None, None),
            ("", None),
            ("soon", None),
            ("-3", None),
            ("nan", None),
            ("inf", None),
        ],
    )
    def test_seconds_and_invalid(self, value, expected):
        assert parse_retry_after(value, now=self.NOW) == expected

    def test_http_date(self):
        value = format_datetime(self.NOW + timedelta(seconds=30), usegmt=True)
        assert parse_retry_after(value, now=self.NOW) == pytest.approx(30.0)

    def test_http_date_in_past_is_zero(self):
        value = format_datetime(self.NOW - timedelta(seconds=30), usegmt=True)
        assert parse_retry_after(value, now=self.NOW) == 0.0


class TestRetryPolicy:
    policy = RetryPolicy(
        max_attempts=4, base_delay_seconds=1.0, max_delay_seconds=3.0, max_retry_after_seconds=10.0
    )

    def test_exponential_backoff_is_capped(self):
        error = errors.UpstreamServerError("x")
        delays = [self.policy.delay_before_retry(error, attempt, MaxRng()) for attempt in (1, 2, 3)]
        assert delays == [1.0, 2.0, 3.0]

    def test_full_jitter_stays_within_bounds(self):
        rng = random.Random(1234)
        error = errors.ProviderTimeoutError("x")
        for attempt in (1, 2, 3):
            delay = self.policy.delay_before_retry(error, attempt, rng)
            assert 0.0 <= delay <= min(3.0, 2 ** (attempt - 1))

    def test_stops_after_max_attempts(self):
        assert self.policy.delay_before_retry(errors.UpstreamServerError("x"), 4, MaxRng()) is None

    @pytest.mark.parametrize(
        "error",
        [
            errors.AuthenticationError("x"),
            errors.InvalidRequestError("x"),
            errors.MalformedResponseError("x"),
            errors.UnknownProviderError("x"),
            errors.ProviderConfigurationError("x"),
            errors.UnsupportedCapabilityError("x"),
        ],
    )
    def test_permanent_errors_are_not_retried(self, error):
        assert self.policy.delay_before_retry(error, 1, MaxRng()) is None

    def test_retry_after_is_used_exactly(self):
        error = errors.RateLimitError("x", retry_after=7.5)
        assert self.policy.delay_before_retry(error, 1, MaxRng()) == 7.5

    def test_unreasonable_retry_after_stops_retrying(self):
        error = errors.RateLimitError("x", retry_after=3600)
        assert self.policy.delay_before_retry(error, 1, MaxRng()) is None
