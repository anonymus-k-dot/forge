"""Normalized provider errors.

Every adapter converts provider-specific failures into one of these classes. Each class
carries a stable, secret-free ``safe_message`` for clients; the internal message names the
provider and HTTP status only, and the original exception is kept as ``__cause__``.
"""

from __future__ import annotations

from enum import Enum

from forge.errors import ConfigurationError, ForgeError


class ErrorCategory(str, Enum):
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"
    RATE_LIMIT = "rate_limit"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    MALFORMED_RESPONSE = "malformed_response"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    UNKNOWN = "unknown"


RETRYABLE_CATEGORIES = frozenset(
    {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.UNAVAILABLE,
        ErrorCategory.TIMEOUT,
        ErrorCategory.SERVER_ERROR,
    }
)


class ProviderError(ForgeError):
    """A model-provider failure, classified into an ``ErrorCategory``."""

    category = ErrorCategory.UNKNOWN
    client_message = "The model provider request failed unexpectedly."

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.category in RETRYABLE_CATEGORIES

    @property
    def safe_message(self) -> str:
        """Stable message that is safe to show to clients."""
        return self.client_message


class ProviderConfigurationError(ProviderError, ConfigurationError):
    """Provider is missing configuration (for example an unset credential variable).

    Messages are written by FORGE, name variables but never their values, and are shown
    to clients as-is.
    """

    category = ErrorCategory.CONFIGURATION

    @property
    def safe_message(self) -> str:
        return str(self)


class AuthenticationError(ProviderError):
    category = ErrorCategory.AUTHENTICATION
    client_message = "The model provider rejected the server's credentials."


class InvalidRequestError(ProviderError):
    category = ErrorCategory.INVALID_REQUEST
    client_message = "The model provider rejected the request as invalid."


class RateLimitError(ProviderError):
    category = ErrorCategory.RATE_LIMIT
    client_message = (
        "The model provider's rate limit was reached (rate_limit). Please wait and try again."
    )


class ProviderUnavailableError(ProviderError):
    category = ErrorCategory.UNAVAILABLE
    client_message = "The model provider is currently unavailable. Please try again later."


class ConcurrencyLimitError(ProviderUnavailableError):
    """Raised locally when no concurrency slot frees up in time; never retried."""

    client_message = (
        "Too many requests are in progress for this model provider. Please try again shortly."
    )


class ProviderTimeoutError(ProviderError):
    category = ErrorCategory.TIMEOUT
    client_message = "The model provider did not respond in time (timeout). Please try again."


class UpstreamServerError(ProviderError):
    category = ErrorCategory.SERVER_ERROR
    client_message = "The model provider returned a server error. Please try again later."


class MalformedResponseError(ProviderError):
    category = ErrorCategory.MALFORMED_RESPONSE
    client_message = "The model provider returned an invalid response."


class UnsupportedCapabilityError(ProviderError):
    category = ErrorCategory.UNSUPPORTED_CAPABILITY
    client_message = "The selected model does not support this request."


class UnknownProviderError(ProviderError):
    category = ErrorCategory.UNKNOWN


def error_for_status(
    status_code: int, *, provider: str, retry_after: float | None = None
) -> ProviderError:
    """Map an HTTP status code from an upstream API to a normalized error."""
    message = f"{provider}: upstream HTTP {status_code}"
    cls: type[ProviderError]
    if status_code in (401, 403):
        cls = AuthenticationError
    elif status_code == 408:
        cls = ProviderTimeoutError
    elif status_code == 429:
        cls = RateLimitError
    elif status_code == 503:
        cls = ProviderUnavailableError
    elif 400 <= status_code < 500:
        cls = InvalidRequestError
    elif 500 <= status_code < 600:
        cls = UpstreamServerError
    else:
        cls = UnknownProviderError
    return cls(message, provider=provider, status_code=status_code, retry_after=retry_after)
