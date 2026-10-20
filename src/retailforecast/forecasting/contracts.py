"""Versioned forecast API inputs, persisted provenance and exact sales totals."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from retailforecast.features.contracts import MAX_HORIZON, HistoricalAssumptions
from retailforecast.features.snapshot import MAX_STORES_PER_BUILD
from retailforecast.training.contracts import Algorithm

MAX_FORECAST_STORES = MAX_STORES_PER_BUILD
MAX_FORECAST_POINTS = MAX_FORECAST_STORES * MAX_HORIZON
SALES_DECIMAL_PLACES = 4
PositiveStoreId = Annotated[int, Field(gt=0, strict=True)]
SalesAmount = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=SALES_DECIMAL_PLACES)]
ClosurePolicy = Literal["known_plan_zero", "unadjusted"]


class ApiContract(BaseModel):
    """Reject unknown fields and nonfinite values at the public/persistence boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ScenarioPlan(ApiContract):
    """A user-asserted full replacement plan known by the request's information cutoff."""

    store_id: PositiveStoreId
    target_date: date
    available_as_of: date
    provenance: str = Field(min_length=3, max_length=200)
    is_open: StrictBool | None = None
    promotion: StrictBool | None = None
    state_holiday: str | None = Field(default=None, min_length=1, max_length=20)
    school_holiday: StrictBool | None = None

    @model_validator(mode="after")
    def require_plan_values(self) -> ScenarioPlan:
        """Reject empty plans or claims without an identifiable source."""
        if not self.provenance.strip() or all(
            value is None
            for value in (self.is_open, self.promotion, self.state_holiday, self.school_holiday)
        ):
            raise ValueError(
                "Supply a nonempty plan provenance and at least one known future value"
            )
        return self


class ForecastRequest(ApiContract):
    """Request direct daily forecasts; no training, hyperparameter or actual-target inputs."""

    store_ids: tuple[PositiveStoreId, ...] = Field(min_length=1, max_length=MAX_FORECAST_STORES)
    cutoff_date: date
    horizon_days: int = Field(ge=1, le=MAX_HORIZON, strict=True)
    scenarios: tuple[ScenarioPlan, ...] = Field(default=(), max_length=MAX_FORECAST_POINTS)

    @field_validator("store_ids")
    @classmethod
    def canonical_store_ids(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        """Reject duplicates and normalize order for deterministic output."""
        if len(set(values)) != len(values):
            raise ValueError("Store IDs must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_future_plans(self) -> ForecastRequest:
        """Only declared target dates and information already known by cutoff may enter."""
        if self.cutoff_date > date.max - timedelta(days=self.horizon_days):
            raise ValueError("Cutoff plus horizon exceeds the supported calendar")
        target_end = self.cutoff_date + timedelta(days=self.horizon_days)
        seen: set[tuple[int, date]] = set()
        for plan in self.scenarios:
            key = (plan.store_id, plan.target_date)
            if (
                plan.store_id not in self.store_ids
                or not self.cutoff_date < plan.target_date <= target_end
            ):
                raise ValueError("Scenario store/date must be in the requested forecast window")
            if plan.available_as_of > self.cutoff_date:
                raise ValueError("Future scenario information must be known at or before cutoff")
            if key in seen:
                raise ValueError("Only one full scenario plan per store/target date is supported")
            seen.add(key)
        return self


class ForecastDay(ApiContract):
    """One rounded store-day estimate; flags disclose the evaluated output adjustments."""

    store_id: int
    target_date: date
    horizon: int
    predicted_sales: SalesAmount
    known_open: bool | None
    nonnegative_clamped: bool
    closure_adjusted: bool


class HistoryCoverage(ApiContract):
    """Observed business-date coverage actually visible to this request, per store."""

    store_id: int
    observed_from: date
    observed_through: date
    observations: int
    missing_days_in_last_28: int


class ForecastModel(ApiContract):
    """Pin version/generation and fitted schema so switches cannot mix model identities."""

    version_id: str
    algorithm: Algorithm
    generation: int
    trained_until: date
    feature_schema_fingerprint: str


class ForecastData(ApiContract):
    """Expose historical source dates separately from the time a forecast was generated."""

    dataset_version_id: str
    dataset_fingerprint: str
    source_checksum: str
    feature_context_dataset_fingerprint: str | None = None
    source: str
    source_available_through: date
    actual_data_cutoff: date
    source_kind: Literal["imported_historical_snapshot"] = "imported_historical_snapshot"
    history: tuple[HistoryCoverage, ...]
    assumptions: HistoricalAssumptions


class OutputPolicy(ApiContract):
    """The same nonnegative/closure policy used during evaluation, with export precision."""

    clip_negative_sales: Literal[True] = True
    closure_policy: ClosurePolicy
    decimal_places: Literal[4] = 4
    totals_method: Literal["sum_rounded_store_daily_forecasts"] = (
        "sum_rounded_store_daily_forecasts"
    )
    sales_unit: Literal["source Sales units; currency unspecified"] = (
        "source Sales units; currency unspecified"
    )


class ForecastContext(ApiContract):
    """Persist complete reproducibility metadata independently from normalized point rows."""

    schema_version: Literal[1] = 1
    request: ForecastRequest
    input_fingerprint: str
    model: ForecastModel
    data: ForecastData
    policy: OutputPolicy
    warnings: tuple[str, ...]


class PeriodTotal(ApiContract):
    """Sum only requested target dates, disclosing partial calendar weeks/months."""

    period_start: date
    period_end: date
    covered_from: date
    covered_through: date
    days_predicted: int
    predicted_sales: SalesAmount


class StoreTotal(ApiContract):
    """Sum rounded daily predictions for one selected store."""

    store_id: int
    predicted_sales: SalesAmount


class ForecastTotals(ApiContract):
    """Daily, ISO-week and calendar-month sums over the requested store cohort."""

    predicted_sales: SalesAmount
    by_store: tuple[StoreTotal, ...]
    daily: tuple[PeriodTotal, ...]
    weekly: tuple[PeriodTotal, ...]
    monthly: tuple[PeriodTotal, ...]


class ForecastResponse(ForecastContext):
    """A saved immutable forecast, never retrospective target values or invented errors."""

    forecast_id: str
    generated_at: datetime
    points: tuple[ForecastDay, ...]
    totals: ForecastTotals


class ErrorDetail(ApiContract):
    """Stable domain error codes and actionable messages without private filesystem paths."""

    code: str
    message: str


class ErrorResponse(ApiContract):
    """Envelope used by documented domain errors; input errors retain FastAPI's 422 shape."""

    error: ErrorDetail
