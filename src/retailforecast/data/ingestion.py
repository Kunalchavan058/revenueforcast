"""Publish immutable validated snapshots in one business transaction."""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import Engine, insert, select, text
from sqlalchemy.orm import Session

from retailforecast.data.contracts import ImportRequest, ImportResponse, ValidationReport
from retailforecast.data.validation import (
    SOURCE_MODELS,
    file_checksum,
    source_rows,
    validate_bundle,
)
from retailforecast.storage.database import ROOT, new_id, session_factory, utc_now
from retailforecast.storage.models import (
    DailySale,
    DatasetVersion,
    ForecastInput,
    ImportJob,
    Store,
)

INSERT_BATCH_ROWS = 5000
DEFAULT_RAW_ROOT = ROOT / "data" / "raw"


def preserve_sources(directory: Path, report: ValidationReport, raw_root: Path) -> Path:
    """Copy bytes into a content-addressed local folder and verify before publication."""
    destination = raw_root / report.checksum
    destination.mkdir(parents=True, exist_ok=True)
    for name, summary in report.files.items():
        target = destination / name
        if target.exists():
            if file_checksum(target) != summary.checksum:
                raise ValueError(
                    f"Preserved {name} has an unexpected checksum; do not overwrite it"
                )
            continue
        temporary = destination / f"{name}.{new_id()}.tmp"
        try:
            shutil.copyfile(directory / name, temporary)
            if file_checksum(temporary) != summary.checksum:
                raise ValueError(
                    f"{name} changed after validation; retry using stable source files"
                )
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return destination


def insert_file(session: Session, path: Path, dataset_id: str) -> None:
    """Insert typed source records in bounded batches, never committing individual batches."""
    model = {"store.csv": Store, "train.csv": DailySale, "test.csv": ForecastInput}[path.name]
    batch: list[dict[str, object]] = []
    for _, values in source_rows(path):
        parsed = SOURCE_MODELS[path.name].model_validate(values)
        row: dict[str, object] = parsed.model_dump()
        row["source_version"] = dataset_id
        batch.append(row)
        if len(batch) >= INSERT_BATCH_ROWS:
            session.execute(insert(model), batch)
            batch.clear()
    if batch:
        session.execute(insert(model), batch)


def persist_snapshot(
    session: Session,
    raw_path: Path,
    report: ValidationReport,
) -> str:
    """Publish all business rows atomically; the caller owns the transaction."""
    dataset_id = new_id()
    last_date = report.files["train.csv"].date_max
    if last_date is None:
        raise ValueError("Validated train.csv must have an observed date span")
    session.add(
        DatasetVersion(
            id=dataset_id,
            source=report.source,
            checksum=report.checksum,
            version=report.checksum,
            rows=report.files["train.csv"].valid_rows,
            available_through=last_date,
            availability_policy=report.availability_policy,
            raw_uri=str(raw_path),
            validation_report=report.model_dump(mode="json"),
        )
    )
    session.flush()
    # Stores must exist before either actuals or unlabeled inputs satisfy their composite FK.
    for filename in ["store.csv", "train.csv", "test.csv"]:
        insert_file(session, raw_path / filename, dataset_id)
    return dataset_id


def record_failure(
    engine: Engine,
    job_id: str,
    report: ValidationReport,
    error_code: str,
) -> None:
    """Retain failure audit after the business transaction has rolled back."""
    with session_factory(engine).begin() as session:
        job = session.get(ImportJob, job_id)
        if job is None:
            raise RuntimeError("Import audit record is missing")
        job.state = "failed"
        job.completed_at = utc_now()
        job.error_code = error_code
        job.report = report.model_dump(mode="json")


def import_bundle(
    request: ImportRequest,
    engine: Engine | None = None,
    raw_root: Path = DEFAULT_RAW_ROOT,
) -> ImportResponse:
    """Validate first; dry runs need no database and actual imports publish all-or-nothing."""
    report = validate_bundle(request)
    if request.dry_run:
        return ImportResponse(state="validated" if report.valid else "rejected", report=report)
    if engine is None:
        raise ValueError("A configured PostgreSQL engine is required for publication")
    sessions = session_factory(engine)
    job_id = new_id()
    with sessions.begin() as session:
        session.add(
            ImportJob(
                id=job_id,
                checksum=report.checksum,
                state="validating",
                report=report.model_dump(mode="json"),
            )
        )
    if not report.valid:
        record_failure(engine, job_id, report, "validation_failed")
        return ImportResponse(state="rejected", import_job_id=job_id, report=report)
    with sessions.begin() as session:
        job = session.get(ImportJob, job_id)
        if job is None:
            raise RuntimeError("Import audit record is missing")
        job.state = "running"
    try:
        raw_path = preserve_sources(Path(request.source_dir), report, raw_root)
        with sessions.begin() as session:
            if engine.dialect.name == "postgresql":
                # Serialize equal snapshots across processes; a pre-check alone races.
                lock_key = int(report.checksum[:15], 16)
                session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
            existing = session.scalar(
                select(DatasetVersion.id).where(DatasetVersion.checksum == report.checksum),
            )
            dataset_id = existing or persist_snapshot(session, raw_path, report)
            job = session.get(ImportJob, job_id)
            if job is None:
                raise RuntimeError("Import audit record is missing")
            job.dataset_version_id = dataset_id
            job.state = "duplicate" if existing else "succeeded"
            job.completed_at = utc_now()
        return ImportResponse(
            state="duplicate" if existing else "succeeded",
            dataset_version_id=dataset_id,
            import_job_id=job_id,
            report=report,
        )
    except Exception as error:
        # Deliberately retain only the exception class, not SQL parameters/credentials.
        record_failure(engine, job_id, report, type(error).__name__)
        raise
