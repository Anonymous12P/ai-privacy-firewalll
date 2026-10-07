"""Placeholder interfaces for validating datasets."""

import logging

logger: logging.Logger = logging.getLogger(__name__)


class DatasetValidator:
    """Represent the future boundary for dataset validation."""

    def validate(self, dataset: object) -> None:
        """Validate a dataset after validation requirements are specified."""
        # TODO: Define and implement validation rules when requirements are known.
        logger.warning("Dataset validation is not implemented.")
        raise NotImplementedError("Dataset validation is not implemented.")
