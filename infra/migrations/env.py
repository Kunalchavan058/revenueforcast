"""Alembic transaction environment; external connections support isolated schema tests."""

from alembic import context
from sqlalchemy import Connection, create_engine, pool

from retailforecast.storage.database import DatabaseSettings
from retailforecast.storage.models import Base

target_metadata = Base.metadata


def migrate_connection(connection: Connection) -> None:
    """Apply revisions to one connection, optionally within an isolated test schema."""
    schema = context.config.attributes.get("schema")
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=schema,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations() -> None:
    """Use PostgreSQL only and never include credentials in migration logs."""
    supplied = context.config.attributes.get("connection")
    if isinstance(supplied, Connection):
        migrate_connection(supplied)
        return
    url = DatabaseSettings().database_url.get_secret_value()
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("Migrations require a PostgreSQL psycopg URL")
    if context.is_offline_mode():
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
        with engine.connect() as connection:
            migrate_connection(connection)
        engine.dispose()


run_migrations()
