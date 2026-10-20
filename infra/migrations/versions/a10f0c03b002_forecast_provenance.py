"""Persist forecast provenance and evaluated per-day adjustments."""

import sqlalchemy as sa
from alembic import op

revision = "a10f0c03b002"
down_revision = "719de0a9b001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve existing rows; legacy contexts stay explicitly unsupported for API replay."""
    schema = op.get_context().opts.get("version_table_schema")
    op.add_column(
        "forecast_runs",
        sa.Column("request_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        schema=schema,
    )
    op.add_column(
        "forecast_points", sa.Column("known_open", sa.Boolean(), nullable=True), schema=schema
    )
    op.add_column(
        "forecast_points",
        sa.Column(
            "nonnegative_clamped", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema=schema,
    )
    op.add_column(
        "forecast_points",
        sa.Column(
            "closure_adjusted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema=schema,
    )


def downgrade() -> None:
    """Remove only new metadata columns; retained forecast values are not deleted."""
    schema = op.get_context().opts.get("version_table_schema")
    op.drop_column("forecast_points", "closure_adjusted", schema=schema)
    op.drop_column("forecast_points", "nonnegative_clamped", schema=schema)
    op.drop_column("forecast_points", "known_open", schema=schema)
    op.drop_column("forecast_runs", "request_context", schema=schema)
