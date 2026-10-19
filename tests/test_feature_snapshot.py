"""Exercise projected real-format Parquet inputs without Kaggle or a database."""

from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import pytest
from test_file_pipeline import fixture_project

from retailforecast.data.file_pipeline import run_pipeline
from retailforecast.features.contracts import ForecastKey, HistoricalAssumptions
from retailforecast.features.snapshot import load_feature_builder


def test_snapshot_adapter_projects_customers_and_gates_calendar(tmp_path: Path) -> None:
    """Customers can change across file versions without becoming a feature."""
    config = fixture_project(tmp_path)
    run_pipeline(config, "synthetic")
    assumptions = HistoricalAssumptions(
        explanation=(
            "Synthetic historical simulation; metadata asserted known for this example only."
        ),
        metadata_known_as_of=date(2015, 7, 1),
    )
    request = ForecastKey(store_id=9001, cutoff_date=date(2015, 7, 31), horizon_days=1)
    builder = load_feature_builder(config, "synthetic", store_ids=[9001], assumptions=assumptions)
    baseline = builder.build(request).values
    assert baseline["sales_at_cutoff"] == 0.0
    assert baseline["sales_lag_1_from_cutoff"] == 10.0
    assert baseline["target_open"] is None
    assert (
        builder.build(request.model_copy(update={"store_id": 9002})).values["sales_at_cutoff"]
        is None
    )
    raw = tmp_path / "data/raw/synthetic/train.csv"
    reader = csv.DictReader(io.StringIO(raw.read_text()))
    assert reader.fieldnames is not None
    rows = list(reader)
    for row in rows:
        row["Customers"] = "999999"
    with raw.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    run_pipeline(config, "synthetic")
    changed = load_feature_builder(config, "synthetic", store_ids=[9001], assumptions=assumptions)
    assert changed.build(request).values == baseline
    planned = assumptions.model_copy(update={"calendar_known_as_of": date(2015, 7, 31)})
    assert (
        load_feature_builder(config, "synthetic", store_ids=[9001], assumptions=planned)
        .build(request)
        .values["target_promo"]
        is not None
    )
    late = assumptions.model_copy(update={"calendar_known_as_of": date(2015, 8, 1)})
    assert (
        load_feature_builder(config, "synthetic", store_ids=[9001], assumptions=late)
        .build(request)
        .values["target_promo"]
        is None
    )


def test_snapshot_adapter_requires_verified_artifacts_and_bounded_stores(tmp_path: Path) -> None:
    """Reject unsafe expansion and stale/tampered data before exposing a builder."""
    config = fixture_project(tmp_path)
    run_pipeline(config, "synthetic")
    assumptions = HistoricalAssumptions(
        explanation="Synthetic metadata assumption for a bounded test only.",
        metadata_known_as_of=date(2015, 7, 1),
    )
    for stores in ([], list(range(1, 34)), [-1]):
        with pytest.raises(ValueError, match="positive store IDs"):
            load_feature_builder(config, "synthetic", store_ids=stores, assumptions=assumptions)
    manifest = tmp_path / "data/processed/synthetic/manifest.json"
    manifest.write_text(manifest.read_text().replace('"schema_version": 1', '"schema_version": 2'))
    with pytest.raises(ValueError):
        load_feature_builder(config, "synthetic", store_ids=[9001], assumptions=assumptions)
