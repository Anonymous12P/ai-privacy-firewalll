"""Public interfaces for the dataset architecture."""

from app.datasets.loader import DatasetLoader
from app.datasets.pipeline import DatasetPipeline
from app.datasets.validator import DatasetValidator
from app.datasets.exceptions import (
    DatasetDirectoryError,
    DatasetError,
    DatasetFileNotFoundError,
    DatasetPathError,
)
from app.datasets.profiler import DatasetProfiler
from app.datasets.report_generator import ProfileReportGenerator
from app.datasets.exceptions import DatasetProfileError, DatasetValidationError
from app.datasets.schemas import (
    ColumnProfile,
    DatasetManifest,
    DatasetProfile,
    DatasetSchema,
    ProfileReport,
    ValidationIssue,
    ValidationResult,
)

# TODO: Expand the public API when concrete dataset requirements are defined.
__all__: tuple[str, ...] = (
    "DatasetDirectoryError",
    "DatasetError",
    "DatasetFileNotFoundError",
    "DatasetLoader",
    "DatasetManifest",
    "DatasetPathError",
    "DatasetPipeline",
    "DatasetProfile",
    "DatasetProfileError",
    "DatasetProfiler",
    "DatasetSchema",
    "DatasetValidator",
    "DatasetValidationError",
    "ColumnProfile",
    "ProfileReport",
    "ProfileReportGenerator",
    "ValidationIssue",
    "ValidationResult",
)
