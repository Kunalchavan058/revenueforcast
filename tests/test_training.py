"""Genuine native fitting, cutoff safety, reproducibility and portable serialization."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from retailforecast.evaluation.contracts import TrainingHistory
from retailforecast.features.builder import FeatureBuilder
from retailforecast.features.contracts import (
    ForecastKey,
    HistoricalAssumptions,
    SalesObservation,
    SnapshotContext,
)
from retailforecast.training.adapters import NativeTreeAdapter
from retailforecast.training.contracts import Algorithm, InternalParameters, ModeSettings
from retailforecast.training.dataset import PreparedData, encoded_columns, prepare_training_data

CUTOFF = date(2015, 4, 10)


def small_settings() -> ModeSettings:
    """Use a bounded but genuine all-horizon fixture, not a fabricated model."""
    return ModeSettings(
        lookback_days=60,
        origin_stride_days=14,
        max_rows=288,
        max_trials_per_algorithm=1,
        elapsed_seconds=60,
    )


def synthetic_builder(future_value: float | None = None) -> FeatureBuilder:
    """Create explicit synthetic actuals with weekday variation and two distinct stores."""
    assumptions = HistoricalAssumptions(
        explanation="Synthetic training test only; no future plans are asserted known.",
        metadata_known_as_of=date(2015, 1, 1),
    )
    context = SnapshotContext(
        dataset_fingerprint="synthetic-training-test", assumptions=assumptions
    )
    rows = [
        SalesObservation(
            store_id=store,
            date=date(2015, 1, 1) + timedelta(days=offset),
            sales=float(100 + offset * 2 + store * 20) if offset % 7 != 3 else 0.0,
            available_as_of=date(2015, 1, 1) + timedelta(days=offset),
        )
        for offset in range(100)
        for store in (1, 2)
    ]
    if future_value is not None:
        rows.extend(
            SalesObservation(
                store_id=store,
                date=CUTOFF + timedelta(days=offset),
                available_as_of=CUTOFF + timedelta(days=offset),
                sales=future_value,
            )
            for offset in range(1, 49)
            for store in (1, 2)
        )
    return FeatureBuilder(rows, context=context)


def prepared(builder: FeatureBuilder | None = None) -> PreparedData:
    """Use the same public fit boundary as the evaluation runner."""
    builder = builder or synthetic_builder()
    history = TrainingHistory(
        cutoff_date=CUTOFF, observations=tuple(builder.history_at_cutoff([1, 2], CUTOFF))
    )
    return prepare_training_data(builder, history, small_settings())


@pytest.mark.parametrize("algorithm", ["xgboost", "lightgbm"])
def test_native_adapter_reproducibility_and_serialization(
    algorithm: Algorithm, tmp_path: Path
) -> None:
    """Both native libraries genuinely fit and preserve predictions after save/load."""
    data = prepared()
    params = InternalParameters(trees=8, max_depth=2, learning_rate=0.1, min_leaf_rows=2)
    adapter = NativeTreeAdapter(algorithm)
    first = adapter.fit(data, params, seed=42, n_jobs=1)
    second = adapter.fit(data, params, seed=42, n_jobs=1)
    path = tmp_path / algorithm
    first.save(path)
    loaded = adapter.load(path)
    for horizon in (1, 48):
        row = synthetic_builder().build(
            ForecastKey(store_id=1, cutoff_date=CUTOFF, horizon_days=horizon)
        )
        assert np.isfinite(first.predict(row))
        assert first.predict(row) == pytest.approx(second.predict(row), rel=1e-6, abs=1e-6)
        assert first.predict(row) == pytest.approx(loaded.predict(row), rel=1e-6, abs=1e-6)
    assert loaded.metadata.training_span.rows > 0
    assert loaded.preprocessing.training_label_end == CUTOFF
    assert "horizon_days" in loaded.metadata.encoded_columns
    assert not any("customer" in name.lower() for name in loaded.metadata.encoded_columns)
    assert adapter.capabilities().cpu_only
    with pytest.raises(ValueError, match="already exists"):
        first.save(path)


def test_training_matrix_cannot_use_post_cutoff_sales_and_categories_are_one_hot() -> None:
    """Mutating/erasing all future actuals leaves fit inputs unchanged."""
    original = prepared(synthetic_builder(10.0))
    changed = prepared(synthetic_builder(999999.0))
    erased = prepared(synthetic_builder())
    np.testing.assert_array_equal(original.matrix, changed.matrix)
    np.testing.assert_array_equal(original.labels, changed.labels)
    np.testing.assert_array_equal(original.matrix, erased.matrix)
    assert original.span.label_end <= CUTOFF
    assert original.span.rows <= small_settings().max_rows
    assert original.span.origin_cap_applied
    columns = encoded_columns(original.preprocessing)
    store_columns = [
        index for index, name in enumerate(columns) if name.startswith("store_id__category_")
    ]
    np.testing.assert_array_equal(
        original.matrix[:, store_columns].sum(axis=1), np.ones(len(original.labels))
    )


@pytest.mark.parametrize("algorithm", ["xgboost", "lightgbm"])
def test_model_guards_future_cutoff_unseen_store_and_tampered_bundle(
    algorithm: Algorithm, tmp_path: Path
) -> None:
    """A fitted model cannot serve earlier cutoffs, uncovered stores or corrupted bytes."""
    model = NativeTreeAdapter(algorithm).fit(
        prepared(),
        InternalParameters(trees=3, max_depth=2, learning_rate=0.1, min_leaf_rows=2),
        seed=42,
        n_jobs=1,
    )
    builder = synthetic_builder()
    with pytest.raises(ValueError, match="beyond forecast cutoff"):
        model.predict(
            builder.build(
                ForecastKey(store_id=1, cutoff_date=CUTOFF - timedelta(days=1), horizon_days=1)
            )
        )
    with pytest.raises(ValueError, match="unseen store"):
        model.predict(builder.build(ForecastKey(store_id=999, cutoff_date=CUTOFF, horizon_days=1)))
    with pytest.raises(ValidationError):
        ForecastKey(store_id=1, cutoff_date=CUTOFF, horizon_days=49)
    path = tmp_path / algorithm
    model.save(path)
    target = path / "preprocessing.json"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum"):
        NativeTreeAdapter(algorithm).load(path)


def test_native_fit_rejects_nonfinite_training_data() -> None:
    """Malformed arrays fail before native libraries can publish a model."""
    data = prepared()
    data.matrix[0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        NativeTreeAdapter("xgboost").fit(
            data,
            InternalParameters(trees=2, max_depth=2, learning_rate=0.1, min_leaf_rows=2),
            seed=42,
            n_jobs=1,
        )
