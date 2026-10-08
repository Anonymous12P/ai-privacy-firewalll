"""Safe loading and validation for preprocessing YAML configuration."""

import logging
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from app.core.constants import APP_LOGGER_NAME
from app.preprocessing.cleaning_policy import CleaningPolicy, PreprocessingConfig
from app.preprocessing.exceptions import PreprocessingConfigError

logger: logging.Logger = logging.getLogger(
    f"{APP_LOGGER_NAME}.preprocessing.config"
)
ModelT = TypeVar("ModelT", bound=BaseModel)


def _load_model(path: Path, model_type: type[ModelT]) -> ModelT:
    """Load one YAML mapping into a strict typed model."""
    config_path = path.expanduser().resolve()
    if not config_path.is_file():
        logger.error("Preprocessing configuration file is missing: %s", config_path)
        raise PreprocessingConfigError(
            f"Preprocessing configuration file does not exist: {config_path}"
        )

    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            payload = yaml.safe_load(config_file)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        logger.exception("Unable to load preprocessing configuration %s", config_path)
        raise PreprocessingConfigError(
            f"Unable to load preprocessing configuration {config_path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise PreprocessingConfigError(
            f"Configuration must contain a YAML mapping: {config_path}"
        )

    try:
        model = model_type.model_validate(payload)
    except ValidationError as exc:
        logger.error("Invalid preprocessing configuration %s: %s", config_path, exc)
        raise PreprocessingConfigError(
            f"Invalid preprocessing configuration {config_path}: {exc}"
        ) from exc

    logger.info("Loaded preprocessing configuration from %s", config_path)
    return model


def load_cleaning_policy(path: Path) -> CleaningPolicy:
    """Load and validate a YAML cleaning policy."""
    return _load_model(path, CleaningPolicy)


def load_preprocessing_config(path: Path) -> PreprocessingConfig:
    """Load and validate preprocessing planning settings."""
    return _load_model(path, PreprocessingConfig)
