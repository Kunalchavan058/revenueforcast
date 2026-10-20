"""Provision a distinct local MLflow role/database without exposing credentials."""

from __future__ import annotations

import secrets

import psycopg
from dotenv import dotenv_values, set_key
from psycopg import sql
from sqlalchemy.engine import make_url

from retailforecast.storage.database import ROOT, DatabaseSettings

DATABASE_NAME = "retailforecast_mlflow"
ROLE_NAME = "retailforecast_mlflow"


def main() -> None:
    """Create missing resources idempotently; never replace an existing tracking password."""
    path = ROOT / ".env"
    existing = dotenv_values(path).get("MLFLOW_TRACKING_URI")
    business = make_url(DatabaseSettings().database_url.get_secret_value())
    tracking = (
        make_url(existing)
        if existing and "replace_" not in existing
        else business.set(
            username=ROLE_NAME, password=secrets.token_hex(24), database=DATABASE_NAME
        )
    )
    if (
        tracking.database != DATABASE_NAME
        or tracking.username != ROLE_NAME
        or tracking.drivername != "postgresql+psycopg"
        or business.host not in ("127.0.0.1", "localhost")
        or tracking.host != business.host
        or tracking.port != business.port
    ):
        raise ValueError("Provisioner only manages the dedicated local MLflow role/database")
    with psycopg.connect(
        host=business.host,
        port=business.port,
        dbname=business.database,
        user=business.username,
        password=business.password,
        autocommit=True,
    ) as connection:
        role_exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE_NAME,)
        ).fetchone()
        if role_exists and (not existing or "replace_" in existing):
            raise ValueError(
                "Existing MLflow role needs its original credentials; "
                "restore ignored .env from backup"
            )
        if not role_exists:
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(ROLE_NAME), sql.Literal(tracking.password)
                )
            )
        if not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (DATABASE_NAME,)
        ).fetchone():
            connection.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(DATABASE_NAME), sql.Identifier(ROLE_NAME)
                )
            )
    # Persist only after provision succeeds. Keep the business credentials independent.
    set_key(path, "MLFLOW_TRACKING_URI", tracking.render_as_string(hide_password=False))
    print("Dedicated MLflow PostgreSQL database is ready; credentials remain in ignored .env.")


if __name__ == "__main__":
    main()
