"""Centralized standard-library logging configuration."""

import logging

from app.core.constants import APP_LOGGER_NAME, LOG_FORMAT


def configure_logging(log_level: str) -> logging.Logger:
    """Configure root logging and return the application logger."""
    level = getattr(logging, log_level.upper(), None)
    if not isinstance(level, int):
        raise ValueError(f"Invalid logging level: {log_level}")

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.setFormatter(logging.Formatter(LOG_FORMAT))
            handler.setLevel(level)

    return logging.getLogger(APP_LOGGER_NAME)
