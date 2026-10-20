"""Bounded SQL-to-file materialization with honest labels, hashes and empty-plan handling."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from retailforecast.data.contracts import ImportRequest, InputRow, SaleRow, SourceRow, StoreRow
from retailforecast.data.file_pipeline import (
    ValidationArtifact,
    atomic_json,
    create_manifest,
    normalize_sources,
    processing_context_hash,
)
from retailforecast.data.pipeline_config import DataConfig, load_config, text_hash
from retailforecast.data.validation import validate_bundle
from retailforecast.storage.models import DailySale, DatasetVersion, ForecastInput, Store

EXPORT_BATCH_ROWS = 5000


def export_table(
    session: Session,
    model: type[Store] | type[DailySale] | type[ForecastInput],
    contract: type[SourceRow],
    source_id: str,
    destination: Path,
) -> None:
    """Stream validated SQL fields to source aliases without inventing observations."""
    names = list(contract.model_fields)
    fields = [field.alias or name for name, field in contract.model_fields.items()]
    columns = [getattr(model, name) for name in names]
    statement = select(*columns).where(model.source_version == source_id).order_by(model.store_id)
    if model is DailySale:
        statement = statement.order_by(DailySale.date)
    elif model is ForecastInput:
        statement = statement.order_by(ForecastInput.date)
    rows = session.execute(statement).yield_per(EXPORT_BATCH_ROWS)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        for row in rows:
            writer.writerow([int(value) if isinstance(value, bool) else value for value in row])


def materialize_snapshot(
    session: Session, source: DatasetVersion, output: Path, root: Path
) -> tuple[Path, str, str]:
    """Create immutable request-owned files from SQL; original Kaggle/DVC inputs stay untouched."""
    if output.exists():
        raise ValueError("Snapshot directory already exists; use a new owned attempt")
    raw = output / "data/raw/sql"
    processed = output / "data/processed/sql"
    raw.mkdir(parents=True)
    (output / "configs").mkdir()
    exports: tuple[
        tuple[type[Store] | type[DailySale] | type[ForecastInput], type[SourceRow], str], ...
    ] = (
        (Store, StoreRow, "store.csv"),
        (DailySale, SaleRow, "train.csv"),
        (ForecastInput, InputRow, "test.csv"),
    )
    for model, contract, name in exports:
        export_table(session, model, contract, source.id, raw / name)
    with (raw / "sample_submission.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["Id", "Sales"])
        for value in session.scalars(
            select(ForecastInput.submission_id)
            .where(ForecastInput.source_version == source.id)
            .order_by(ForecastInput.store_id, ForecastInput.date)
        ).yield_per(EXPORT_BATCH_ROWS):
            # A submission template is explicitly a placeholder, never an observed target.
            writer.writerow([value, 0])
    original = load_config(root / "configs/data.yaml")
    profile = "synthetic" if source.source.startswith("synthetic") else "rossmann"
    values = original.model_dump(mode="json")
    values["profiles"] = {
        profile: {
            "kind": profile,
            "source_dir": "data/raw/sql",
            "output_dir": "data/processed/sql",
            "fixture": None,
        }
    }
    validation = original.validation.model_dump(mode="json")
    validation.update(
        maximum_date=max(original.validation.maximum_date, source.available_through).isoformat(),
        availability_policy=source.availability_policy
        + " SQL export v1: "
        + text_hash(Path(__file__)),
    )
    values["validation"] = validation
    config = DataConfig.model_validate(values)
    config_path = output / "configs/data.yaml"
    config_path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    shutil.copyfile(root / "uv.lock", output / "uv.lock")
    report = validate_bundle(
        ImportRequest(
            source_dir=str(raw),
            maximum_date=config.validation.maximum_date,
            minimum_date=config.validation.minimum_date,
            availability_policy=config.validation.availability_policy,
        )
    )
    # A post-competition SQL snapshot legitimately has no remaining test/template
    # rows. Allow only those two documented empty-plan diagnostics; every actual,
    # header, date, duplicate, checksum and store validation remains mandatory.
    empty_plan_errors = [
        issue
        for issue in report.issues
        if issue.file in ("test.csv", "sample_submission.csv")
        and issue.message == "File contains no data records"
    ]
    if report.issue_count == len(empty_plan_errors) and len(empty_plan_errors) == len(
        report.issues
    ):
        report.issues = []
        report.issue_count = 0
        report.valid = True
        if empty_plan_errors:
            report.warnings.append(
                "SQL snapshot has empty plans/template; no future rows fabricated."
            )
    if not report.valid:
        raise ValueError(
            "SQL snapshot failed source validation: "
            + "; ".join(issue.message for issue in report.issues[:3])
        )
    report.source = (
        "synthetic:sql-snapshot" if profile == "synthetic" else "operator:validated-sql-snapshot"
    )
    atomic_json(
        processed / "validation.json",
        ValidationArtifact(
            report=report, context_sha256=processing_context_hash(config_path, profile)
        ).model_dump(mode="json"),
    )
    normalize_sources(config_path, profile)
    manifest = create_manifest(config_path, profile)
    return config_path, profile, manifest.ingestion_dataset_checksum
