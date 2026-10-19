"""Reproducible file artifacts only; never modify PostgreSQL or train a model."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pyarrow
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field

from retailforecast.data.contracts import ImportRequest, ValidationReport
from retailforecast.data.parquet_tables import TABLE_NAMES, write_normalized_table
from retailforecast.data.pipeline_config import (
    DEFAULT_CONFIG,
    canonical_json,
    content_hash,
    profile_paths,
    rooted_path,
    text_hash,
)
from retailforecast.data.synthetic_data import generate_synthetic
from retailforecast.data.validation import SOURCE_MODELS, file_checksum, validate_bundle

PROCESSOR_FILES = (
    "contracts.py",
    "validation.py",
    "pipeline_config.py",
    "parquet_tables.py",
    "file_pipeline.py",
)


class TableArtifact(BaseModel):
    """A portable normalized-table reference, not rows or a model artifact."""

    model_config = ConfigDict(extra="forbid")
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(ge=0)
    columns: dict[str, str]


class ValidationArtifact(BaseModel):
    """Bind a reusable validation report to the exact processing context."""

    report: ValidationReport
    context_sha256: str


class NormalizationReceipt(BaseModel):
    """Prove which validated context produced each completed normalized table."""

    validation_report_sha256: str
    table_checksums: dict[str, str]


class DatasetManifest(BaseModel):
    """Stable metadata intended for inspection and a future read-only UI/API."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    dataset_kind: Literal["synthetic", "rossmann"]
    dataset_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    ingestion_dataset_checksum: str
    max_historical_actual_date: date
    availability_policy: str
    effective_config_sha256: str
    input_checksums: dict[str, str]
    processing_code_sha256: dict[str, str]
    dependency_lock_sha256: str
    pyarrow_version: str
    validation_report_sha256: str
    normalization_receipt_sha256: str
    tables: dict[str, TableArtifact]


def atomic_json(path: Path, value: object) -> None:
    """Publish deterministic UTF-8 JSON using an owned temporary sibling file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(canonical_json(value))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def effective_config_hash(config_path: Path, profile_name: str) -> str:
    """Hash semantic processing settings, excluding machine-relative file locations."""
    config, profile, _, _ = profile_paths(config_path, profile_name)
    return content_hash(
        {
            "schema_version": config.schema_version,
            "dataset_kind": profile.kind,
            "validation": config.validation.model_dump(mode="json"),
            "processing": config.processing.model_dump(mode="json"),
        }
    )


def processor_hashes() -> dict[str, str]:
    """Identify actual source code, including uncommitted edits, without a Git dependency."""
    package = Path(__file__).resolve().parent
    return {
        f"src/retailforecast/data/{name}": text_hash(package / name) for name in PROCESSOR_FILES
    }


def source_checksums(source: Path) -> dict[str, str]:
    """Identify exact raw bytes for the four required files."""
    return {name: file_checksum(source / name) for name in SOURCE_MODELS}


def processing_context_hash(config_path: Path, profile_name: str) -> str:
    """Invalidate direct stage reuse when code, config, lock, or writer changes."""
    root = config_path.resolve().parent.parent
    return content_hash(
        {
            "effective_config_sha256": effective_config_hash(config_path, profile_name),
            "processing_code_sha256": processor_hashes(),
            "dependency_lock_sha256": text_hash(root / "uv.lock"),
            "pyarrow_version": pyarrow.__version__,
        }
    )


def validate_sources(config_path: Path, profile_name: str) -> ValidationReport:
    """Reuse source contracts with fixed config bounds and persist a deterministic report."""
    config, profile, source, output = profile_paths(config_path, profile_name)
    request = ImportRequest(
        source_dir=str(source),
        dry_run=True,
        minimum_date=config.validation.minimum_date,
        maximum_date=config.validation.maximum_date,
        availability_policy=config.validation.availability_policy,
    )
    report = validate_bundle(request)
    if profile.kind == "synthetic":
        report.source = "synthetic:rossmann-shaped"
    artifact = ValidationArtifact(
        report=report,
        context_sha256=processing_context_hash(config_path, profile_name),
    )
    atomic_json(output / "validation.json", artifact.model_dump(mode="json"))
    if not report.valid:
        examples = "; ".join(
            f"{item.file}:{item.row}: {item.message}" for item in report.issues[:3]
        )
        raise ValueError(f"Source validation failed; inspect validation.json. {examples}")
    return report


def checked_report(config_path: Path, profile_name: str) -> ValidationReport:
    """Refuse stale validation after source/policy changes, even outside DVC orchestration."""
    config, _, source, output = profile_paths(config_path, profile_name)
    artifact = ValidationArtifact.model_validate_json((output / "validation.json").read_bytes())
    if artifact.context_sha256 != processing_context_hash(config_path, profile_name):
        raise ValueError("Validation context changed; rerun the validate stage")
    report = artifact.report
    if (
        not report.valid
        or report.minimum_date != config.validation.minimum_date
        or report.maximum_date != config.validation.maximum_date
        or report.availability_policy != config.validation.availability_policy
        or {name: item.checksum for name, item in report.files.items()} != source_checksums(source)
    ):
        raise ValueError("Validation is stale or rejected; rerun the validate stage")
    return report


def normalize_sources(config_path: Path, profile_name: str) -> None:
    """Create only typed source-normalized tables, with no lags, imputations or features."""
    config, _, source, output = profile_paths(config_path, profile_name)
    report = checked_report(config_path, profile_name)
    for filename, table_name in TABLE_NAMES.items():
        count = write_normalized_table(
            source / filename,
            output / "tables" / f"{table_name}.parquet",
            config.processing,
        )
        if count != report.files[filename].valid_rows:
            raise ValueError("Source row count changed while normalizing")
    # Hash again after streaming: never publish a manifest for changing raw inputs.
    checked_report(config_path, profile_name)
    receipt = NormalizationReceipt(
        validation_report_sha256=file_checksum(output / "validation.json"),
        table_checksums={
            name: file_checksum(output / "tables" / f"{name}.parquet")
            for name in TABLE_NAMES.values()
        },
    )
    atomic_json(output / "tables" / "normalization.json", receipt.model_dump(mode="json"))


def create_manifest(config_path: Path, profile_name: str) -> DatasetManifest:
    """Publish a timestamp-free content/config/code fingerprint after all tables succeed."""
    _, profile, _, output = profile_paths(config_path, profile_name)
    root = config_path.resolve().parent.parent
    report = checked_report(config_path, profile_name)
    receipt_path = output / "tables" / "normalization.json"
    receipt = NormalizationReceipt.model_validate_json(receipt_path.read_bytes())
    if receipt.validation_report_sha256 != file_checksum(output / "validation.json"):
        raise ValueError("Normalized tables are stale; rerun normalization")
    tables: dict[str, TableArtifact] = {}
    for filename, name in TABLE_NAMES.items():
        path = output / "tables" / f"{name}.parquet"
        if file_checksum(path) != receipt.table_checksums[name]:
            raise ValueError("Normalized table changed; rerun normalization")
        metadata = pq.ParquetFile(path)
        count = int(metadata.metadata.num_rows)
        if count != report.files[filename].valid_rows:
            raise ValueError(f"{name} has unexpected row count; rerun normalization")
        tables[name] = TableArtifact(
            path=path.relative_to(root).as_posix(),
            sha256=file_checksum(path),
            row_count=count,
            columns={field.name: str(field.type) for field in metadata.schema_arrow},
        )
    actual_date = report.files["train.csv"].date_max
    if actual_date is None:
        raise ValueError("A dataset manifest needs historical labels")
    payload: dict[str, object] = {
        "schema_version": 1,
        "dataset_kind": profile.kind,
        "ingestion_dataset_checksum": report.checksum,
        "max_historical_actual_date": actual_date.isoformat(),
        "availability_policy": report.availability_policy,
        "effective_config_sha256": effective_config_hash(config_path, profile_name),
        "input_checksums": {name: item.checksum for name, item in report.files.items()},
        "processing_code_sha256": processor_hashes(),
        "dependency_lock_sha256": text_hash(root / "uv.lock"),
        "pyarrow_version": pyarrow.__version__,
        "validation_report_sha256": file_checksum(output / "validation.json"),
        "normalization_receipt_sha256": file_checksum(receipt_path),
        "tables": {name: item.model_dump(mode="json") for name, item in tables.items()},
    }
    manifest = DatasetManifest.model_validate(
        {
            **payload,
            "dataset_fingerprint": content_hash(payload),
        }
    )
    atomic_json(output / "manifest.json", manifest.model_dump(mode="json"))
    return manifest


def verify_manifest(config_path: Path, profile_name: str) -> DatasetManifest:
    """Verify stored manifest identity and all current source/output/config/code references."""
    _, profile, source, output = profile_paths(config_path, profile_name)
    root = config_path.resolve().parent.parent
    manifest = DatasetManifest.model_validate_json((output / "manifest.json").read_bytes())
    payload = manifest.model_dump(mode="json", exclude={"dataset_fingerprint"})
    if manifest.dataset_fingerprint != content_hash(payload):
        raise ValueError("Manifest fingerprint does not match its contents")
    if (
        manifest.dataset_kind != profile.kind
        or manifest.input_checksums != source_checksums(source)
        or manifest.effective_config_sha256 != effective_config_hash(config_path, profile_name)
        or manifest.processing_code_sha256 != processor_hashes()
        or manifest.dependency_lock_sha256 != text_hash(root / "uv.lock")
        or manifest.pyarrow_version != pyarrow.__version__
        or manifest.validation_report_sha256 != file_checksum(output / "validation.json")
        or manifest.normalization_receipt_sha256
        != file_checksum(output / "tables" / "normalization.json")
    ):
        raise ValueError(
            "Manifest is stale; reproduce it with current inputs/config/code/environment"
        )
    for table in manifest.tables.values():
        if file_checksum(rooted_path(root, table.path)) != table.sha256:
            raise ValueError("Parquet artifact checksum changed; restore/reproduce it")
    return manifest


def run_pipeline(config_path: Path, profile_name: str) -> DatasetManifest:
    """Run validation, normalization and manifest sequentially without any database calls."""
    validate_sources(config_path, profile_name)
    normalize_sources(config_path, profile_name)
    return create_manifest(config_path, profile_name)


def prepare_raw(config_path: Path, profile_name: str, source_dir: Path) -> None:
    """Stage verified real CSV copies for DVC without modifying original downloaded files."""
    config, profile, destination, _ = profile_paths(config_path, profile_name)
    if profile.kind != "rossmann":
        raise ValueError("Use sample for synthetic profiles; prepare is for real files only")
    request = ImportRequest(
        source_dir=str(source_dir.resolve()),
        dry_run=True,
        minimum_date=config.validation.minimum_date,
        maximum_date=config.validation.maximum_date,
        availability_policy=config.validation.availability_policy,
    )
    report = validate_bundle(request)
    if not report.valid:
        raise ValueError(
            "Raw source bundle is invalid; run the existing validation CLI for details"
        )
    destination.mkdir(parents=True, exist_ok=True)
    for name, summary in report.files.items():
        target = destination / name
        if target.exists() and file_checksum(target) == summary.checksum:
            continue
        temporary = destination / f".{name}.{uuid4().hex}.tmp"
        try:
            shutil.copyfile(source_dir / name, temporary)
            if file_checksum(temporary) != summary.checksum:
                raise ValueError(f"{name} changed while copying; retry a stable source")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def main() -> int:
    """Expose small stage commands used by DVC; failures return nonzero without fake outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=["sample", "prepare", "validate", "normalize", "manifest", "run", "verify"]
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--profile", default="synthetic")
    parser.add_argument("--source-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.stage == "sample":
            generate_synthetic(args.config, args.profile)
        elif args.stage == "prepare":
            if args.source_dir is None:
                parser.error("prepare requires --source-dir")
            prepare_raw(args.config, args.profile, args.source_dir)
        elif args.stage == "validate":
            validate_sources(args.config, args.profile)
        elif args.stage == "normalize":
            normalize_sources(args.config, args.profile)
        else:
            action = {"manifest": create_manifest, "run": run_pipeline, "verify": verify_manifest}
            manifest = action[args.stage](args.config, args.profile)
            actual_date = manifest.max_historical_actual_date.isoformat()
            print(
                json.dumps(
                    {
                        "dataset_kind": manifest.dataset_kind,
                        "dataset_fingerprint": manifest.dataset_fingerprint,
                        "max_historical_actual_date": actual_date,
                        "row_counts": {
                            name: item.row_count for name, item in manifest.tables.items()
                        },
                    },
                    indent=2,
                )
            )
    except (OSError, ValueError, KeyError) as error:
        print(f"File pipeline failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
