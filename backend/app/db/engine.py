"""Reusable SQLAlchemy engine configuration."""

from sqlalchemy import Engine, create_engine

from app.core.config import get_settings

settings = get_settings()
engine: Engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)
