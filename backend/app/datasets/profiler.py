"""Read-only, streaming profiling of validated CSV datasets."""

import csv
import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.core.constants import APP_LOGGER_NAME
from app.datasets.exceptions import DatasetProfileError
from app.datasets.schemas import ColumnProfile, DatasetProfile, ProfileReport

logger: logging.Logger = logging.getLogger(f"{APP_LOGGER_NAME}.datasets.profiler")
TOP_VALUE_LIMIT = 10


@dataclass
class _ColumnAccumulator:
    """Mutable counters used while streaming a CSV column."""

    integer_only: bool = True
    numeric_only: bool = True
    missing_count: int = 0
    distinct_values: set[str] = field(default_factory=set)
    value_counts: Counter[str] = field(default_factory=Counter)
    numeric_count: int = 0
    numeric_sum: float = 0.0
    minimum: float | int | None = None
    maximum: float | int | None = None

    def add(self, value: str) -> None:
        """Accumulate one cell without retaining the source row."""
        normalized = value.strip()
        if not normalized:
            self.missing_count += 1
            return

        self.distinct_values.add(value)
        self.value_counts[value] += 1

        try:
            parsed_integer = int(normalized)
        except ValueError:
            self.integer_only = False
            try:
                parsed_number = float(normalized)
            except ValueError:
                self.numeric_only = False
                return
            if not math.isfinite(parsed_number):
                self.numeric_only = False
                return
            numeric_value: float | int = parsed_number
        else:
            numeric_value = parsed_integer

        self.numeric_count += 1
        self.numeric_sum += float(numeric_value)
        if self.minimum is None or numeric_value < self.minimum:
            self.minimum = numeric_value
        if self.maximum is None or numeric_value > self.maximum:
            self.maximum = numeric_value

    def to_profile(self, name: str) -> ColumnProfile:
        """Create an immutable profile from accumulated cell statistics."""
        if self.distinct_values and self.numeric_only:
            data_type = "integer" if self.integer_only else "float"
            numeric_count = self.numeric_count
            minimum = self.minimum
            maximum = self.maximum
            mean = self.numeric_sum / numeric_count if numeric_count else None
            top_values: tuple[tuple[str, int], ...] = ()
        elif self.distinct_values:
            data_type = "string"
            numeric_count = 0
            minimum = None
            maximum = None
            mean = None
            top_values = tuple(
                sorted(
                    self.value_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:TOP_VALUE_LIMIT]
            )
        else:
            data_type = "empty"
            numeric_count = 0
            minimum = None
            maximum = None
            mean = None
            top_values = ()

        return ColumnProfile(
            name=name,
            data_type=data_type,
            missing_count=self.missing_count,
            distinct_count=len(self.distinct_values),
            numeric_count=numeric_count,
            minimum=minimum,
            maximum=maximum,
            mean=mean,
            top_values=top_values,
        )


class DatasetProfiler:
    """Compute descriptive statistics without changing source CSV files."""

    def profile(
        self,
        dataset_name: str,
        files: tuple[Path, ...],
    ) -> ProfileReport:
        """Profile validated CSV files and return an aggregate typed report."""
        logger.info("Dataset profiling started for %s", dataset_name)
        profiles: list[DatasetProfile] = []
        warnings: list[str] = []

        for file_path in files:
            if file_path.suffix.casefold() != ".csv":
                warnings.append(
                    f"Skipped non-CSV validated file: {file_path.name}"
                )
                continue
            logger.info("Dataset loaded for profiling: %s", file_path)
            try:
                profiles.append(self._profile_csv(file_path))
            except (OSError, UnicodeError, csv.Error, DatasetProfileError) as exc:
                logger.exception("Unable to profile dataset file %s", file_path)
                raise DatasetProfileError(
                    f"Unable to profile dataset file {file_path}: {exc}"
                ) from exc

        if not profiles:
            warnings.append("No validated CSV files were available for profiling.")

        summary = {
            "file_count": len(profiles),
            "row_count": sum(profile.row_count for profile in profiles),
            "column_count": sum(profile.column_count for profile in profiles),
            "missing_values": sum(profile.missing_values for profile in profiles),
            "duplicate_rows": sum(profile.duplicate_rows for profile in profiles),
        }
        recommendations = self._recommendations(summary)
        report = ProfileReport(
            dataset_name=dataset_name,
            summary=summary,
            statistics=tuple(profiles),
            warnings=tuple(warnings),
            recommendations=recommendations,
        )
        logger.info(
            "Dataset profiling completed for %s: files=%d, rows=%d",
            dataset_name,
            summary["file_count"],
            summary["row_count"],
        )
        return report

    @staticmethod
    def _profile_csv(file_path: Path) -> DatasetProfile:
        """Profile a CSV by iterating records once from disk."""
        with file_path.open(mode="r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.reader(csv_file)
            headers = next(reader, None)
            if not headers:
                raise DatasetProfileError(f"CSV file has no header row: {file_path}")

            column_states = [_ColumnAccumulator() for _ in headers]
            seen_rows: set[tuple[str, ...]] = set()
            row_count = 0
            duplicate_rows = 0
            missing_values = 0

            for row_number, row in enumerate(reader, start=2):
                if len(row) > len(headers):
                    raise DatasetProfileError(
                        f"CSV row {row_number} in {file_path} has more values "
                        f"than its header."
                    )
                record = tuple(
                    row[index] if index < len(row) else ""
                    for index in range(len(headers))
                )
                row_count += 1
                if record in seen_rows:
                    duplicate_rows += 1
                else:
                    seen_rows.add(record)

                for state, value in zip(column_states, record):
                    state.add(value)
                    if not value.strip():
                        missing_values += 1

        return DatasetProfile(
            file=file_path,
            row_count=row_count,
            column_count=len(headers),
            missing_values=missing_values,
            duplicate_rows=duplicate_rows,
            columns=tuple(
                state.to_profile(name)
                for state, name in zip(column_states, headers)
            ),
        )

    @staticmethod
    def _recommendations(summary: dict[str, int]) -> tuple[str, ...]:
        """Suggest follow-up review without changing or cleaning source data."""
        recommendations: list[str] = []
        if summary["missing_values"]:
            recommendations.append(
                "Review missing-value patterns before designing any cleaning policy."
            )
        if summary["duplicate_rows"]:
            recommendations.append(
                "Review duplicate rows and decide whether they are meaningful."
            )
        if summary["file_count"] == 0:
            recommendations.append(
                "Provide validated CSV files before requesting a profile."
            )
        return tuple(recommendations)
