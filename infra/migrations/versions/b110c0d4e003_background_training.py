"""Add durable fenced training attempts, optional schedules and append-only lineage."""

import sqlalchemy as sa
from alembic import op

revision = "b110c0d4e003"
down_revision = "a10f0c03b002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve old jobs, converting the historical interrupted state to an explicit failure."""
    schema = op.get_context().opts.get("version_table_schema")
    op.drop_constraint(
        op.f("ck_training_jobs_state"), "training_jobs", type_="check", schema=schema
    )
    jobs = sa.table("training_jobs", sa.column("state"), schema=schema)
    op.execute(jobs.update().where(jobs.c.state == "interrupted").values(state="failed"))
    op.create_check_constraint(
        op.f("ck_training_jobs_state"),
        "training_jobs",
        "state IN ('queued','running','succeeded','failed','skipped','cancelled')",
        schema=schema,
    )
    op.alter_column("training_jobs", "dataset_version_id", nullable=True, schema=schema)
    columns = [
        sa.Column("trigger_key", sa.String(180), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False, server_default=""),
        sa.Column("request_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("stage", sa.String(40), nullable=False, server_default="queued"),
        sa.Column(
            "message",
            sa.Text(),
            nullable=False,
            server_default="Legacy request; inspect before execution",
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("retry_after", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("scheduled_for", sa.DateTime(timezone=True)),
        sa.Column("result_model_version_id", sa.String(36)),
    ]
    op.create_index(
        "uq_model_training_job",
        "model_versions",
        ["training_job_id"],
        unique=True,
        postgresql_where=sa.text("training_job_id IS NOT NULL"),
        schema=schema,
    )
    for column in columns:
        if not isinstance(column, sa.Column):
            raise TypeError("Expected a frozen SQL column definition")
        op.add_column("training_jobs", column, schema=schema)
    table = sa.table("training_jobs", sa.column("id"), sa.column("trigger_key"), schema=schema)
    op.execute(table.update().values(trigger_key=table.c.id))
    op.alter_column("training_jobs", "trigger_key", nullable=False, schema=schema)
    op.create_unique_constraint(
        "uq_training_jobs_trigger_key", "training_jobs", ["trigger_key"], schema=schema
    )
    op.create_check_constraint(
        op.f("ck_training_jobs_attempt_bounds"),
        "training_jobs",
        "attempt_count >= 0 AND max_attempts BETWEEN 1 AND 3",
        schema=schema,
    )
    # Do not conceal ambiguous legacy simultaneous running jobs during upgrade.
    op.create_index(
        "uq_running_training_job",
        "training_jobs",
        ["state"],
        unique=True,
        postgresql_where=sa.text("state = 'running'"),
        schema=schema,
    )
    for column in [
        sa.Column("anchor_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("algorithm", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("last_check_at", sa.DateTime(timezone=True)),
    ]:
        if not isinstance(column, sa.Column):
            raise TypeError("Expected a frozen SQL column definition")
        op.add_column("retraining_schedules", column, schema=schema)
    op.create_table(
        "dataset_lineage",
        sa.Column(
            "dataset_version_id",
            sa.String(36),
            sa.ForeignKey("dataset_versions.id"),
            primary_key=True,
        ),
        sa.Column(
            "parent_version_id", sa.String(36), sa.ForeignKey("dataset_versions.id"), nullable=False
        ),
        sa.Column("additional_checksum", sa.String(64), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "dataset_version_id <> parent_version_id",
            name=op.f("ck_dataset_lineage_distinct_parent"),
        ),
    )
    op.create_table(
        "training_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("training_jobs.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("owner_token", sa.String(36), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("process_id", sa.Integer()),
        sa.Column("process_created_at", sa.Float()),
        sa.Column("output_relative", sa.Text(), nullable=False),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.UniqueConstraint("job_id", "number", name="uq_training_attempts_job_id"),
    )


def downgrade() -> None:
    """Remove worker metadata without deleting source snapshots, model files or forecasts."""
    schema = op.get_context().opts.get("version_table_schema")
    op.drop_index("uq_model_training_job", table_name="model_versions", schema=schema)
    op.drop_table("training_attempts")
    op.drop_table("dataset_lineage")
    for name in ("last_check_at", "algorithm", "revision", "anchor_at"):
        op.drop_column("retraining_schedules", name, schema=schema)
    op.drop_index("uq_running_training_job", table_name="training_jobs", schema=schema)
    op.drop_constraint(
        op.f("ck_training_jobs_attempt_bounds"), "training_jobs", type_="check", schema=schema
    )
    op.drop_constraint(
        "uq_training_jobs_trigger_key", "training_jobs", type_="unique", schema=schema
    )
    for name in (
        "result_model_version_id",
        "scheduled_for",
        "heartbeat_at",
        "started_at",
        "retry_after",
        "max_attempts",
        "attempt_count",
        "message",
        "stage",
        "request_context",
        "request_fingerprint",
        "trigger_key",
    ):
        op.drop_column("training_jobs", name, schema=schema)
    op.drop_constraint(
        op.f("ck_training_jobs_state"), "training_jobs", type_="check", schema=schema
    )
    jobs = sa.table("training_jobs", sa.column("state"), schema=schema)
    op.execute(jobs.update().where(jobs.c.state == "skipped").values(state="failed"))
    op.create_check_constraint(
        op.f("ck_training_jobs_state"),
        "training_jobs",
        "state IN ('queued','running','succeeded','failed','interrupted','cancelled')",
        schema=schema,
    )
    old_jobs = sa.table("training_jobs", sa.column("dataset_version_id"), schema=schema)
    if op.get_bind().scalar(
        sa.select(sa.func.count())
        .select_from(old_jobs)
        .where(old_jobs.c.dataset_version_id.is_(None))
    ):
        raise ValueError(
            "Cannot downgrade null-source schedule audit; retain/export those records first"
        )
    op.alter_column("training_jobs", "dataset_version_id", nullable=False, schema=schema)
