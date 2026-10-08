"""Typed data contracts for dataset manifests and validation outcomes."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class DatasetManifest:
    """Describe the files and CSV headers expected in a dataset."""

    name: str
    required_files: tuple[str, ...] = ()
    allowed_extensions: tuple[str, ...] = (".csv",)
    required_columns: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetSchema:
    """Identify a future dataset schema without defining dataset fields."""

    name: str
    version: str

    # TODO: Add schema fields after dataset contracts are agreed upon.


@dataclass(frozen=True)
class ValidationIssue:
    """Describe a single dataset validation warning or error."""

    code: str
    message: str
    severity: Literal["warning", "error"]
    file: Path | None = None


@dataclass(frozen=True)
class ValidationResult:
    """Aggregate the outcome and evidence from one validation run."""

    success: bool
    warnings: tuple[ValidationIssue, ...]
    errors: tuple[ValidationIssue, ...]
    checked_files: tuple[Path, ...]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass(frozen=True)
class ColumnProfile:
    """Summarize observed values and statistics for one CSV column."""

    name: str
    data_type: Literal["integer", "float", "string", "empty"]
    missing_count: int
    distinct_count: int
    numeric_count: int = 0
    minimum: float | int | None = None
    maximum: float | int | None = None
    mean: float | None = None
    top_values: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class DatasetProfile:
    """Profile summary for one validated CSV file."""

    file: Path
    row_count: int
    column_count: int
    missing_values: int
    duplicate_rows: int
    columns: tuple[ColumnProfile, ...]


@dataclass(frozen=True)
class ProfileReport:
    """Dataset-level profiling report ready for serialization."""

    dataset_name: str
    summary: dict[str, int]
    statistics: tuple[DatasetProfile, ...]
    warnings: tuple[str, ...]
    recommendations: tuple[str, ...]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
