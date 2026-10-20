"""Add sealed model registrations, generation-checked serving slots and decision audit."""

import sqlalchemy as sa
from alembic import op

revision = "719de0a9b001"
down_revision = "52b92c66f920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add metadata only; artifacts and legacy model records remain untouched."""
    op.create_table(
        "model_registrations",
        sa.Column(
            "model_version_id", sa.String(36), sa.ForeignKey("model_versions.id"), primary_key=True
        ),
        sa.Column("bundle_sha256", sa.String(64), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(64), nullable=False),
        sa.Column("mlflow_model_name", sa.String(255), nullable=False),
        sa.Column("mlflow_model_version", sa.String(80), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
    )
    op.create_table(
        "model_slots",
        sa.Column("scope", sa.String(255), primary_key=True),
        sa.Column(
            "active_model_version_id",
            sa.String(36),
            sa.ForeignKey("model_versions.id"),
            nullable=True,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.CheckConstraint("generation >= 0", name=op.f("ck_model_slots_generation")),
    )
    op.create_table(
        "model_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "model_version_id", sa.String(36), sa.ForeignKey("model_versions.id"), nullable=False
        ),
        sa.Column(
            "previous_model_version_id",
            sa.String(36),
            sa.ForeignKey("model_versions.id"),
            nullable=True,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Remove lifecycle metadata only; no model/data files are deleted."""
    op.drop_table("model_events")
    op.drop_table("model_slots")
    op.drop_table("model_registrations")
