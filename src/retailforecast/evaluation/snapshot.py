"""Scoring-only Parquet projection; outcomes remain outside forecasting interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import pyarrow.dataset as ds
from pydantic import BaseModel

from retailforecast.data.file_pipeline import ValidationArtifact
from retailforecast.data.pipeline_config import profile_paths
from retailforecast.evaluation.contracts import Outcome, outcome_index
from retailforecast.features.contracts import HistoricalAssumptions
from retailforecast.features.snapshot import MAX_STORES_PER_BUILD, SCAN_BATCH_ROWS


class _ActualRow(BaseModel):
    store_id: int
    date: date
    sales: float
    is_open: bool | None


def historical_span(config_path: Path, profile: str) -> tuple[date, date]:
    """Read validated coverage metadata to reserve dates without scoring any model."""
    _, _, _, output = profile_paths(config_path, profile)
    report = ValidationArtifact.model_validate_json((output / "validation.json").read_bytes())
    train = report.report.files["train.csv"]
    if train.date_min is None or train.date_max is None:
        raise ValueError("Backtests require labeled train coverage")
    return train.date_min, train.date_max


def load_outcomes(
    config_path: Path,
    profile: str,
    store_ids: Sequence[int],
    assumptions: HistoricalAssumptions,
) -> dict[tuple[int, date], Outcome]:
    """Load actual sales and observed Open only for scoring, after prediction generation.

    Never read competition test or sample submission as truth. The caller must
    verify the snapshot before prediction and once again before publication.
    """
    if not store_ids or len(store_ids) > MAX_STORES_PER_BUILD:
        raise ValueError("Outcome store partition exceeds the feature adapter bound")
    _, _, _, output = profile_paths(config_path, profile)
    dataset = ds.dataset(output / "tables" / "daily_sales.parquet", format="parquet")
    scanner = dataset.scanner(
        columns=["store_id", "date", "sales", "is_open"],
        filter=ds.field("store_id").isin(store_ids),
        batch_size=SCAN_BATCH_ROWS,
    )
    outcomes: list[Outcome] = []
    for batch in scanner.to_batches():
        for values in batch.to_pylist():
            row = _ActualRow.model_validate(values)
            outcomes.append(
                Outcome(
                    store_id=row.store_id,
                    target_date=row.date,
                    actual_sales=row.sales,
                    observed_open=row.is_open,
                    available_as_of=row.date + timedelta(days=assumptions.sales_delay_days),
                )
            )
    return outcome_index(outcomes)
