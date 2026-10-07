"""Reusable SQLAlchemy session factory."""

from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import engine

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)
