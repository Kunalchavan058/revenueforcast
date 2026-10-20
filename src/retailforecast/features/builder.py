"""One direct multi-horizon builder for training, backtesting and future serving."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from statistics import fmean
from types import MappingProxyType

from retailforecast.features.contracts import (
    MAX_HORIZON,
    ForecastKey,
    PlanSnapshot,
    SalesObservation,
    SnapshotContext,
    StoreSnapshot,
)
from retailforecast.features.registry import FEATURE_NAMES, LAG_DAYS, ROLLING_DAYS, FeatureValue

MONTH_TOKENS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class FeatureRow:
    """Predictors and request identity; no target or customer value is attached."""

    key: ForecastKey
    values: Mapping[str, FeatureValue]
    context: SnapshotContext | None = None


@dataclass(frozen=True)
class LabeledExample:
    """Separate supervised label; its availability is not the feature cutoff."""

    features: FeatureRow
    target_sales: float
    label_available_as_of: date

    def __post_init__(self) -> None:
        """Validate standalone examples as well as examples emitted by the builder."""
        if not isfinite(self.target_sales) or self.target_sales < 0:
            raise ValueError("Training targets must be finite and nonnegative")
        if self.label_available_as_of < self.features.key.target_date:
            raise ValueError("Target label cannot be available before target date")


class FeatureBuilder:
    """Index one snapshot, then build lazily without reading labels after each cutoff.

    Duplicate actual store-days or equal-time metadata/plan revisions are rejected.
    Corrections belong in a new dataset version, not an ambiguous in-memory overwrite.
    """

    def __init__(
        self,
        observations: Iterable[SalesObservation],
        stores: Iterable[StoreSnapshot] = (),
        plans: Iterable[PlanSnapshot] = (),
        *,
        context: SnapshotContext | None = None,
    ) -> None:
        """Index typed source records without manufacturing history or future plans."""
        self.context = context
        self._sales: dict[int, dict[date, SalesObservation]] = {}
        for observation in observations:
            by_date = self._sales.setdefault(observation.store_id, {})
            if observation.date in by_date:
                raise ValueError("Duplicate actual store/date; select one dataset version")
            by_date[observation.date] = observation
        self._dates = {store: sorted(rows) for store, rows in self._sales.items()}
        self._stores: dict[int, list[StoreSnapshot]] = {}
        for store in stores:
            self._stores.setdefault(store.store_id, []).append(store)
        self._plans: dict[tuple[int, date], list[PlanSnapshot]] = {}
        for plan in plans:
            self._plans.setdefault((plan.store_id, plan.target_date), []).append(plan)
        for snapshots in self._stores.values():
            snapshots.sort(key=lambda item: item.available_as_of)
            if len({item.available_as_of for item in snapshots}) != len(snapshots):
                raise ValueError("Duplicate metadata availability date")
        for revisions in self._plans.values():
            revisions.sort(key=lambda item: item.available_as_of)
            if len({item.available_as_of for item in revisions}) != len(revisions):
                raise ValueError("Duplicate plan availability date")

    def _observed(self, store_id: int, day: date, cutoff: date) -> float | None:
        observation = self._sales.get(store_id, {}).get(day)
        if observation is None or day > cutoff or observation.available_as_of > cutoff:
            return None
        return observation.sales

    def _metadata(self, key: ForecastKey) -> StoreSnapshot | None:
        return next(
            (
                item
                for item in reversed(self._stores.get(key.store_id, []))
                if item.available_as_of <= key.cutoff_date
            ),
            None,
        )

    def _plan(self, key: ForecastKey) -> PlanSnapshot | None:
        revisions = self._plans.get((key.store_id, key.target_date), [])
        return next(
            (item for item in reversed(revisions) if item.available_as_of <= key.cutoff_date), None
        )

    def build(self, key: ForecastKey) -> FeatureRow:
        """Build one row using only as-of history, metadata and explicitly known plans.

        For t=July 31 and target=August 7, lag_1 reads July 30. The seven-day
        mean reads July 25..31 inclusive, never August 1..6 actuals. Missing
        calendar dates stay missing rather than shifting to another row/store.
        """
        cutoff, target = key.cutoff_date, key.target_date
        store, plan = self._metadata(key), self._plan(key)
        values: dict[str, FeatureValue] = {
            "store_id": str(key.store_id),
            "horizon_days": float(key.horizon_days),
            "target_day_of_week": float(target.isoweekday()),
            "target_month": float(target.month),
            "target_year": float(target.year),
            "target_day_of_year": float(target.timetuple().tm_yday),
            "store_type": store.store_type if store else None,
            "assortment": store.assortment if store else None,
            "competition_distance": store.competition_distance if store else None,
            "competition_months_at_cutoff": competition_months(store, cutoff),
            "promo2_active_target": promo2_active(store, target),
            "target_open": optional_flag(plan.is_open) if plan else None,
            "target_promo": optional_flag(plan.promotion) if plan else None,
            "target_state_holiday": plan.state_holiday if plan else None,
            "target_school_holiday": optional_flag(plan.school_holiday) if plan else None,
            "sales_at_cutoff": self._observed(key.store_id, cutoff, cutoff),
            "days_since_last_sales": self._history_age(key),
        }
        for lag in LAG_DAYS:
            values[f"sales_lag_{lag}_from_cutoff"] = self._observed(
                key.store_id, cutoff - timedelta(days=lag), cutoff
            )
        for window in ROLLING_DAYS:
            # The window is calendar based and inclusive of t, so a delayed or
            # absent day reduces coverage; it never becomes an invented zero.
            observed = [
                self._observed(key.store_id, cutoff - timedelta(days=offset), cutoff)
                for offset in range(window)
            ]
            present = [value for value in observed if value is not None]
            values[f"sales_mean_{window}_through_cutoff"] = fmean(present) if present else None
            values[f"sales_count_{window}_through_cutoff"] = float(len(present))
        if tuple(values) != FEATURE_NAMES:
            raise ValueError("Builder output differs from registry order; update both deliberately")
        return FeatureRow(key, MappingProxyType(values), self.context)

    def _history_age(self, key: ForecastKey) -> float | None:
        dates = self._dates.get(key.store_id, [])
        # Bisect excludes all future dates before searching availability; this
        # remains independent of adding, changing or erasing future actuals.
        stop = bisect_right(dates, key.cutoff_date)
        for index in range(stop - 1, -1, -1):
            day = dates[index]
            if self._observed(key.store_id, day, key.cutoff_date) is not None:
                return float((key.cutoff_date - day).days)
        return None

    def with_history(self, observations: Iterable[SalesObservation]) -> FeatureBuilder:
        """Reuse as-of metadata/plans with an explicitly filtered fitting history.

        A training adapter supplies TrainingHistory, so target labels beyond its
        fold end are physically absent. Existing per-row knowledge gates still
        apply to metadata/plans at every earlier training origin.
        """
        return FeatureBuilder(
            observations,
            (item for snapshots in self._stores.values() for item in snapshots),
            (item for revisions in self._plans.values() for item in revisions),
            context=self.context,
        )

    def history_at_cutoff(
        self, store_ids: Iterable[int], cutoff_date: date
    ) -> Iterator[SalesObservation]:
        """Yield sorted immutable actuals known by cutoff for model fitting only.

        The evaluation runner hands this filtered view to a forecaster, never the
        complete builder or its future label index. Delayed reports remain hidden.
        """
        for store_id in sorted(set(store_ids)):
            dates = self._dates.get(store_id, [])
            for day in dates[: bisect_right(dates, cutoff_date)]:
                observation = self._sales[store_id][day]
                if observation.available_as_of <= cutoff_date:
                    yield observation

    def iter_features(self, keys: Iterable[ForecastKey]) -> Iterator[FeatureRow]:
        """Yield shared inference/backtest inputs without materializing a Cartesian dataset."""
        for key in keys:
            yield self.build(key)

    def iter_labeled(
        self, keys: Iterable[ForecastKey], *, training_label_end: date
    ) -> Iterator[LabeledExample]:
        """Yield aligned labels available by fold end; omit unavailable targets.

        A later training row's historical inputs may legitimately include earlier
        labels, but every row retains its own cutoff. Fold end constrains both
        target business date and label availability, not merely cutoff date.
        """
        for key in keys:
            label = self._sales.get(key.store_id, {}).get(key.target_date)
            if key.target_date > training_label_end or label is None:
                continue
            if label.available_as_of > training_label_end:
                continue
            yield LabeledExample(self.build(key), label.sales, label.available_as_of)


def optional_flag(value: bool | None) -> float | None:
    """Preserve unknown booleans as missing rather than claiming a false fact."""
    return None if value is None else float(value)


def competition_months(store: StoreSnapshot | None, cutoff: date) -> float | None:
    """Compute month-level competition age at cutoff from known metadata only."""
    if (
        store is None
        or store.competition_open_since_month is None
        or store.competition_open_since_year is None
    ):
        return None
    months = 12 * (cutoff.year - store.competition_open_since_year)
    months += cutoff.month - store.competition_open_since_month
    return float(months) if months >= 0 else None


def promo2_active(store: StoreSnapshot | None, target: date) -> float | None:
    """Expand a known Promo2 schedule; do not treat missing schedules as no promotion."""
    if store is None or store.promo2 is None:
        return None
    if not store.promo2:
        return 0.0
    if (
        store.promo2_since_week is None
        or store.promo2_since_year is None
        or store.promo_interval is None
    ):
        return None
    start = date.fromisocalendar(store.promo2_since_year, store.promo2_since_week, 1)
    return float(
        target >= start and MONTH_TOKENS[target.month - 1] in store.promo_interval.split(",")
    )


def forecast_keys(
    store_ids: Iterable[int],
    cutoffs: Iterable[date],
    horizons: Iterable[int] = range(1, MAX_HORIZON + 1),
) -> Iterator[ForecastKey]:
    """Expand requested origins lazily; default direct horizons are 1 through 48."""
    days, steps = tuple(cutoffs), tuple(horizons)
    for store_id in store_ids:
        for cutoff in days:
            for horizon in steps:
                yield ForecastKey(store_id=store_id, cutoff_date=cutoff, horizon_days=horizon)
