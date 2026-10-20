"""Private tracking settings and explicit isolated-test backend selection."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from retailforecast.storage.database import ROOT, DatabaseSettings


class TrackingSettings(BaseSettings):
    """Read credentials only from ignored environment settings."""

    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    mlflow_tracking_uri: SecretStr


def tracking_uri(root: Path) -> str:
    """Require distinct PostgreSQL databases; tests must explicitly opt into SQLite."""
    if os.environ.get("RETAILFORECAST_TEST_MLFLOW_SQLITE") == "1":
        return "sqlite:///" + (root / "metadata.db").resolve().as_posix()
    uri = TrackingSettings().mlflow_tracking_uri.get_secret_value()
    tracking = make_url(uri)
    business = make_url(DatabaseSettings().database_url.get_secret_value())
    if (
        tracking.drivername != "postgresql+psycopg"
        or tracking.database == business.database
        or tracking.username == business.username
    ):
        raise ValueError(
            "MLflow requires postgresql+psycopg and a distinct metadata database/login"
        )
    return uri
