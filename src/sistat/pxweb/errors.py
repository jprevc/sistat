class PxWebError(Exception):
    """Base class for all errors raised by this package."""


class APIError(PxWebError):
    """The server returned an error response."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class QueryError(PxWebError, ValueError):
    """A selection does not match the table's variables or values."""
