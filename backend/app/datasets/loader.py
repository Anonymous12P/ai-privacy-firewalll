"""Placeholder interfaces for locating and loading datasets."""

import logging
from pathlib import Path

logger: logging.Logger = logging.getLogger(__name__)


class DatasetLoader:
    """Represent the future boundary for dataset loading."""

    def load(self, source: Path) -> object:
        """Load a dataset from a source after loading behavior is specified."""
        # TODO: Implement loading when dataset formats and requirements are known.
        logger.warning("Dataset loading is not implemented for source %s", source)
        raise NotImplementedError("Dataset loading is not implemented.")
