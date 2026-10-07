"""Application settings loaded from environment variables and backend/.env."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import (
    DEFAULT_APP_ENV,
    DEFAULT_APP_NAME,
    DEFAULT_APP_VERSION,
    DEFAULT_DEBUG,
    DEFAULT_LOG_LEVEL,
)

BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Validated application settings."""

    app_name: str = DEFAULT_APP_NAME
    app_version: str = DEFAULT_APP_VERSION
    app_env: str = DEFAULT_APP_ENV
    debug: bool = DEFAULT_DEBUG
    log_level: str = DEFAULT_LOG_LEVEL
    database_url: str = Field(
    ...,
    alias="DATABASE_URL",
)

    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
