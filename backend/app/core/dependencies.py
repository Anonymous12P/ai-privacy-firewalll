"""Reusable FastAPI dependency providers for core infrastructure."""

import logging

from app.core.config import Settings, get_settings
from app.core.constants import APP_LOGGER_NAME


def get_settings_dependency() -> Settings:
    """Provide the cached application settings."""
    return get_settings()


def get_application_logger() -> logging.Logger:
    """Provide the centralized application logger."""
    return logging.getLogger(APP_LOGGER_NAME)
