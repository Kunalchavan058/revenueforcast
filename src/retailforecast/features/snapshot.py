"""Bounded projected Parquet adapter with explicit archived availability assumptions."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from pathlib import Path

import pyarrow.dataset as ds
from pydantic import BaseModel

from retailforecast.data.file_pipeline import verify_manifest
from retailforecast.data.pipeline_config import profile_paths
from retailforecast.features.builder import FeatureBuilder
from retailforecast.features.contracts import (
    HistoricalAssumptions,
    PlanSnapshot,
    SalesObservation,
    SnapshotContext,
    StoreSnapshot,
)

SCAN_BATCH_ROWS = 10_000
MAX_STORES_PER_BUILD = 32


class _HistoricalRow(BaseModel):
    store_id: int
    date: date
    sales: float


class _CalendarRow(BaseModel):
    store_id: int
    date: date
    is_open: bool | None
    promotion: bool | None
    state_holiday: str | None
    school_holiday: bool | None


def _rows(
    path: Path, columns: Sequence[str], store_ids: tuple[int, ...]
) -> Iterator[dict[str, object]]:
    dataset = ds.dataset(path, format="parquet")
    scanner = dataset.scanner(
        columns=list(columns),
        filter=ds.field("store_id").isin(store_ids),
        batch_size=SCAN_BATCH_ROWS,
    )
    for batch in scanner.to_batches():
        for row in batch.to_pylist():
            yield dict(row)


def load_feature_builder(
    config_path: Path,
    profile_name: str,
    *,
    store_ids: Sequence[int],
    assumptions: HistoricalAssumptions,
) -> FeatureBuilder:
    """Load a verified snapshot for at most 32 stores; project Customers out entirely.

    Call once per bounded store partition; stream examples rather than expanding
    every store/cutoff/horizon. Known-time assumptions are required, never inferred
    from the CSV download or import time. With no calendar assumption, no plans
    are loaded; target flags stay unknown. No SQL connection is opened.
    """
    selected = tuple(sorted(set(store_ids)))
    if not selected or len(selected) > MAX_STORES_PER_BUILD or any(item <= 0 for item in selected):
        raise ValueError(
            f"Select between 1 and {MAX_STORES_PER_BUILD} positive store IDs per build"
        )
    manifest = verify_manifest(config_path, profile_name)
    _, _, _, output = profile_paths(config_path, profile_name)
    tables = output / "tables"

    def observations() -> Iterator[SalesObservation]:
        for values in _rows(
            tables / "daily_sales.parquet", ("store_id", "date", "sales"), selected
        ):
            row = _HistoricalRow.model_validate(values)
            yield SalesObservation(
                store_id=row.store_id,
                date=row.date,
                sales=row.sales,
                available_as_of=row.date + timedelta(days=assumptions.sales_delay_days),
            )

    def stores() -> Iterator[StoreSnapshot]:
        columns = tuple(name for name in StoreSnapshot.model_fields if name != "available_as_of")
        for values in _rows(tables / "stores.parquet", columns, selected):
            yield StoreSnapshot.model_validate(
                {**values, "available_as_of": assumptions.metadata_known_as_of}
            )

    def plans() -> Iterator[PlanSnapshot]:
        if assumptions.calendar_known_as_of is None:
            return
        columns = ("store_id", "date", "is_open", "promotion", "state_holiday", "school_holiday")
        for name in ("daily_sales", "forecast_inputs"):
            for values in _rows(tables / f"{name}.parquet", columns, selected):
                row = _CalendarRow.model_validate(values)
                yield PlanSnapshot(
                    store_id=row.store_id,
                    target_date=row.date,
                    available_as_of=assumptions.calendar_known_as_of,
                    is_open=row.is_open,
                    promotion=row.promotion,
                    state_holiday=row.state_holiday,
                    school_holiday=row.school_holiday,
                )

    return FeatureBuilder(
        observations(),
        stores(),
        plans(),
        context=SnapshotContext(
            dataset_fingerprint=manifest.dataset_fingerprint, assumptions=assumptions
        ),
    )
