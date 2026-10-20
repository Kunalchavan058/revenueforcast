"""Validate and append operator-supplied observed sales without changing existing snapshots."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import Engine, insert, literal, select, text
from sqlalchemy.orm import Session

from retailforecast.data.contracts import SaleRow
from retailforecast.data.pipeline_config import content_hash
from retailforecast.data.validation import REQUIRED_COLUMNS, file_checksum, source_rows
from retailforecast.storage.database import ROOT, database_engine, new_id, session_factory, utc_now
from retailforecast.storage.models import (
    DailySale,
    DatasetLineage,
    DatasetVersion,
    ForecastInput,
    ImportJob,
    Store,
)

MAX_ADDITIONAL_ROWS = 50_000
INSERT_BATCH_ROWS = 5000


class ActualsReport(BaseModel):
    """Auditable row/date/checksum report, separate from an unlabeled competition import."""

    parent_version_id: str
    checksum: str
    provenance: str = Field(min_length=5, max_length=500)
    synthetic: bool
    rows: int
    date_min: date
    date_max: date
    stores: tuple[int, ...]
    closed_with_sales: int


def validate_actuals(
    session: Session,
    parent: DatasetVersion,
    path: Path,
    provenance: str,
    *,
    synthetic: bool = False,
) -> tuple[ActualsReport, list[SaleRow]]:
    """Require observed labels, known stores and strictly later business dates."""
    import csv

    with path.open(encoding="utf-8-sig", newline="") as stream:
        fields = csv.DictReader(stream).fieldnames or []
    missing = REQUIRED_COLUMNS["train.csv"] - set(fields)
    if missing:
        raise ValueError(f"Additional actuals are missing required columns: {sorted(missing)}")
    known = set(session.scalars(select(Store.store_id).where(Store.source_version == parent.id)))
    rows: list[SaleRow] = []
    keys: set[tuple[int, date]] = set()
    checksum = file_checksum(path)
    for line, values in source_rows(path):
        try:
            row = SaleRow.model_validate(values)
        except ValueError as error:
            raise ValueError(f"Invalid observed sales at CSV row {line}: {error}") from error
        if len(rows) >= MAX_ADDITIONAL_ROWS:
            raise ValueError(f"Split additional actuals into at most {MAX_ADDITIONAL_ROWS} rows")
        if row.store_id not in known:
            raise ValueError(
                f"Row {line}: unknown store {row.store_id}; store onboarding is separate"
            )
        if not parent.available_through < row.date <= utc_now().date():
            raise ValueError(
                f"Row {line}: Date must be after {parent.available_through} and no later than today"
            )
        key = (row.store_id, row.date)
        if key in keys:
            raise ValueError(f"Row {line}: duplicate Store/Date {key}")
        keys.add(key)
        rows.append(row)
    if not rows:
        raise ValueError("Additional actuals CSV contains no labeled observations")
    if file_checksum(path) != checksum:
        raise ValueError("CSV changed during validation; retry a stable file")
    report = ActualsReport(
        parent_version_id=parent.id,
        checksum=checksum,
        provenance=provenance,
        synthetic=synthetic,
        rows=len(rows),
        date_min=min(row.date for row in rows),
        date_max=max(row.date for row in rows),
        stores=tuple(sorted({row.store_id for row in rows})),
        closed_with_sales=sum(row.is_open == 0 and row.sales > 0 for row in rows),
    )
    return report, rows


def clone_rows(
    session: Session,
    model: type[Store] | type[DailySale] | type[ForecastInput],
    parent_id: str,
    child_id: str,
) -> None:
    """Copy immutable rows inside the publication transaction without loading them into RAM."""
    columns = list(model.__table__.columns)
    statement = select(
        *(literal(child_id) if col.name == "source_version" else col for col in columns)
    ).where(model.source_version == parent_id)
    if model is ForecastInput:
        # Actual observations replace matching unlabeled plans; no test row gains
        # a made-up Sales label, and surviving template IDs remain consistent.
        observed = (
            select(DailySale.store_id)
            .where(
                DailySale.source_version == child_id,
                DailySale.store_id == ForecastInput.store_id,
                DailySale.date == ForecastInput.date,
            )
            .exists()
        )
        statement = statement.where(~observed)
    session.execute(insert(model).from_select([col.name for col in columns], statement))


def import_actuals(
    engine: Engine,
    parent_id: str,
    path: Path,
    provenance: str,
    *,
    synthetic: bool = False,
    dry_run: bool = False,
    raw_root: Path = ROOT / "data/raw/additional",
) -> dict[str, object]:
    """Validate first, preserve checksum-verified bytes, then publish one idempotent child."""
    sessions = session_factory(engine)
    with sessions() as session:
        parent = session.get(DatasetVersion, parent_id)
        if parent is None:
            raise ValueError("Unknown parent dataset version")
        report, rows = validate_actuals(session, parent, path, provenance, synthetic=synthetic)
    identity = content_hash(
        {"parent_checksum": parent.checksum, "additional": report.model_dump(mode="json")}
    )
    if dry_run:
        return {
            "state": "validated",
            "report": report.model_dump(mode="json"),
            "dataset_checksum": identity,
        }
    job_id = new_id()
    with sessions.begin() as session:
        session.add(
            ImportJob(
                id=job_id,
                checksum=identity,
                state="validating",
                report=report.model_dump(mode="json"),
            )
        )
    try:
        destination = raw_root / report.checksum / "actuals.csv"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temporary = destination.with_name(new_id() + ".tmp")
            try:
                shutil.copyfile(path, temporary)
                if file_checksum(temporary) != report.checksum:
                    raise ValueError("Actuals changed after validation")
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        if file_checksum(destination) != report.checksum:
            raise ValueError("Preserved actuals checksum mismatch")
        with sessions.begin() as session:
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(identity[:15], 16)}
            )
            session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(parent.checksum[:15], 16)}
            )
            existing = session.scalar(
                select(DatasetVersion.id).where(DatasetVersion.checksum == identity)
            )
            branch = session.scalar(
                select(DatasetLineage.dataset_version_id).where(
                    DatasetLineage.parent_version_id == parent_id
                )
            )
            if branch and not existing:
                raise ValueError(
                    f"Parent already extended by {branch}; use that latest child as the next base"
                )
            child_id = existing or new_id()
            if not existing:
                session.add(
                    DatasetVersion(
                        id=child_id,
                        source="synthetic:additional-actuals"
                        if synthetic
                        else "operator:additional-actuals",
                        checksum=identity,
                        version=identity,
                        rows=parent.rows + len(rows),
                        available_through=report.date_max,
                        availability_policy=parent.availability_policy,
                        raw_uri=str(destination),
                        validation_report={"additional_actuals": report.model_dump(mode="json")},
                    )
                )
                session.flush()
                clone_rows(session, Store, parent_id, child_id)
                clone_rows(session, DailySale, parent_id, child_id)
                for start in range(0, len(rows), INSERT_BATCH_ROWS):
                    session.execute(
                        insert(DailySale),
                        [
                            {**row.model_dump(), "source_version": child_id}
                            for row in rows[start : start + INSERT_BATCH_ROWS]
                        ],
                    )
                clone_rows(session, ForecastInput, parent_id, child_id)
                session.add(
                    DatasetLineage(
                        dataset_version_id=child_id,
                        parent_version_id=parent_id,
                        additional_checksum=report.checksum,
                        provenance=report.provenance,
                        synthetic=synthetic,
                    )
                )
            job = session.get(ImportJob, job_id)
            assert job is not None
            job.state = "duplicate" if existing else "succeeded"
            job.dataset_version_id = child_id
            job.completed_at = utc_now()
        return {
            "state": "duplicate" if existing else "succeeded",
            "dataset_version_id": child_id,
            "import_job_id": job_id,
            "report": report.model_dump(mode="json"),
        }
    except Exception as error:
        with sessions.begin() as session:
            job = session.get(ImportJob, job_id)
            assert job is not None
            job.state, job.completed_at, job.error_code = "failed", utc_now(), type(error).__name__
        raise


def main() -> None:
    """Import operator-observed rows; the explicit synthetic flag labels demonstrations honestly."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dataset-id", required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                import_actuals(
                    database_engine(),
                    args.base_dataset_id,
                    args.csv,
                    args.provenance,
                    synthetic=args.synthetic,
                    dry_run=args.dry_run,
                ),
                indent=2,
            )
        )
    except (ValueError, OSError) as error:
        parser.exit(2, f"Actuals import rejected: {error}\n")


if __name__ == "__main__":
    main()
