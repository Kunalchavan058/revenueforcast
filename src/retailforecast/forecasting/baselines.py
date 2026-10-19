"""Deterministic same-store historical baselines, fixed across all future horizons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import fmean
from typing import Literal

from retailforecast.evaluation.contracts import TrainingHistory
from retailforecast.features.builder import FeatureRow
from retailforecast.features.contracts import SalesObservation

BaselineName = Literal["last_known", "last_weekday", "weekday_average"]
BASELINE_NAMES: tuple[BaselineName, ...] = ("last_known", "last_weekday", "weekday_average")


@dataclass(frozen=True)
class HistoricalBaseline:
    """Origin-frozen state; no recursion or intermediate future actual is required."""

    name: BaselineName
    trained_until: date
    seasonal_weeks: int
    by_store: dict[int, tuple[SalesObservation, ...]]

    def predict(self, features: FeatureRow) -> float | None:
        """Repeat a known value or weekday mean; absent weekday falls back to last actual.

        At h=48, target weekday is still known. Its matching historical observations
        are selected solely from the fitted origin history, never target-7 if that
        date is after the origin. No store history means unsupported, not fake zero.
        """
        key = features.key
        if key.cutoff_date < self.trained_until:
            raise ValueError("Baseline was fitted beyond forecast cutoff")
        rows = self.by_store.get(key.store_id, ())
        if not rows:
            return None
        last = rows[-1].sales
        if self.name == "last_known":
            return last
        weekday = key.target_date.isoweekday()
        matches = [row for row in rows if row.date.isoweekday() == weekday]
        if self.name == "last_weekday":
            return matches[-1].sales if matches else last
        earliest = self.trained_until - timedelta(days=7 * self.seasonal_weeks - 1)
        seasonal = [row.sales for row in matches if row.date >= earliest]
        return fmean(seasonal) if seasonal else last


@dataclass(frozen=True)
class BaselineFactory:
    """Small algorithm adapter with explicitly declared sparse-history fallback."""

    name: BaselineName
    seasonal_weeks: int = 8

    def __post_init__(self) -> None:
        """Validate runtime callers as well as typed/configured uses."""
        if self.name not in BASELINE_NAMES or not 1 <= self.seasonal_weeks <= 52:
            raise ValueError("Unknown baseline or invalid seasonal history length")

    def fit(self, history: TrainingHistory) -> HistoricalBaseline:
        """Build one deterministic store/date-sorted state from the cutoff-safe view."""
        grouped: dict[int, list[SalesObservation]] = {}
        for row in history.observations:
            grouped.setdefault(row.store_id, []).append(row)
        return HistoricalBaseline(
            self.name,
            history.cutoff_date,
            self.seasonal_weeks,
            {
                store: tuple(sorted(rows, key=lambda row: row.date))
                for store, rows in grouped.items()
            },
        )
