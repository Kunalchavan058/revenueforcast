"""Verify deterministic file artifacts, bounded batches and source/label separation."""

from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from retailforecast.data.file_pipeline import (
    create_manifest,
    run_pipeline,
    validate_sources,
    verify_manifest,
)
from retailforecast.data.pipeline_config import DEFAULT_CONFIG, load_config, profile_paths
from retailforecast.data.synthetic_data import generate_synthetic


def fixture_project(root: Path) -> Path:
    """Create a standalone synthetic project without Kaggle, database, or DVC service."""
    original = DEFAULT_CONFIG.parent.parent
    config = root / "configs" / "data.yaml"
    config.parent.mkdir(parents=True)
    text = DEFAULT_CONFIG.read_text(encoding="utf-8").replace("batch_rows: 10000", "batch_rows: 2")
    config.write_text(text, encoding="utf-8")
    fixture = root / "tests" / "fixtures" / "rossmann_synthetic.json"
    fixture.parent.mkdir(parents=True)
    shutil.copyfile(original / "tests" / "fixtures" / fixture.name, fixture)
    shutil.copyfile(original / "uv.lock", root / "uv.lock")
    generate_synthetic(config, "synthetic")
    return config


def test_identical_rerun_is_byte_reproducible(tmp_path: Path) -> None:
    """Unchanged raw/config/code/lock reproduce identical Parquet and manifest bytes."""
    config = fixture_project(tmp_path)
    first = run_pipeline(config, "synthetic")
    output = tmp_path / "data" / "processed" / "synthetic"
    paths = [
        output / "manifest.json",
        output / "validation.json",
        *sorted((output / "tables").iterdir()),
    ]
    before = {path.name: path.read_bytes() for path in paths}
    second = run_pipeline(config, "synthetic")
    assert first.dataset_fingerprint == second.dataset_fingerprint
    assert before == {path.name: path.read_bytes() for path in paths}
    assert verify_manifest(config, "synthetic") == second


def test_changed_input_changes_dataset_fingerprint(tmp_path: Path) -> None:
    """A changed actual label yields a new data identity without touching PostgreSQL."""
    config = fixture_project(tmp_path)
    first = run_pipeline(config, "synthetic")
    source = tmp_path / "data" / "raw" / "synthetic" / "train.csv"
    source.write_text(source.read_text().replace("10.00", "11.00"), encoding="utf-8", newline="\n")
    second = run_pipeline(config, "synthetic")
    assert first.dataset_fingerprint != second.dataset_fingerprint
    assert first.tables["daily_sales"].sha256 != second.tables["daily_sales"].sha256


def test_manifest_is_portable_across_project_roots(tmp_path: Path) -> None:
    """Machine-local project paths never enter the data identity or JSON manifest."""
    left = run_pipeline(fixture_project(tmp_path / "left"), "synthetic")
    right = run_pipeline(fixture_project(tmp_path / "right"), "synthetic")
    assert left == right
    assert str(tmp_path) not in left.model_dump_json()


def test_config_change_requires_fresh_normalization(tmp_path: Path) -> None:
    """Do not attach new config provenance to old Parquet with an equal row count."""
    config = fixture_project(tmp_path)
    first = run_pipeline(config, "synthetic")
    config.write_text(
        config.read_text().replace("batch_rows: 2", "batch_rows: 3"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="context changed"):
        create_manifest(config, "synthetic")
    validate_sources(config, "synthetic")
    with pytest.raises(ValueError, match="stale"):
        create_manifest(config, "synthetic")
    second = run_pipeline(config, "synthetic")
    assert second.dataset_fingerprint != first.dataset_fingerprint


def test_types_labels_missingness_and_memory_batches(tmp_path: Path) -> None:
    """Retain source quirks while bounding row groups and excluding future labels."""
    config = fixture_project(tmp_path)
    manifest = run_pipeline(config, "synthetic")
    assert manifest.dataset_kind == "synthetic"
    assert manifest.max_historical_actual_date.isoformat() == "2015-07-31"
    sales = pq.ParquetFile(tmp_path / manifest.tables["daily_sales"].path)
    assert sales.num_row_groups == 2
    assert all(sales.metadata.row_group(i).num_rows <= 2 for i in range(sales.num_row_groups))
    assert str(sales.schema_arrow.field("sales").type) == "decimal128(18, 4)"
    inputs = pq.read_table(tmp_path / manifest.tables["forecast_inputs"].path)
    assert "sales" not in inputs.column_names
    assert "customers" not in inputs.column_names
    assert inputs.column("is_open").to_pylist() == [None, True]
    template = pq.read_table(tmp_path / manifest.tables["submission_template"].path)
    assert "placeholder_sales" in template.column_names
    assert "sales" not in template.column_names


def test_tampered_parquet_is_not_accepted(tmp_path: Path) -> None:
    """A restored/served manifest must still identify the actual table bytes."""
    config = fixture_project(tmp_path)
    manifest = run_pipeline(config, "synthetic")
    table = tmp_path / manifest.tables["daily_sales"].path
    table.write_bytes(table.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum changed"):
        verify_manifest(config, "synthetic")


def test_invalid_labels_never_publish_a_manifest(tmp_path: Path) -> None:
    """Broken raw inputs fail before any normalized dataset is advertised."""
    config = fixture_project(tmp_path)
    source = tmp_path / "data" / "raw" / "synthetic" / "train.csv"
    source.write_text(source.read_text().replace("10.00", "-10.00"), encoding="utf-8")
    with pytest.raises(ValueError, match="Source validation failed"):
        run_pipeline(config, "synthetic")
    assert not (tmp_path / "data" / "processed" / "synthetic" / "manifest.json").exists()


@pytest.mark.parametrize("location", ["C:/private/data", "/tmp/private", "../escape"])
def test_shared_config_rejects_private_absolute_paths(tmp_path: Path, location: str) -> None:
    """Keep local machine paths out of shared YAML."""
    config = fixture_project(tmp_path)
    config.write_text(config.read_text().replace("data/raw/synthetic", location), encoding="utf-8")
    with pytest.raises(ValueError, match="repository-relative"):
        load_config(config)


def test_dataset_profiles_cannot_share_output_locations(tmp_path: Path) -> None:
    """Synthetic preparation must never overwrite the real dataset directory."""
    config = fixture_project(tmp_path)
    config.write_text(
        config.read_text().replace("data/raw/rossmann", "data/raw/synthetic"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="distinct"):
        profile_paths(config, "synthetic")
