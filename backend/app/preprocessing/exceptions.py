"""Typed errors raised by preprocessing configuration and planning."""


class PreprocessingError(Exception):
    """Base exception for preprocessing infrastructure."""


class PreprocessingConfigError(PreprocessingError, ValueError):
    """Raised when a preprocessing YAML file is absent or invalid."""


class CleaningPlanError(PreprocessingError):
    """Raised when a safe cleaning plan cannot be created."""


class CleaningExecutionError(PreprocessingError):
    """Raised when plan execution or safe artifact persistence fails."""
