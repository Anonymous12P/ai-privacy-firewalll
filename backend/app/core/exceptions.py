"""Reusable application exception types.

These exceptions are not registered as FastAPI exception handlers.
"""


class ApplicationError(Exception):
    """Base class for expected application-level errors."""

    def __init__(self, message: str, *, code: str = "application_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ConfigurationError(ApplicationError):
    """Raised when application configuration is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="configuration_error")


class InfrastructureError(ApplicationError):
    """Raised when a shared infrastructure operation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="infrastructure_error")
