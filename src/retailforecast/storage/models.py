"""Normalized business records; fitted models remain external artifact files."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from retailforecast.storage.database import new_id, utc_now

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Single SQLAlchemy metadata root shared with Alembic."""

    metadata = MetaData(naming_convention=NAMING)


class DatasetVersion(Base):
    """An immutable four-file snapshot and its historical-availability contract."""

    __tablename__ = "dataset_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(80))
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    version: Mapped[str] = mapped_column(String(64), unique=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    rows: Mapped[int] = mapped_column(Integer)
    available_through: Mapped[date] = mapped_column(Date)
    availability_policy: Mapped[str] = mapped_column(Text)
    raw_uri: Mapped[str] = mapped_column(Text)
    validation_report: Mapped[dict[str, object]] = mapped_column(JSON)
    __table_args__ = (CheckConstraint("rows > 0", name="positive_rows"),)


class Store(Base):
    """Source metadata at snapshot grain; store IDs alone do not identify a version."""

    __tablename__ = "stores"
    source_version: Mapped[str] = mapped_column(
        ForeignKey("dataset_versions.id"),
        primary_key=True,
    )
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_type: Mapped[str | None] = mapped_column(String(1))
    assortment: Mapped[str | None] = mapped_column(String(1))
    competition_distance: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    competition_open_since_month: Mapped[int | None]
    competition_open_since_year: Mapped[int | None]
    promo2: Mapped[bool | None]
    promo2_since_week: Mapped[int | None]
    promo2_since_year: Mapped[int | None]
    promo_interval: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (CheckConstraint("store_id > 0", name="positive_store"),)


class DailySale(Base):
    """Observed train.csv labels; future competition inputs never enter this table."""

    __tablename__ = "daily_sales"
    source_version: Mapped[str] = mapped_column(String(36), primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    sales: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    customers: Mapped[int]
    is_open: Mapped[bool]
    promotion: Mapped[bool]
    day_of_week: Mapped[int]
    state_holiday: Mapped[str] = mapped_column(String(1))
    school_holiday: Mapped[bool]
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_version", "store_id"],
            ["stores.source_version", "stores.store_id"],
        ),
        CheckConstraint("sales >= 0 AND customers >= 0", name="nonnegative_actuals"),
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="weekday"),
    )


class ForecastInput(Base):
    """Unlabeled test.csv plans; deliberately has no Sales or Customers columns."""

    __tablename__ = "forecast_inputs"
    source_version: Mapped[str] = mapped_column(String(36), primary_key=True)
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    submission_id: Mapped[int]
    is_open: Mapped[bool | None]
    promotion: Mapped[bool]
    day_of_week: Mapped[int]
    state_holiday: Mapped[str] = mapped_column(String(1))
    school_holiday: Mapped[bool]
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_version", "store_id"],
            ["stores.source_version", "stores.store_id"],
        ),
        UniqueConstraint("source_version", "submission_id"),
        CheckConstraint("submission_id > 0", name="positive_submission_id"),
    )


class ImportJob(Base):
    """A durable audit attempt, retained even when business-data publication rolls back."""

    __tablename__ = "import_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_version_id: Mapped[str | None] = mapped_column(ForeignKey("dataset_versions.id"))
    checksum: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20))
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    report: Mapped[dict[str, object]] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (
        CheckConstraint(
            "state IN ('validating','running','succeeded','failed','duplicate')",
            name="state",
        ),
    )


class TrainingJob(Base):
    """Future training metadata only; this phase does not execute jobs."""

    __tablename__ = "training_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    requested_algorithm: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="queued")
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    logs_uri: Mapped[str | None] = mapped_column(Text)
    exit_code: Mapped[int | None]
    __table_args__ = (
        CheckConstraint(
            "requested_algorithm IN ('lightgbm','xgboost','auto')",
            name="algorithm",
        ),
        CheckConstraint(
            "state IN ('queued','running','succeeded','failed','interrupted','cancelled')",
            name="state",
        ),
    )


class ModelVersion(Base):
    """Future artifact references and scope-scoped approval; never serialized bytes."""

    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    training_job_id: Mapped[str | None] = mapped_column(ForeignKey("training_jobs.id"))
    scope: Mapped[str] = mapped_column(String(255))
    algorithm: Mapped[str] = mapped_column(String(20))
    trained_until: Mapped[date] = mapped_column(Date)
    artifact_uri: Mapped[str] = mapped_column(Text)
    feature_schema_fingerprint: Mapped[str] = mapped_column(String(64))
    mlflow_run_id: Mapped[str | None] = mapped_column(String(80))
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    evaluation_reference: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="candidate")
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate','active','rejected','archived')",
            name="status",
        ),
        CheckConstraint("algorithm IN ('lightgbm','xgboost')", name="algorithm"),
        Index(
            "uq_active_model_scope",
            "scope",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )


class ForecastRun(Base):
    """Future request-level provenance shared by its points to avoid duplication."""

    __tablename__ = "forecast_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_version: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id"))
    cutoff_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    __table_args__ = (UniqueConstraint("id", "source_version"),)


class ForecastPoint(Base):
    """Future values inherit model/cutoff/creation provenance from their parent run."""

    __tablename__ = "forecast_points"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_version: Mapped[str] = mapped_column(String(36))
    store_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_date: Mapped[date] = mapped_column(Date, primary_key=True)
    horizon: Mapped[int]
    predicted_sales: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "source_version"], ["forecast_runs.id", "forecast_runs.source_version"]
        ),
        ForeignKeyConstraint(
            ["source_version", "store_id"], ["stores.source_version", "stores.store_id"]
        ),
        UniqueConstraint("run_id", "store_id", "horizon"),
        CheckConstraint("horizon BETWEEN 1 AND 48", name="horizon"),
        CheckConstraint("predicted_sales >= 0", name="nonnegative_prediction"),
    )


class RetrainingSchedule(Base):
    """Future schedule configuration; no scheduler runs in this ingestion phase."""

    __tablename__ = "retraining_schedules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(255), unique=True)
    cadence: Mapped[str] = mapped_column(String(20), default="manual")
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint(
            "cadence IN ('manual','weekly','monthly','quarterly')",
            name="cadence",
        ),
    )
