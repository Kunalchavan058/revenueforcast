"""Immutable, date-based feature inputs with explicit knowledge-time contracts."""

from __future__ import annotations

from datetime import date as BusinessDate
from datetime import timedelta
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_HORIZON = 1
MAX_HORIZON = 48
StoreId = Annotated[int, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class FrozenInput(BaseModel):
    """Reject undeclared inputs (including Customers) and prevent later mutation."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ForecastKey(FrozenInput):
    """Identify one direct forecast; target is always cutoff plus horizon days."""

    store_id: StoreId
    cutoff_date: BusinessDate
    horizon_days: Annotated[int, Field(ge=MIN_HORIZON, le=MAX_HORIZON)]

    @property
    def target_date(self) -> BusinessDate:
        """Return the aligned business date without timezone conversion."""
        return self.cutoff_date + timedelta(days=self.horizon_days)


class SalesObservation(FrozenInput):
    """One nonnegative actual, usable only after both business and availability dates."""

    store_id: StoreId
    date: BusinessDate
    sales: Nonnegative
    available_as_of: BusinessDate

    @model_validator(mode="after")
    def validate_availability(self) -> SalesObservation:
        """Reject labels claimed known before the underlying business date."""
        if self.available_as_of < self.date:
            raise ValueError("Sales cannot be available before their business date")
        return self


class StoreSnapshot(FrozenInput):
    """Full replacement metadata snapshot asserted known on available_as_of."""

    store_id: StoreId
    available_as_of: BusinessDate
    store_type: str | None = None
    assortment: str | None = None
    competition_distance: Nonnegative | None = None
    competition_open_since_month: Annotated[int, Field(ge=1, le=12)] | None = None
    competition_open_since_year: Annotated[int, Field(ge=1900, le=2100)] | None = None
    promo2: bool | None = None
    promo2_since_week: Annotated[int, Field(ge=1, le=53)] | None = None
    promo2_since_year: Annotated[int, Field(ge=1900, le=2100)] | None = None
    promo_interval: str | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> StoreSnapshot:
        """Reject malformed supplied schedules rather than guessing month/week values."""
        if self.promo_interval is not None:
            allowed = {
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sept",
                "Oct",
                "Nov",
                "Dec",
            }
            if not set(self.promo_interval.split(",")).issubset(allowed):
                raise ValueError("Unrecognized PromoInterval month")
        if self.promo2_since_week is not None and self.promo2_since_year is not None:
            BusinessDate.fromisocalendar(self.promo2_since_year, self.promo2_since_week, 1)
        return self


class PlanSnapshot(FrozenInput):
    """Full target-day plan revision; missing fields explicitly mean unknown, not zero."""

    store_id: StoreId
    target_date: BusinessDate
    available_as_of: BusinessDate
    is_open: bool | None = None
    promotion: bool | None = None
    state_holiday: str | None = None
    school_holiday: bool | None = None


class HistoricalAssumptions(FrozenInput):
    """Explicit archived-data assumptions; source CSVs do not establish knowledge times."""

    explanation: Annotated[str, Field(min_length=20)]
    metadata_known_as_of: BusinessDate
    calendar_known_as_of: BusinessDate | None = None
    sales_delay_days: Annotated[int, Field(ge=0, le=365)] = 0


class SnapshotContext(FrozenInput):
    """Carry file identity and declared availability assumptions with feature rows."""

    dataset_fingerprint: str
    assumptions: HistoricalAssumptions
