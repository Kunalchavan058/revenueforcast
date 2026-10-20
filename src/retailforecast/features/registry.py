"""Single source of truth for V1 predictor order, provenance and generated reference."""

from __future__ import annotations

import argparse
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from retailforecast.data.pipeline_config import content_hash

LAG_DAYS = (1, 7, 28)
ROLLING_DAYS = (7, 28)
FeatureValue = float | str | None
Availability = Literal["static", "historical_at_cutoff", "known_future", "unknown_future"]


class FeatureDefinition(BaseModel):
    """Machine-readable feature contract; predictor=False documents prohibited sources."""

    model_config = ConfigDict(frozen=True)
    name: str
    explanation: str
    source_csv: str
    data_type: Literal["numeric", "categorical"]
    derivation: str
    missing_policy: str
    temporal_availability: Availability
    lineage: str
    leakage_risk: str
    serving_requirement: str
    predictor: bool = True


def _definition(
    name: str,
    explanation: str,
    source: str,
    dtype: Literal["numeric", "categorical"],
    derivation: str,
    availability: Availability,
    requirement: str,
    *,
    predictor: bool = True,
) -> FeatureDefinition:
    return FeatureDefinition(
        name=name,
        explanation=explanation,
        source_csv=source,
        data_type=dtype,
        derivation=derivation,
        temporal_availability=availability,
        missing_policy=(
            "Excluded; no model imputation or encoding."
            if not predictor
            else (
                "Preserve None; fitted numeric median (empty-column fallback 0) plus missing flag; "
                "categorical missing=-2, unseen=-1. Counts remain observed counts."
            )
        ),
        lineage=f"Versioned {source}; join by store_id and business date where applicable.",
        leakage_risk=(
            "Never a predictor."
            if not predictor
            else (
                "Gate source availability at cutoff; never inspect post-cutoff "
                "actuals or refit at serving."
            )
        ),
        serving_requirement=requirement,
        predictor=predictor,
    )


def _definitions() -> tuple[FeatureDefinition, ...]:
    history = "Observations with date <= cutoff AND available_as_of <= cutoff, within this store."
    metadata = "Latest full store snapshot with available_as_of <= cutoff; unknown store allowed."
    plans = (
        "Latest full plan snapshot for target with available_as_of <= "
        "cutoff; missing stays unknown."
    )
    specs = [
        _definition(
            "store_id",
            "Store identity; new stores use the saved unknown category.",
            "train.csv/test.csv/store.csv:Store",
            "categorical",
            "String form of request store_id.",
            "static",
            "Positive store identifier.",
        ),
        _definition(
            "horizon_days",
            "Days from information cutoff to target.",
            "request dates (train.csv/test.csv:Date alignment)",
            "numeric",
            "target_date - cutoff_date, inclusive range 1..48.",
            "known_future",
            "Validated ForecastKey.",
        ),
        _definition(
            "target_day_of_week",
            "Target weekday, Monday=1, Sunday=7.",
            "request dates (train.csv/test.csv:Date alignment)",
            "numeric",
            "target_date.isoweekday().",
            "known_future",
            "ForecastKey dates.",
        ),
        _definition(
            "target_month",
            "Target calendar month.",
            "request dates (train.csv/test.csv:Date alignment)",
            "numeric",
            "target_date.month.",
            "known_future",
            "ForecastKey dates.",
        ),
        _definition(
            "target_year",
            "Target calendar year.",
            "request dates (train.csv/test.csv:Date alignment)",
            "numeric",
            "target_date.year.",
            "known_future",
            "ForecastKey dates.",
        ),
        _definition(
            "target_day_of_year",
            "Target ordinal calendar day, preserving leap years.",
            "request dates (train.csv/test.csv:Date alignment)",
            "numeric",
            "target_date.timetuple().tm_yday.",
            "known_future",
            "ForecastKey dates.",
        ),
        _definition(
            "store_type",
            "Known store format.",
            "store.csv:StoreType",
            "categorical",
            "As-of store snapshot field.",
            "static",
            metadata,
        ),
        _definition(
            "assortment",
            "Known assortment category.",
            "store.csv:Assortment",
            "categorical",
            "As-of store snapshot field.",
            "static",
            metadata,
        ),
        _definition(
            "competition_distance",
            "Known competition distance; source units not inferred.",
            "store.csv:CompetitionDistance",
            "numeric",
            "As-of snapshot field, unchanged.",
            "static",
            metadata,
        ),
        _definition(
            "competition_months_at_cutoff",
            "Calendar-month difference from competitor opening to cutoff; not exact elapsed days.",
            "store.csv:CompetitionOpenSinceMonth/Year",
            "numeric",
            (
                "12*(cutoff.year-start.year)+cutoff.month-start.month; future or "
                "incomplete start => None."
            ),
            "historical_at_cutoff",
            metadata,
        ),
        _definition(
            "promo2_active_target",
            "Planned Promo2 participation for target month, not realized promotion success.",
            "store.csv:Promo2,Promo2SinceWeek/Year,PromoInterval",
            "numeric",
            (
                "Known metadata: false membership => 0; otherwise ISO-week start "
                "reached and target month in interval => 1, else 0. Incomplete "
                "schedule => None."
            ),
            "known_future",
            metadata + " Caller asserts this snapshot represents a known plan, not hindsight.",
        ),
        _definition(
            "target_open",
            "Known planned daily opening flag; no opening-hour claim.",
            "train.csv/test.csv:Open",
            "numeric",
            "As-of target plan; no Sunday or sales-based inference.",
            "known_future",
            plans,
        ),
        _definition(
            "target_promo",
            "Known planned Promo flag; non-causal association only.",
            "train.csv/test.csv:Promo",
            "numeric",
            "As-of target plan; unavailable plan => None.",
            "known_future",
            plans,
        ),
        _definition(
            "target_state_holiday",
            "Holiday category only if supplied as known at cutoff.",
            "train.csv/test.csv:StateHoliday",
            "categorical",
            "As-of target plan; 0 is an observed no-holiday category, not a missing default.",
            "known_future",
            plans,
        ),
        _definition(
            "target_school_holiday",
            "School holiday only if supplied as known at cutoff.",
            "train.csv/test.csv:SchoolHoliday",
            "numeric",
            "As-of target plan; no holiday calendar inferred from weekday.",
            "known_future",
            plans,
        ),
        _definition(
            "sales_at_cutoff",
            "Actual sales on cutoff day if already available.",
            "train.csv:Sales",
            "numeric",
            "Exact date t, not latest row.",
            "historical_at_cutoff",
            history,
        ),
        _definition(
            "days_since_last_sales",
            "Age in days of latest available actual at/before cutoff.",
            "train.csv:Date,Sales",
            "numeric",
            "cutoff minus latest available observation date; no history => None.",
            "historical_at_cutoff",
            history,
        ),
    ]
    for lag in LAG_DAYS:
        specs.append(
            _definition(
                f"sales_lag_{lag}_from_cutoff",
                f"Sales exactly {lag} calendar days before cutoff.",
                "train.csv:Date,Sales",
                "numeric",
                f"Read t-{lag}; a missing date stays None, never previous-row shift.",
                "historical_at_cutoff",
                history,
            )
        )
    for window in ROLLING_DAYS:
        specs.extend(
            [
                _definition(
                    f"sales_mean_{window}_through_cutoff",
                    (
                        f"Mean of available observations in last {window} calendar days "
                        "including cutoff."
                    ),
                    "train.csv:Date,Sales",
                    "numeric",
                    (
                        f"[t-{window - 1}, t] inclusive; ignore absent/delayed dates; "
                        "empty => None; closed zero sales included."
                    ),
                    "historical_at_cutoff",
                    history,
                ),
                _definition(
                    f"sales_count_{window}_through_cutoff",
                    f"Coverage count for the {window}-day inclusive window.",
                    "train.csv:Date,Sales",
                    "numeric",
                    f"Count available observations in [t-{window - 1}, t]; empty => 0.",
                    "historical_at_cutoff",
                    history,
                ),
            ]
        )
    specs.extend(
        [
            _definition(
                "target_sales",
                "Supervised target only; never an input.",
                "train.csv:Sales",
                "numeric",
                (
                    "Separate y at store_id,target_date; training label must be "
                    "available by training_label_end."
                ),
                "unknown_future",
                "Label access is separate from build().",
                predictor=False,
            ),
            _definition(
                "customers",
                "Excluded from every V1 predictor, including historical aggregates.",
                "train.csv:Customers",
                "numeric",
                "Retained only in source/SQL; not loaded by feature adapter.",
                "unknown_future",
                "Forbidden feature input.",
                predictor=False,
            ),
            _definition(
                "submission_sales",
                "Kaggle template placeholder, never a target or feature.",
                "sample_submission.csv:Sales",
                "numeric",
                "Not loaded by feature adapter.",
                "unknown_future",
                "Forbidden feature/label input.",
                predictor=False,
            ),
        ]
    )
    return tuple(specs)


FEATURE_REGISTRY = _definitions()
PREDICTORS = tuple(item for item in FEATURE_REGISTRY if item.predictor)
FEATURE_NAMES = tuple(item.name for item in PREDICTORS)


@lru_cache(maxsize=1)
def registry_fingerprint() -> str:
    """Hash the complete registry, including policies and stable predictor ordering."""
    return content_hash([item.model_dump(mode="json") for item in FEATURE_REGISTRY])


def render_registry() -> str:
    """Generate the human reference from the exact contracts used in code."""
    lines = [
        "# Feature registry",
        "",
        (
            "In plain English: each input has a cutoff rule. Unknown plans "
            "remain missing; Customers are excluded entirely."
        ),
        "",
        (
            "Generated by `uv run python -m "
            "retailforecast.features.registry`; edit registry.py, not this "
            "document."
        ),
        "",
        f"Registry fingerprint: `{registry_fingerprint()}`",
        "",
        (
            "Predictor order is the order below, excluding entries with predictor=False. "
            "Numeric preprocessing adds one missing indicator per numeric "
            "input; category codes are ordinal identifiers, not measured "
            "quantities."
        ),
        "",
    ]
    for item in FEATURE_REGISTRY:
        lines.extend(
            [
                f"## {item.name}",
                "",
                "| Contract | Value |",
                "|---|---|",
                *[
                    f"| {key} | {str(value).replace('|', '/')} |"
                    for key, value in item.model_dump().items()
                    if key != "name"
                ],
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    """Write the generated reference, or fail --check when it is stale."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[3] / "docs" / "FEATURE_REGISTRY.md"
    expected = render_registry()
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            raise SystemExit("FEATURE_REGISTRY.md is stale; run the generator")
    else:
        path.write_text(expected, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
