"""Exception hierarchy shared across FORGE."""


class ForgeError(Exception):
    """Base class for all FORGE errors."""


class ConfigurationError(ForgeError):
    """Required configuration is missing or invalid."""


class DatabaseUnavailableError(ForgeError):
    """The database could not be reached or the operation failed at the connection level.

    The message is safe to show to clients; the original exception (which may name hosts
    or users) is only kept as ``__cause__``.
    """

    def __init__(self, message: str = "The database is unavailable.") -> None:
        super().__init__(message)
