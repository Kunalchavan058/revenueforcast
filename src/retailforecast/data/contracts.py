"""Typed source-row and validation contracts; no engineered features are defined."""

from __future__ import annotations

from datetime import date as BusinessDate
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PositiveInt = Annotated[int, Field(gt=0)]
NonnegativeInt = Annotated[int, Field(ge=0)]
Binary = Annotated[int, Field(ge=0, le=1)]
NonnegativeDecimal = Annotated[
    Decimal, Field(ge=0, max_digits=18, decimal_places=4, allow_inf_nan=False)
]


class SourceRow(BaseModel):
    """Parse CSV scalars explicitly; blank optional attributes become missing."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_blanks(cls, value: object) -> object:
        """Trim CSV values and preserve missingness instead of inventing zeros."""
        if isinstance(value, str):
            return value.strip() or None
        return value


class StoreRow(SourceRow):
    """Validate original store attributes, allowing missing optional metadata."""

    store_id: PositiveInt = Field(alias="Store")
    store_type: Literal["a", "b", "c", "d"] | None = Field(None, alias="StoreType")
    assortment: Literal["a", "b", "c"] | None = Field(None, alias="Assortment")
    competition_distance: NonnegativeDecimal | None = Field(None, alias="CompetitionDistance")
    competition_open_since_month: Annotated[int, Field(ge=1, le=12)] | None = Field(
        None,
        alias="CompetitionOpenSinceMonth",
    )
    competition_open_since_year: Annotated[int, Field(ge=1900, le=2100)] | None = Field(
        None,
        alias="CompetitionOpenSinceYear",
    )
    promo2: Binary | None = Field(None, alias="Promo2")
    promo2_since_week: Annotated[int, Field(ge=1, le=53)] | None = Field(
        None,
        alias="Promo2SinceWeek",
    )
    promo2_since_year: Annotated[int, Field(ge=1900, le=2100)] | None = Field(
        None,
        alias="Promo2SinceYear",
    )
    promo_interval: str | None = Field(None, alias="PromoInterval")

    @field_validator("promo_interval")
    @classmethod
    def check_promo_months(cls, value: str | None) -> str | None:
        """Reject unknown promotion month tokens while retaining source intervals."""
        months = {
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
        if value is not None and not set(value.split(",")).issubset(months):
            raise ValueError("PromoInterval must contain recognized month abbreviations")
        return value


class CalendarRow(SourceRow):
    """Validate store/date inputs without treating them as observed labels."""

    store_id: PositiveInt = Field(alias="Store")
    date: BusinessDate = Field(alias="Date")
    day_of_week: Annotated[int, Field(ge=1, le=7)] = Field(alias="DayOfWeek")
    is_open: Binary | None = Field(None, alias="Open")
    promotion: Binary = Field(alias="Promo")
    state_holiday: Literal["0", "a", "b", "c"] = Field(alias="StateHoliday")
    school_holiday: Binary = Field(alias="SchoolHoliday")

    @model_validator(mode="after")
    def check_weekday(self) -> CalendarRow:
        """Reject contradictory date/weekday inputs rather than silently correcting them."""
        if self.day_of_week != self.date.isoweekday():
            raise ValueError("DayOfWeek does not match Date")
        return self


class SaleRow(CalendarRow):
    """Observed historical labels; Customers are retained only for source auditing."""

    sales: NonnegativeDecimal = Field(alias="Sales")
    customers: NonnegativeInt = Field(alias="Customers")
    is_open: Binary = Field(alias="Open")


class InputRow(CalendarRow):
    """Unlabeled competition inputs; Sales and Customers are forbidden extra columns."""

    submission_id: PositiveInt = Field(alias="Id")


class SubmissionRow(SourceRow):
    """Submission template placeholders, never actual sales or model predictions."""

    submission_id: PositiveInt = Field(alias="Id")
    sales: NonnegativeDecimal = Field(alias="Sales")


class ValidationIssue(BaseModel):
    """An actionable bounded issue sample; aggregate counters are never truncated."""

    file: str
    row: int | None = None
    message: str


class FileReport(BaseModel):
    """Full counts and spans for one source file, plus bounded issue examples."""

    filename: str
    checksum: str
    rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    date_min: BusinessDate | None = None
    date_max: BusinessDate | None = None
    unique_stores: int = 0
    missingness: dict[str, int] = Field(default_factory=dict)
    duplicates: int = 0
    closed_stores: int = 0
    closed_with_sales: int = 0
    missing_open: int = 0
    zero_sales_when_open: int = 0
    missing_optional_columns: list[str] = Field(default_factory=list)


class ValidationReport(BaseModel):
    """Bundle identity, policy and reports for immutable validate-first ingestion."""

    contract_version: str = "rossmann-v1"
    source: str = "kaggle:rossmann-store-sales"
    checksum: str
    minimum_date: BusinessDate
    maximum_date: BusinessDate
    availability_policy: str
    valid: bool = True
    files: dict[str, FileReport] = Field(default_factory=dict)
    issues: list[ValidationIssue] = Field(default_factory=list)
    issue_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class ImportRequest(BaseModel):
    """Explicit CLI input contract; local paths are never accepted over HTTP."""

    source_dir: str
    dry_run: bool = True
    minimum_date: BusinessDate = BusinessDate(2000, 1, 1)
    maximum_date: BusinessDate
    availability_policy: str = (
        "Historical simulation: train labels available on their business date; "
        "store metadata and competition plans are assumed known at forecast cutoff. "
        "Archived CSV files do not prove real-world historical availability."
    )


class ImportResponse(BaseModel):
    """Validated outcome; duplicate means the original dataset was reused unchanged."""

    state: Literal["validated", "rejected", "succeeded", "duplicate"]
    dataset_version_id: str | None = None
    import_job_id: str | None = None
    report: ValidationReport
