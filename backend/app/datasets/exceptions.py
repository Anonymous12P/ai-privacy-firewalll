"""Domain-specific exceptions raised by dataset filesystem operations."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.datasets.schemas import ValidationResult


class DatasetError(Exception):
    """Base exception for dataset infrastructure failures."""


class DatasetDirectoryError(DatasetError):
    """Raised when the configured dataset directory is unavailable."""


class DatasetPathError(DatasetError, ValueError):
    """Raised when a requested dataset path is invalid or outside its root."""


class DatasetFileNotFoundError(DatasetError, FileNotFoundError):
    """Raised when one or more required dataset files are missing."""


class DatasetValidationError(DatasetError):
    """Raised when profiling is requested for a dataset that failed validation."""

    def __init__(self, message: str, validation_result: "ValidationResult") -> None:
        super().__init__(message)
        self.validation_result = validation_result


class DatasetProfileError(DatasetError):
    """Raised when a validated dataset cannot be profiled."""
