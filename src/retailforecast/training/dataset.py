"""Build bounded direct training matrices with the shared cutoff-safe feature builder."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

import numpy as np
from numpy.typing import NDArray

from retailforecast.evaluation.contracts import TrainingHistory
from retailforecast.features.builder import FeatureBuilder, FeatureRow, forecast_keys
from retailforecast.features.preprocessing import FittedPreprocessor
from retailforecast.training.contracts import ModeSettings, TrainingSpan

WARMUP_DAYS = 28
TRAINING_HORIZONS = range(1, 49)


def encoded_columns(preprocessing: FittedPreprocessor) -> tuple[str, ...]:
    """Derive fixed one-hot columns from training-only vocabularies, including missing/unseen."""
    result: list[str] = []
    for name in preprocessing.output_columns:
        if name in preprocessing.categories:
            codes = (-2, -1, *range(len(preprocessing.categories[name])))
            result.extend(f"{name}__category_{code}" for code in codes)
        else:
            result.append(name)
    return tuple(result)


def encode_values(
    values: Sequence[float], preprocessing: FittedPreprocessor
) -> NDArray[np.float32]:
    """One-hot encode categorical IDs so trees never interpret their codes as ordered quantities."""
    result: list[float] = []
    for name, value in zip(preprocessing.output_columns, values, strict=True):
        if name in preprocessing.categories:
            codes = (-2, -1, *range(len(preprocessing.categories[name])))
            result.extend(float(value == code) for code in codes)
        else:
            result.append(value)
    return np.asarray(result, dtype=np.float32)


def encode_row(row: FeatureRow, preprocessing: FittedPreprocessor) -> NDArray[np.float32]:
    """Transform inference without fitting any median or vocabulary."""
    return encode_values(preprocessing.transform(row), preprocessing)


@dataclass(frozen=True)
class PreparedData:
    """Fold-local dense float32 matrix, labels and fitted preprocessing."""

    matrix: NDArray[np.float32]
    labels: NDArray[np.float32]
    preprocessing: FittedPreprocessor
    span: TrainingSpan


def prepare_training_data(
    builder: FeatureBuilder, history: TrainingHistory, settings: ModeSettings
) -> PreparedData:
    """Create eligible direct rows with targets/availability <= the fitting cutoff.

    Origins are selected by calendar before reading label values. If the explicit
    row budget requires fewer origins, retain evenly spaced origins across the
    whole requested window, keeping every store and all 48 horizons eligible.
    Missing/unavailable targets are then omitted rather than imputed as zeros.
    """
    if not history.observations:
        raise ValueError("No available history for supervised training")
    stores = tuple(sorted({row.store_id for row in history.observations}))
    first = min(row.date for row in history.observations) + timedelta(days=WARMUP_DAYS)
    if settings.lookback_days is not None:
        first = max(first, history.cutoff_date - timedelta(days=settings.lookback_days - 1))
    last = history.cutoff_date - timedelta(days=1)
    if first > last:
        raise ValueError("Insufficient history after supervised feature warmup")
    origins = [
        first + timedelta(days=offset)
        for offset in range(0, (last - first).days + 1, settings.origin_stride_days)
    ]
    limit = settings.max_rows // (len(stores) * len(TRAINING_HORIZONS))
    if limit < 1:
        raise ValueError("Row budget cannot retain all stores and horizons at one origin")
    capped = len(origins) > limit
    if capped:
        indices = np.linspace(0, len(origins) - 1, num=limit, dtype=int)
        origins = [origins[int(index)] for index in indices]
    view = builder.with_history(history.observations)
    examples = list(
        view.iter_labeled(
            forecast_keys(stores, origins, TRAINING_HORIZONS),
            training_label_end=history.cutoff_date,
        )
    )
    if not examples:
        raise ValueError("No eligible labeled direct training examples")
    preprocessing = FittedPreprocessor.fit(examples, training_label_end=history.cutoff_date)
    matrix = np.stack(
        [encode_values(preprocessing.transform_training(item), preprocessing) for item in examples]
    )
    labels = np.asarray([item.target_sales for item in examples], dtype=np.float32)
    span = TrainingSpan(
        origin_start=min(item.features.key.cutoff_date for item in examples),
        origin_end=max(item.features.key.cutoff_date for item in examples),
        label_start=min(item.features.key.target_date for item in examples),
        label_end=max(item.features.key.target_date for item in examples),
        rows=len(examples),
        origins=len(origins),
        origin_stride_days=settings.origin_stride_days,
        origin_cap_applied=capped,
        store_ids=stores,
    )
    return PreparedData(matrix, labels, preprocessing, span)
