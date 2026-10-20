"""Bounded historical reporting and saved-model dashboard contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from retailforecast.forecasting.contracts import (
    MAX_FORECAST_STORES,
    ApiContract,
    ForecastDay,
    ForecastModel,
    ForecastTotals,
    HistoryCoverage,
    PositiveStoreId,
    SalesAmount,
)

MAX_REPORT_DAYS = 1096
DEFAULT_SELECTED_STORES = 3


class HistoryQuery(ApiContract):
    """Inclusive calendar interval and explicit bounded store cohort in one immutable source."""

    dataset_version_id: str
    store_ids: tuple[PositiveStoreId, ...] = Field(min_length=1, max_length=MAX_FORECAST_STORES)
    start_date: date
    end_date: date
    frequency: Literal["day", "week", "month"] = "day"

    @field_validator("store_ids")
    @classmethod
    def unique_stores(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        """Reject duplicate IDs rather than double-counting business totals."""
        if len(values) != len(set(values)):
            raise ValueError("Store IDs must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def valid_period(self) -> HistoryQuery:
        """Keep SQL/report output bounded and dates ordered without silently truncating."""
        days = (self.end_date - self.start_date).days + 1
        if not 1 <= days <= MAX_REPORT_DAYS:
            raise ValueError(f"Choose an ordered interval of at most {MAX_REPORT_DAYS} days")
        return self


class SourceCoverage(ApiContract):
    """Observed-date coverage, unrelated to import timestamp or wall-clock date."""

    dataset_version_id: str
    checksum: str
    observed_from: date
    observed_through: date
    store_count: int
    default_store_ids: tuple[int, ...]


class CoverageResponse(ApiContract):
    """An empty database is explicit rather than a fabricated historical range."""

    coverage: SourceCoverage | None


class ActualPeriod(ApiContract):
    """Observed totals only; partial periods and missing store-days remain visible."""

    period_start: date
    period_end: date
    covered_from: date
    covered_through: date
    observed_store_days: int
    expected_store_days: int
    sales: SalesAmount | None


class StoreActual(ApiContract):
    """Per-store comparison retains zero sales and explicit missing coverage."""

    store_id: int
    sales: SalesAmount | None
    observed_store_days: int
    open_store_days: int
    closed_store_days: int


class WeekdayActual(ApiContract):
    """Mean per observed store-day includes closed-store zeros; missing days are excluded."""

    weekday: int
    observations: int
    sales: SalesAmount | None
    mean_sales: Decimal | None


class HistorySummary(ApiContract):
    """Read-only aggregates for one exact source/filter, not forecast evaluation metrics."""

    query: HistoryQuery
    checksum: str
    observed_from: date | None
    observed_through: date | None
    selected_store_count: int
    observed_store_days: int
    expected_store_days: int
    missing_store_days: int
    total_sales: SalesAmount | None
    open_store_days: int
    closed_store_days: int
    closed_positive_sales_days: int
    series: tuple[ActualPeriod, ...]
    by_store: tuple[StoreActual, ...]
    weekdays: tuple[WeekdayActual, ...]
    sales_unit: str = "source Sales units; currency unspecified"


class StoreCoverage(ApiContract):
    """History actually present for a store in the active compatible source."""

    store_id: int
    observed_from: date
    observed_through: date


class ForecastOptions(ApiContract):
    """Read-only saved-model context; there is no training or forecast side effect."""

    model: ForecastModel | None
    coverage: SourceCoverage | None
    stores: tuple[StoreCoverage, ...] = ()
    sales_delay_days: int = 0
    max_stores: int = MAX_FORECAST_STORES
    max_horizon: int = 48


class ForecastView(ApiContract):
    """Display-only store subset; CSV still exports the complete immutable saved forecast."""

    forecast_id: str
    store_ids: tuple[int, ...]
    points: tuple[ForecastDay, ...]
    totals: ForecastTotals
    actual_data_cutoff: date
    history: tuple[HistoryCoverage, ...]
