"""Exact aggregation and CSV serialization from the persisted rounded daily forecasts."""

from __future__ import annotations

import calendar
import csv
import io
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from retailforecast.forecasting.contracts import (
    ForecastDay,
    ForecastResponse,
    ForecastTotals,
    PeriodTotal,
    StoreTotal,
)


def period_totals(
    points: Sequence[ForecastDay], frequency: Literal["day", "week", "month"]
) -> tuple[PeriodTotal, ...]:
    """Group by calendar period, reporting the actually covered portion of partial periods."""
    groups: dict[tuple[date, date], list[ForecastDay]] = defaultdict(list)
    for point in points:
        target = point.target_date
        start = end = target
        if frequency == "week":
            start = target - timedelta(days=target.weekday())
            end = start + timedelta(days=6)
        elif frequency == "month":
            start = target.replace(day=1)
            end = target.replace(day=calendar.monthrange(target.year, target.month)[1])
        groups[(start, end)].append(point)
    return tuple(
        PeriodTotal(
            period_start=start,
            period_end=end,
            covered_from=min(row.target_date for row in rows),
            covered_through=max(row.target_date for row in rows),
            days_predicted=len({row.target_date for row in rows}),
            predicted_sales=sum((row.predicted_sales for row in rows), Decimal("0.0000")),
        )
        for (start, end), rows in sorted(groups.items())
    )


def forecast_totals(points: Sequence[ForecastDay]) -> ForecastTotals:
    """Sum stored values, never separately predict a portfolio, week or month."""
    stores = sorted({row.store_id for row in points})
    return ForecastTotals(
        predicted_sales=sum((row.predicted_sales for row in points), Decimal("0.0000")),
        by_store=tuple(
            StoreTotal(
                store_id=store_id,
                predicted_sales=sum(
                    (row.predicted_sales for row in points if row.store_id == store_id),
                    Decimal("0.0000"),
                ),
            )
            for store_id in stores
        ),
        daily=period_totals(points, "day"),
        weekly=period_totals(points, "week"),
        monthly=period_totals(points, "month"),
    )


def forecast_csv(response: ForecastResponse) -> str:
    """Export one row per store-day with frozen model, cutoff and source-date metadata."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "forecast_id",
            "store_id",
            "target_date",
            "horizon_days",
            "predicted_sales",
            "algorithm",
            "model_version_id",
            "model_generation",
            "cutoff_date",
            "actual_data_cutoff",
            "store_actual_data_cutoff",
            "source_available_through",
            "dataset_version_id",
            "generated_at",
            "nonnegative_clamped",
            "closure_adjusted",
        )
    )
    history = {row.store_id: row.observed_through for row in response.data.history}
    for point in response.points:
        writer.writerow(
            (
                response.forecast_id,
                point.store_id,
                point.target_date.isoformat(),
                point.horizon,
                format(point.predicted_sales, ".4f"),
                response.model.algorithm,
                response.model.version_id,
                response.model.generation,
                response.request.cutoff_date.isoformat(),
                response.data.actual_data_cutoff.isoformat(),
                history[point.store_id].isoformat(),
                response.data.source_available_through.isoformat(),
                response.data.dataset_version_id,
                response.generated_at.isoformat(),
                point.nonnegative_clamped,
                point.closure_adjusted,
            )
        )
    return stream.getvalue()
