"""Filesystem-only discovery and validation for dataset files."""

import logging
from collections.abc import Iterable
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.constants import APP_LOGGER_NAME
from app.datasets.exceptions import (
    DatasetDirectoryError,
    DatasetFileNotFoundError,
    DatasetPathError,
)

logger: logging.Logger = logging.getLogger(f"{APP_LOGGER_NAME}.datasets.loader")


class DatasetLoader:
    """Discover and validate files within one configured dataset directory.

    The loader performs filesystem operations only; it does not open or parse
    dataset contents.
    """

    def __init__(
        self,
        data_dir: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize the loader for a configured data directory."""
        configured_settings = settings or get_settings()
        selected_dir = data_dir or configured_settings.raw_data_dir
        self.data_dir = selected_dir.expanduser().resolve()
        self._validate_directory()
        logger.info("Dataset loader initialized for %s", self.data_dir)

    def _validate_directory(self) -> None:
        """Ensure the selected dataset directory exists and is a directory."""
        if not self.data_dir.exists():
            logger.error("Dataset directory does not exist: %s", self.data_dir)
            raise DatasetDirectoryError(
                f"Dataset directory does not exist: {self.data_dir}"
            )
        if not self.data_dir.is_dir():
            logger.error("Dataset path is not a directory: %s", self.data_dir)
            raise DatasetDirectoryError(
                f"Dataset path is not a directory: {self.data_dir}"
            )

    def _resolve_filename(self, filename: str | Path) -> Path:
        """Resolve a relative dataset filename and prevent escaping the root."""
        relative_path = Path(filename)
        if (
            not str(filename).strip()
            or relative_path.is_absolute()
            or relative_path.name in {"", ".", ".."}
        ):
            raise DatasetPathError("Dataset filename must be a non-empty relative path.")

        resolved_path = (self.data_dir / relative_path).resolve()
        if not resolved_path.is_relative_to(self.data_dir):
            raise DatasetPathError(
                f"Dataset path must remain within {self.data_dir}: {filename}"
            )
        return resolved_path

    def dataset_exists(self, filename: str | Path) -> bool:
        """Return whether a regular file exists for the requested dataset."""
        dataset_path = self._resolve_filename(filename)
        exists = dataset_path.is_file()
        if not exists:
            logger.warning("Dataset file does not exist: %s", dataset_path)
        return exists

    def list_available_files(self) -> list[Path]:
        """List regular files directly inside the configured data directory."""
        files = sorted(
            (
                path
                for path in self.data_dir.iterdir()
                if path.is_file() and path.resolve().is_relative_to(self.data_dir)
            ),
            key=lambda path: path.name.casefold(),
        )
        logger.info(
            "Discovered %d dataset file(s) in %s",
            len(files),
            self.data_dir,
        )
        return files

    def get_dataset_path(self, filename: str | Path) -> Path:
        """Return a safe filesystem path for a dataset filename."""
        return self._resolve_filename(filename)

    def validate_required_files(
        self,
        required_files: Iterable[str | Path],
    ) -> tuple[Path, ...]:
        """Confirm all required files exist, raising a typed error otherwise."""
        required_paths = tuple(
            self._resolve_filename(filename) for filename in required_files
        )
        missing_paths = tuple(path for path in required_paths if not path.is_file())
        if missing_paths:
            missing_names = tuple(
                str(path.relative_to(self.data_dir)) for path in missing_paths
            )
            logger.error(
                "Required dataset file(s) are missing from %s: %s",
                self.data_dir,
                ", ".join(missing_names),
            )
            raise DatasetFileNotFoundError(
                f"Required dataset file(s) are missing from {self.data_dir}: "
                f"{', '.join(missing_names)}"
            )

        logger.info(
            "Validated %d required dataset file(s) in %s",
            len(required_paths),
            self.data_dir,
        )
        return required_paths
