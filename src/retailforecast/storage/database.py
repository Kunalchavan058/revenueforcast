"""Database configuration and explicit unit-of-work construction."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[3]


class DatabaseSettings(BaseSettings):
    """Load a private host-side database URL without printing credentials."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        extra="ignore",
        env_prefix="",
    )
    database_url: SecretStr = Field(
        description="PostgreSQL psycopg URL, supplied through DATABASE_URL.",
    )


def utc_now() -> datetime:
    """Return an aware UTC timestamp for persisted events, not business dates."""
    return datetime.now(UTC)


def new_id() -> str:
    """Return an opaque identifier independent of database sequence state."""
    from uuid import uuid4

    return str(uuid4())


@lru_cache(maxsize=1)
def database_engine() -> Engine:
    """Create a lazy PostgreSQL engine; health does not call this function."""
    url = DatabaseSettings().database_url.get_secret_value()
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("DATABASE_URL must use postgresql+psycopg://")
    return create_engine(url, pool_pre_ping=True, hide_parameters=True)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Construct sessions; callers own begin/commit/rollback boundaries."""
    return sessionmaker(engine, expire_on_commit=False)
