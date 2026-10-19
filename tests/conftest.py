"""Real PostgreSQL isolation for integration tests; never replace failures with skips."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.schema import CreateSchema, DropSchema

from retailforecast.storage.database import ROOT, database_engine


def migrate_schema(engine: Engine, schema: str, revision: str, *, downgrade: bool = False) -> None:
    """Run real frozen Alembic revisions in a disposable test schema."""
    config = Config(str(ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        config.attributes["schema"] = schema
        if downgrade:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)


@pytest.fixture
def postgres_database() -> Iterator[tuple[Engine, str]]:
    """Create/drop only a unique test schema, retaining the real imported business data."""
    base_engine = database_engine()
    schema = f"rf_test_{uuid4().hex}"
    with base_engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = base_engine.execution_options(schema_translate_map={None: schema})
    try:
        migrate_schema(isolated, schema, "head")
        yield isolated, schema
    finally:
        # The schema name is generated here, never accepted from a user or environment.
        with base_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
