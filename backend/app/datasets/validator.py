"""Header-only validation for dataset files and directory structure."""

import csv
import logging
from pathlib import Path

from app.core.config import get_settings
from app.core.constants import APP_LOGGER_NAME
from app.datasets.exceptions import (
    DatasetDirectoryError,
    DatasetPathError,
)
from app.datasets.loader import DatasetLoader
from app.datasets.schemas import (
    DatasetManifest,
    ValidationIssue,
    ValidationResult,
)

logger: logging.Logger = logging.getLogger(f"{APP_LOGGER_NAME}.datasets.validator")


class DatasetValidator:
    """Validate dataset structure and CSV headers without loading row data."""

    def __init__(
        self,
        loader: DatasetLoader | None = None,
        data_dir: Path | None = None,
    ) -> None:
        """Configure validation to use a loader or a dataset directory."""
        if loader is not None and data_dir is not None:
            raise ValueError("Provide either loader or data_dir, not both.")
        self.loader = loader
        self.data_dir = (
            data_dir
            if data_dir is not None
            else loader.data_dir
            if loader is not None
            else get_settings().raw_data_dir
        )

    def validate(self, manifest: DatasetManifest) -> ValidationResult:
        """Validate files and required CSV headers described by a manifest."""
        logger.info("Dataset validation started for %s", manifest.name)
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        checked_files: list[Path] = []

        loader = self.loader
        if loader is None:
            try:
                loader = DatasetLoader(data_dir=self.data_dir)
            except DatasetDirectoryError as exc:
                errors.append(
                    ValidationIssue(
                        code="invalid_dataset_directory",
                        message=str(exc),
                        severity="error",
                    )
                )
                return self._result(manifest, errors, warnings, checked_files)

        discovered_files = tuple(
            path for path in loader.list_available_files() if path.name != ".gitkeep"
        )
        if not discovered_files:
            errors.append(
                ValidationIssue(
                    code="empty_dataset_directory",
                    message=f"Dataset directory contains no files: {loader.data_dir}",
                    severity="error",
                )
            )

        required_paths: dict[Path, str] = {}
        for filename in manifest.required_files:
            try:
                required_path = loader.get_dataset_path(filename)
            except DatasetPathError as exc:
                errors.append(
                    ValidationIssue(
                        code="invalid_required_file_path",
                        message=str(exc),
                        severity="error",
                    )
                )
                continue

            required_paths[required_path] = filename
            if not loader.dataset_exists(filename):
                errors.append(
                    ValidationIssue(
                        code="missing_required_file",
                        message=f"Required dataset file is missing: {filename}",
                        severity="error",
                        file=required_path,
                    )
                )

        files_to_check = tuple(
            sorted(
                set(discovered_files).union(
                    path for path in required_paths if path.is_file()
                ),
                key=lambda path: str(path).casefold(),
            )
        )
        allowed_extensions = {
            extension.casefold()
            if extension.startswith(".")
            else f".{extension.casefold()}"
            for extension in manifest.allowed_extensions
        }
        if not allowed_extensions:
            errors.append(
                ValidationIssue(
                    code="no_allowed_extensions",
                    message="The manifest must define at least one allowed extension.",
                    severity="error",
                )
            )

        for file_path in files_to_check:
            checked_files.append(file_path)
            logger.info("Validating dataset file %s", file_path)
            if file_path.suffix.casefold() not in allowed_extensions:
                errors.append(
                    ValidationIssue(
                        code="invalid_file_extension",
                        message=(
                            f"File extension {file_path.suffix or '(none)'} is not "
                            f"allowed for {file_path.name}."
                        ),
                        severity="error",
                        file=file_path,
                    )
                )

            try:
                is_empty = file_path.stat().st_size == 0
            except OSError as exc:
                errors.append(
                    ValidationIssue(
                        code="file_access_error",
                        message=f"Unable to inspect {file_path}: {exc}",
                        severity="error",
                        file=file_path,
                    )
                )
                continue

            if is_empty:
                errors.append(
                    ValidationIssue(
                        code="empty_file",
                        message=f"Dataset file is empty: {file_path.name}",
                        severity="error",
                        file=file_path,
                    )
                )
                continue

            if file_path.suffix.casefold() != ".csv":
                continue

            try:
                with file_path.open(
                    mode="r",
                    encoding="utf-8-sig",
                    newline="",
                ) as csv_file:
                    headers = next(csv.reader(csv_file), [])
            except (OSError, UnicodeError, csv.Error) as exc:
                errors.append(
                    ValidationIssue(
                        code="csv_header_read_error",
                        message=f"Unable to read CSV header from {file_path}: {exc}",
                        severity="error",
                        file=file_path,
                    )
                )
                continue

            if not headers:
                errors.append(
                    ValidationIssue(
                        code="missing_csv_header",
                        message=f"CSV file has no header row: {file_path.name}",
                        severity="error",
                        file=file_path,
                    )
                )
                continue

            expected_columns = self._required_columns_for_file(
                file_path,
                loader.data_dir,
                manifest.required_columns,
                required_paths,
            )
            if not expected_columns:
                warnings.append(
                    ValidationIssue(
                        code="required_columns_not_configured",
                        message=(
                            f"No required columns are configured for "
                            f"{file_path.name}; only the CSV header row was checked."
                        ),
                        severity="warning",
                        file=file_path,
                    )
                )
                continue

            missing_columns = tuple(
                column for column in expected_columns if column not in headers
            )
            if missing_columns:
                errors.append(
                    ValidationIssue(
                        code="missing_required_columns",
                        message=(
                            f"{file_path.name} is missing required column(s): "
                            f"{', '.join(missing_columns)}"
                        ),
                        severity="error",
                        file=file_path,
                    )
                )

        result = self._result(manifest, errors, warnings, checked_files)
        return result

    @staticmethod
    def _required_columns_for_file(
        file_path: Path,
        data_dir: Path,
        required_columns: dict[str, tuple[str, ...]],
        required_paths: dict[Path, str],
    ) -> tuple[str, ...]:
        """Return manifest columns keyed by relative path or required filename."""
        relative_name = file_path.relative_to(data_dir).as_posix()
        configured_name = required_paths.get(file_path)
        return required_columns.get(
            relative_name,
            required_columns.get(configured_name or file_path.name, ()),
        )

    @staticmethod
    def _result(
        manifest: DatasetManifest,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
        checked_files: list[Path],
    ) -> ValidationResult:
        """Log and return the aggregated result for a validation run."""
        for warning in warnings:
            logger.warning("%s: %s", warning.code, warning.message)
        for error in errors:
            logger.error("%s: %s", error.code, error.message)

        result = ValidationResult(
            success=not errors,
            warnings=tuple(warnings),
            errors=tuple(errors),
            checked_files=tuple(checked_files),
        )
        logger.info(
            "Dataset validation completed for %s: success=%s, files_checked=%d",
            manifest.name,
            result.success,
            len(result.checked_files),
        )
        return result
