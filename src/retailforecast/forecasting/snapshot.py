"""Read a bounded SQL snapshot with both business-date and availability cutoff gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from retailforecast.data.pipeline_config import content_hash
from retailforecast.features.builder import FeatureBuilder
from retailforecast.features.contracts import (
    PlanSnapshot,
    SalesObservation,
    SnapshotContext,
    StoreSnapshot,
)
from retailforecast.forecasting.contracts import ForecastRequest, HistoryCoverage
from retailforecast.forecasting.errors import ForecastError
from retailforecast.storage.models import DailySale, ForecastInput, Store

HISTORY_COVERAGE_DAYS = 28


@dataclass(frozen=True)
class ForecastInputs:
    """Prepared features and provenance; no future actual Sales or Customers are loaded."""

    builder: FeatureBuilder
    history: tuple[HistoryCoverage, ...]
    input_fingerprint: str


def store_snapshot(row: Store, context: SnapshotContext) -> StoreSnapshot:
    """Project one source metadata row into the exact shared feature input schema."""
    return StoreSnapshot(
        store_id=row.store_id,
        available_as_of=context.assumptions.metadata_known_as_of,
        store_type=row.store_type,
        assortment=row.assortment,
        competition_distance=float(row.competition_distance)
        if row.competition_distance is not None
        else None,
        competition_open_since_month=row.competition_open_since_month,
        competition_open_since_year=row.competition_open_since_year,
        promo2=row.promo2,
        promo2_since_week=row.promo2_since_week,
        promo2_since_year=row.promo2_since_year,
        promo_interval=row.promo_interval,
    )


def known_source_plans(
    session: Session,
    source_id: str,
    request: ForecastRequest,
    context: SnapshotContext,
) -> dict[tuple[int, date], PlanSnapshot]:
    """Load calendar covariates only under the model's explicit archived knowledge policy.

    A historical DailySale row can supply assumed-known calendar fields, but its
    Sales and Customers are never selected for future target dates.
    """
    known_as_of = context.assumptions.calendar_known_as_of
    plans: dict[tuple[int, date], PlanSnapshot] = {}
    if known_as_of is None or known_as_of > request.cutoff_date:
        return plans
    target_end = request.cutoff_date + timedelta(days=request.horizon_days)
    for table in (DailySale, ForecastInput):
        rows = session.execute(
            select(
                table.store_id,
                table.date,
                table.is_open,
                table.promotion,
                table.state_holiday,
                table.school_holiday,
            ).where(
                table.source_version == source_id,
                table.store_id.in_(request.store_ids),
                table.date > request.cutoff_date,
                table.date <= target_end,
            )
        )
        for row in rows:
            plans[(row.store_id, row.date)] = PlanSnapshot(
                store_id=row.store_id,
                target_date=row.date,
                available_as_of=known_as_of,
                is_open=row.is_open,
                promotion=row.promotion,
                state_holiday=row.state_holiday,
                school_holiday=row.school_holiday,
            )
    return plans


def load_sql_inputs(
    session: Session,
    source_id: str,
    request: ForecastRequest,
    context: SnapshotContext,
) -> ForecastInputs:
    """Freeze only available observations for selected stores; never read post-cutoff sales."""
    store_rows = list(
        session.scalars(
            select(Store)
            .where(
                Store.source_version == source_id,
                Store.store_id.in_(request.store_ids),
            )
            .order_by(Store.store_id)
        )
    )
    missing = sorted(set(request.store_ids) - {row.store_id for row in store_rows})
    if missing:
        raise ForecastError("unknown_store", f"Store IDs do not exist in this dataset: {missing}")
    stores = [store_snapshot(row, context) for row in store_rows]
    delay = timedelta(days=context.assumptions.sales_delay_days)
    latest_visible_day = request.cutoff_date - delay
    rows = session.execute(
        select(DailySale.store_id, DailySale.date, DailySale.sales)
        .where(
            DailySale.source_version == source_id,
            DailySale.store_id.in_(request.store_ids),
            DailySale.date <= request.cutoff_date,
            DailySale.date <= latest_visible_day,
        )
        .order_by(DailySale.store_id, DailySale.date)
    ).yield_per(10_000)
    observations = [
        SalesObservation(
            store_id=row.store_id,
            date=row.date,
            sales=float(row.sales),
            available_as_of=row.date + delay,
        )
        for row in rows
    ]
    histories: list[HistoryCoverage] = []
    first_recent_day = request.cutoff_date - timedelta(days=HISTORY_COVERAGE_DAYS - 1)
    for store_id in request.store_ids:
        dates = [row.date for row in observations if row.store_id == store_id]
        if not dates:
            raise ForecastError(
                "missing_history", f"No observed sales are available by cutoff for store {store_id}"
            )
        histories.append(
            HistoryCoverage(
                store_id=store_id,
                observed_from=min(dates),
                observed_through=max(dates),
                observations=len(dates),
                missing_days_in_last_28=HISTORY_COVERAGE_DAYS
                - sum(day >= first_recent_day for day in dates),
            )
        )
    plans = known_source_plans(session, source_id, request, context)
    for scenario in request.scenarios:
        # A scenario is a full replacement: omitted fields stay unknown rather
        # than being silently filled from a possibly unavailable target row.
        plans[(scenario.store_id, scenario.target_date)] = PlanSnapshot(
            store_id=scenario.store_id,
            target_date=scenario.target_date,
            available_as_of=scenario.available_as_of,
            is_open=scenario.is_open,
            promotion=scenario.promotion,
            state_holiday=scenario.state_holiday,
            school_holiday=scenario.school_holiday,
        )
    fingerprint = content_hash(
        {
            "request": request.model_dump(mode="json"),
            "dataset": context.dataset_fingerprint,
            "observations": [row.model_dump(mode="json") for row in observations],
            "stores": [row.model_dump(mode="json") for row in stores],
            "plans": [
                row.model_dump(mode="json")
                for row in sorted(plans.values(), key=lambda row: (row.target_date, row.store_id))
            ],
        }
    )
    return ForecastInputs(
        FeatureBuilder(observations, stores, plans.values(), context=context),
        tuple(histories),
        fingerprint,
    )
