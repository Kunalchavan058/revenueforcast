"""Algorithm-independent immutable contracts for chronological evaluation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from retailforecast.features.builder import FeatureRow
from retailforecast.features.contracts import HistoricalAssumptions, SalesObservation

MAX_BACKTEST_STORES = 32
MAX_DEVELOPMENT_FOLDS = 6
MAX_RESULT_ROWS = 100_000


class BacktestConfig(BaseModel):
    """Bound evaluation size and record choices before opening any holdout results."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    horizon_days: Annotated[int, Field(ge=1, le=48)] = 48
    development_folds: Annotated[int, Field(ge=2, le=MAX_DEVELOPMENT_FOLDS)] = 3
    seasonal_weeks: Annotated[int, Field(ge=1, le=52)] = 8
    store_ids: tuple[int, ...]
    seed: int = 42
    closure_policy: Literal["known_plan_zero", "unadjusted"] = "known_plan_zero"
    assumptions: HistoricalAssumptions

    @model_validator(mode="after")
    def validate_stores(self) -> BacktestConfig:
        """Reject duplicates and oversized requests rather than silently sampling stores."""
        if not self.store_ids or len(self.store_ids) > MAX_BACKTEST_STORES:
            raise ValueError(f"Select 1..{MAX_BACKTEST_STORES} stores")
        if len(set(self.store_ids)) != len(self.store_ids) or min(self.store_ids) < 1:
            raise ValueError("Store IDs must be positive and unique")
        return self


class Fold(BaseModel):
    """One forecast origin and its disjoint, subsequent label window."""

    model_config = ConfigDict(frozen=True)
    fold_id: str
    role: Literal["development", "final"]
    cutoff_date: date
    target_end: date


class BacktestPlan(BaseModel):
    """Calendar reservation independent of algorithm outcomes or hyperparameters."""

    model_config = ConfigDict(frozen=True)
    historical_start: date
    historical_end: date
    folds: tuple[Fold, ...]


class TrainingHistory(BaseModel):
    """Only available pre-origin actuals; algorithms never receive scoring labels."""

    model_config = ConfigDict(frozen=True)
    cutoff_date: date
    observations: tuple[SalesObservation, ...]

    @model_validator(mode="after")
    def reject_future(self) -> TrainingHistory:
        """Enforce the fit boundary even for future algorithm adapters."""
        keys = set()
        for row in self.observations:
            if row.date > self.cutoff_date or row.available_as_of > self.cutoff_date:
                raise ValueError("TrainingHistory contains unavailable future actuals")
            key = (row.store_id, row.date)
            if key in keys:
                raise ValueError("Duplicate training store/date")
            keys.add(key)
        return self


class FittedForecaster(Protocol):
    """A fitted algorithm supports direct prediction without seeing actual target y."""

    @property
    def trained_until(self) -> date:
        """Latest permitted fitting label date; must not exceed forecast cutoff."""
        ...

    def predict(self, features: FeatureRow) -> float | None:
        """Return finite sales or None for explicitly unsupported history."""
        ...


class ForecasterFactory(Protocol):
    """Adapter boundary; refit once per origin with a physically filtered history."""

    @property
    def name(self) -> str:
        """Stable algorithm/configuration identifier in comparison outputs."""
        ...

    def fit(self, history: TrainingHistory) -> FittedForecaster:
        """Fit from available actuals only, never the complete source snapshot."""
        ...


class Outcome(BaseModel):
    """Scoring-only actual and observed opening context, never prediction inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    store_id: Annotated[int, Field(gt=0)]
    target_date: date
    actual_sales: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    available_as_of: date
    observed_open: bool | None = None

    @model_validator(mode="after")
    def validate_availability(self) -> Outcome:
        """Reject an outcome claimed known before its business day."""
        if self.available_as_of < self.target_date:
            raise ValueError("Outcome cannot be available before target date")
        return self


def outcome_index(rows: Iterable[Outcome]) -> dict[tuple[int, date], Outcome]:
    """Reject conflicting truth keys instead of taking whichever row arrived last."""
    result: dict[tuple[int, date], Outcome] = {}
    for row in rows:
        key = (row.store_id, row.target_date)
        if key in result:
            raise ValueError("Duplicate outcome store/date")
        result[key] = row
    return result
