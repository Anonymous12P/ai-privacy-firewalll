"""Placeholder orchestration boundary for future dataset workflows."""

import logging
from pathlib import Path

logger: logging.Logger = logging.getLogger(__name__)


class DatasetPipeline:
    """Represent the future coordinator for dataset workflow stages."""

    def run(self, source: Path) -> None:
        """Run a dataset workflow after its stages are implemented."""
        # TODO: Coordinate loading, validation, and storage when specified.
        logger.warning("Dataset pipeline is not implemented for source %s", source)
        raise NotImplementedError("Dataset pipeline is not implemented.")
