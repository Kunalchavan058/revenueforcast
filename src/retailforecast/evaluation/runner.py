"""Generate forecasts before joining truth; compare algorithms on common support."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from retailforecast.evaluation.contracts import (
    MAX_RESULT_ROWS,
    BacktestConfig,
    Fold,
    ForecasterFactory,
    Outcome,
    TrainingHistory,
)
from retailforecast.features.builder import FeatureBuilder
from retailforecast.features.contracts import ForecastKey
from retailforecast.forecasting.policy import apply_output_policy


class PredictionPoint(BaseModel):
    """Auditable forecast and optional scoring fields; missing labels imply no errors."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    fold_id: str
    method: str
    store_id: int
    cutoff_date: date
    target_date: date
    horizon_days: int
    trained_until: date
    raw_prediction: float | None
    predicted_sales: float | None
    known_open: bool | None
    nonnegative_clamped: bool = False
    closure_adjusted: bool = False
    actual_sales: float | None = None
    observed_open: bool | None = None
    status: Literal[
        "pending",
        "missing_actual",
        "unavailable_actual",
        "unsupported",
        "common_mask_excluded",
        "scored",
    ] = "pending"
    signed_error: float | None = None
    absolute_error: float | None = None
    squared_error: float | None = None
    squared_percentage_error: float | None = None


def generate_predictions(
    builder: FeatureBuilder,
    folds: Sequence[Fold],
    config: BacktestConfig,
    factories: Sequence[ForecasterFactory],
) -> list[PredictionPoint]:
    """Refit per origin, freeze history for every horizon, and never access scoring truth."""
    if not factories or len({item.name for item in factories}) != len(factories):
        raise ValueError("Methods must be nonempty with unique names")
    requested = len(folds) * len(config.store_ids) * config.horizon_days * len(factories)
    if requested > MAX_RESULT_ROWS:
        raise ValueError("Backtest exceeds MAX_RESULT_ROWS; use a smaller explicit store partition")
    result: list[PredictionPoint] = []
    for fold in folds:
        if (fold.target_end - fold.cutoff_date).days != config.horizon_days:
            raise ValueError("Fold horizon disagrees with configuration")
        history = TrainingHistory(
            cutoff_date=fold.cutoff_date,
            observations=tuple(builder.history_at_cutoff(config.store_ids, fold.cutoff_date)),
        )
        fitted = [(factory.name, factory.fit(history)) for factory in factories]
        if any(model.trained_until > fold.cutoff_date for _, model in fitted):
            raise ValueError("Model trained_until exceeds evaluation cutoff")
        for store_id in sorted(config.store_ids):
            for horizon in range(1, config.horizon_days + 1):
                key = ForecastKey(
                    store_id=store_id, cutoff_date=fold.cutoff_date, horizon_days=horizon
                )
                features = builder.build(key)
                flag = features.values["target_open"]
                known_open = None if flag is None else bool(flag)
                for name, model in fitted:
                    raw = model.predict(features)
                    adjustment = apply_output_policy(raw, known_open, config.closure_policy)
                    result.append(
                        PredictionPoint(
                            fold_id=fold.fold_id,
                            method=name,
                            store_id=store_id,
                            cutoff_date=fold.cutoff_date,
                            target_date=key.target_date,
                            horizon_days=horizon,
                            trained_until=model.trained_until,
                            raw_prediction=raw,
                            predicted_sales=adjustment.predicted_sales,
                            known_open=known_open,
                            nonnegative_clamped=adjustment.nonnegative_clamped,
                            closure_adjusted=adjustment.closure_adjusted,
                        )
                    )
    return result


def score_predictions(
    predictions: Sequence[PredictionPoint],
    outcomes: Mapping[tuple[int, date], Outcome],
    *,
    scoring_as_of: date,
) -> list[PredictionPoint]:
    """Join outcomes only after prediction; use the same eligible keys for all methods.

    Observed Open is retrospective segment context, not evidence of a known plan.
    Zero actuals stay in MAE/RMSE and revenue totals; only RMSPE excludes them.
    """
    support: dict[tuple[str, int, date], bool] = {}
    methods: dict[str, set[str]] = {}
    seen: set[tuple[str, str, int, date]] = set()
    for point in predictions:
        identity = (point.fold_id, point.method, point.store_id, point.target_date)
        if identity in seen or point.status != "pending":
            raise ValueError("Predictions must be unique and unscored")
        seen.add(identity)
        methods.setdefault(point.fold_id, set()).add(point.method)
        key = (point.fold_id, point.store_id, point.target_date)
        support[key] = support.get(key, True) and point.predicted_sales is not None
    # A future adapter must return every requested key, including unsupported ones.
    # Omitting difficult rows would otherwise create an unfairly favorable mask.
    for fold_id, store_id, target in support:
        if any((fold_id, method, store_id, target) not in seen for method in methods[fold_id]):
            raise ValueError("Methods have different requested target keys")
    result: list[PredictionPoint] = []
    for point in predictions:
        actual = outcomes.get((point.store_id, point.target_date))
        if actual is None:
            result.append(point.model_copy(update={"status": "missing_actual"}))
            continue
        if actual.available_as_of > scoring_as_of:
            result.append(point.model_copy(update={"status": "unavailable_actual"}))
            continue
        values: dict[str, object] = {
            "actual_sales": actual.actual_sales,
            "observed_open": actual.observed_open,
        }
        if point.predicted_sales is None:
            values["status"] = "unsupported"
        elif not support[(point.fold_id, point.store_id, point.target_date)]:
            values["status"] = "common_mask_excluded"
        else:
            residual = point.predicted_sales - actual.actual_sales
            squared = residual * residual
            percentage = (residual / actual.actual_sales) ** 2 if actual.actual_sales > 0 else None
            if not math.isfinite(squared) or (
                percentage is not None and not math.isfinite(percentage)
            ):
                raise ValueError("Scoring overflow; numerical range exceeds supported precision")
            values.update(
                status="scored",
                signed_error=residual,
                absolute_error=abs(residual),
                squared_error=squared,
                squared_percentage_error=percentage,
            )
        result.append(PredictionPoint.model_validate({**point.model_dump(), **values}))
    return result


def horizon_bucket(horizon: int) -> str:
    """Return agreed inclusive reporting buckets for direct horizons 1 through 48."""
    for upper, label in ((7, "1-7"), (14, "8-14"), (28, "15-28"), (48, "29-48")):
        if 1 <= horizon <= upper:
            return label
    raise ValueError("Horizon must be 1..48")
