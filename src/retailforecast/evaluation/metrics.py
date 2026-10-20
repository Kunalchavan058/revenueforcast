"""Coverage-aware business metrics and reproducible segment summaries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from math import fsum, sqrt

from pydantic import BaseModel

from retailforecast.evaluation.runner import PredictionPoint, horizon_bucket


class Metrics(BaseModel):
    """Null metrics mean no eligible observations, never artificial perfect accuracy."""

    requested: int
    labeled: int
    scored: int
    coverage: float
    zero_actuals: int
    rmspe_zero_excluded: int
    labeled_actual_sales_sum: float
    scored_actual_sales_sum: float
    scored_predicted_sales_sum: float
    mae: float | None
    rmse: float | None
    rmspe: float | None


class Segment(BaseModel):
    """One method and reporting axis; week/month refer to target business date."""

    method: str
    axis: str
    value: str
    metrics: Metrics


def calculate_metrics(points: Sequence[PredictionPoint]) -> Metrics:
    """Compute pooled errors, retaining zero actuals in all business summaries."""
    if any(point.status == "pending" for point in points):
        raise ValueError("Cannot summarize unscored predictions")
    labeled = [point for point in points if point.actual_sales is not None]
    scored = [point for point in points if point.status == "scored"]
    percentages = [
        point.squared_percentage_error
        for point in scored
        if point.squared_percentage_error is not None
    ]
    return Metrics(
        requested=len(points),
        labeled=len(labeled),
        scored=len(scored),
        coverage=len(scored) / len(points) if points else 0.0,
        zero_actuals=sum(point.actual_sales == 0 for point in labeled),
        rmspe_zero_excluded=sum(point.actual_sales == 0 for point in scored),
        labeled_actual_sales_sum=fsum(
            point.actual_sales for point in labeled if point.actual_sales is not None
        ),
        scored_actual_sales_sum=fsum(
            point.actual_sales for point in scored if point.actual_sales is not None
        ),
        scored_predicted_sales_sum=fsum(
            point.predicted_sales for point in scored if point.predicted_sales is not None
        ),
        mae=fsum(point.absolute_error for point in scored if point.absolute_error is not None)
        / len(scored)
        if scored
        else None,
        rmse=sqrt(
            fsum(point.squared_error for point in scored if point.squared_error is not None)
            / len(scored)
        )
        if scored
        else None,
        rmspe=sqrt(fsum(percentages) / len(percentages)) if percentages else None,
    )


def summarize(points: Sequence[PredictionPoint], *, exact_horizons: bool = False) -> list[Segment]:
    """Pool common-support points by method, fold, store, horizon, context, week and month."""
    groups: dict[tuple[str, str, str], list[PredictionPoint]] = defaultdict(list)
    for point in points:
        iso = point.target_date.isocalendar()
        context = (
            "unknown"
            if point.observed_open is None
            else "open"
            if point.observed_open
            else "closed"
        )
        dimensions: tuple[tuple[str, str], ...] = (
            ("aggregate", "all"),
            ("fold", point.fold_id),
            ("store", str(point.store_id)),
            ("horizon", horizon_bucket(point.horizon_days)),
            ("observed_open", context),
            ("week", f"{iso.year}-W{iso.week:02d}"),
            ("month", point.target_date.strftime("%Y-%m")),
        )
        if exact_horizons:
            dimensions += (("horizon_day", str(point.horizon_days)),)
        for axis, value in dimensions:
            groups[(point.method, axis, value)].append(point)
    return [
        Segment(method=method, axis=axis, value=value, metrics=calculate_metrics(rows))
        for (method, axis, value), rows in sorted(groups.items())
    ]


def choose_method(segments: Sequence[Segment]) -> str | None:
    """Select by mean development-fold RMSPE, then MAE/name; never inspect final scores.

    Every requested fold row must be scored. All-zero folds have undefined RMSPE
    and cannot silently receive perfect scores or win the Rossmann selection gate.
    """
    by_method: dict[str, list[Metrics]] = defaultdict(list)
    fold_names: dict[str, set[str]] = defaultdict(set)
    for segment in segments:
        if segment.axis == "fold":
            if not segment.value.startswith("development_"):
                raise ValueError("Final holdout must not be passed to model selection")
            if segment.value in fold_names[segment.method]:
                raise ValueError("Duplicate method/fold summary")
            fold_names[segment.method].add(segment.value)
            by_method[segment.method].append(segment.metrics)
    if fold_names and any(
        names != next(iter(fold_names.values())) for names in fold_names.values()
    ):
        raise ValueError("Selection methods must share identical development folds")
    eligible: list[tuple[float, float, str]] = []
    for method, folds in by_method.items():
        if folds and all(
            item.scored == item.requested and item.scored > 0 and item.rmspe is not None
            for item in folds
        ):
            rmspe = fsum(item.rmspe for item in folds if item.rmspe is not None) / len(folds)
            mae = fsum(item.mae for item in folds if item.mae is not None) / len(folds)
            eligible.append((rmspe, mae, method))
    return min(eligible)[2] if eligible else None
