"""SQL aggregation of observed actuals with bounded inclusive filters and exact sums."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from retailforecast.forecasting.errors import ForecastError
from retailforecast.forecasting.totals import period_bounds
from retailforecast.lifecycle.registry import ModelRegistry
from retailforecast.reporting.contracts import (
    DEFAULT_SELECTED_STORES,
    ActualPeriod,
    HistoryQuery,
    HistorySummary,
    SourceCoverage,
    StoreActual,
    WeekdayActual,
)
from retailforecast.storage.models import DailySale, DatasetVersion, Store

SALES_QUANTUM = Decimal("0.0001")


def source_coverage(session: Session, source: DatasetVersion) -> SourceCoverage:
    """Inspect actual labels only, never test.csv plans or submission placeholders."""
    first, last, stores = session.execute(
        select(
            func.min(DailySale.date),
            func.max(DailySale.date),
            func.count(func.distinct(DailySale.store_id)),
        ).where(DailySale.source_version == source.id)
    ).one()
    if first is None or last is None:
        raise ForecastError("missing_history", "This source has no observed sales")
    defaults = tuple(
        session.scalars(
            select(DailySale.store_id)
            .where(DailySale.source_version == source.id)
            .distinct()
            .order_by(DailySale.store_id)
            .limit(DEFAULT_SELECTED_STORES)
        )
    )
    return SourceCoverage(
        dataset_version_id=source.id,
        checksum=source.checksum,
        observed_from=first,
        observed_through=last,
        store_count=stores,
        default_store_ids=defaults,
    )


def select_source(session: Session, source_id: str | None) -> DatasetVersion | None:
    """Resolve an explicit immutable snapshot or latest import for business exploration."""
    if source_id:
        source = session.get(DatasetVersion, source_id)
        if source is None:
            raise ForecastError("dataset_not_found", "The selected dataset no longer exists", 404)
        return source
    return session.scalar(
        select(DatasetVersion)
        .order_by(DatasetVersion.ingested_at.desc(), DatasetVersion.id.desc())
        .limit(1)
    )


class HistoryService:
    """Read-only business aggregates; never fit, score or infer unavailable observations."""

    def __init__(self, registry: ModelRegistry) -> None:
        """Share the existing explicit session boundary without importing any model weights."""
        self.sessions = registry.sessions

    def coverage(self, source_id: str | None = None) -> SourceCoverage | None:
        """Return real observed calendar boundaries; no import means no default date."""
        with self.sessions() as session:
            source = select_source(session, source_id)
            return source_coverage(session, source) if source else None

    def summary(self, query: HistoryQuery) -> HistorySummary:
        """Recompute sums/counts from SQL for the exact source, dates and selected stores."""
        with self.sessions() as session:
            source = select_source(session, query.dataset_version_id)
            assert source is not None
            coverage = source_coverage(session, source)
            if (
                query.start_date < coverage.observed_from
                or query.end_date > coverage.observed_through
            ):
                raise ForecastError(
                    "invalid_history_range", "Choose dates within the observed dataset coverage"
                )
            existing = set(
                session.scalars(
                    select(Store.store_id).where(
                        Store.source_version == source.id, Store.store_id.in_(query.store_ids)
                    )
                )
            )
            if existing != set(query.store_ids):
                raise ForecastError(
                    "unknown_store", "One or more selected stores do not exist in this source"
                )
            filters = (
                DailySale.source_version == source.id,
                DailySale.store_id.in_(query.store_ids),
                DailySale.date >= query.start_date,
                DailySale.date <= query.end_date,
            )
            closed = func.sum(case((DailySale.is_open.is_(False), 1), else_=0))
            positive_closed = func.sum(
                case(((DailySale.is_open.is_(False)) & (DailySale.sales > 0), 1), else_=0)
            )
            # SQL reduces up to 32 stores x 1,096 days to at most 1,096 daily rows.
            # No Customers column or unlabeled plan is read for these business summaries.
            daily = session.execute(
                select(
                    DailySale.date, func.sum(DailySale.sales), func.count(), closed, positive_closed
                )
                .where(*filters)
                .group_by(DailySale.date)
                .order_by(DailySale.date)
            ).all()
            by_store = {
                row[0]: row
                for row in session.execute(
                    select(DailySale.store_id, func.sum(DailySale.sales), func.count(), closed)
                    .where(*filters)
                    .group_by(DailySale.store_id)
                )
            }
            weekdays = {
                int(row[0]): row
                for row in session.execute(
                    select(
                        func.extract("isodow", DailySale.date),
                        func.sum(DailySale.sales),
                        func.count(),
                    )
                    .where(*filters)
                    .group_by(func.extract("isodow", DailySale.date))
                )
            }
            expected = ((query.end_date - query.start_date).days + 1) * len(query.store_ids)
            observed = sum(row[2] for row in daily)
            series = self._periods(query, {row[0]: (row[1], row[2]) for row in daily})
            return HistorySummary(
                query=query,
                checksum=source.checksum,
                observed_from=daily[0][0] if daily else None,
                observed_through=daily[-1][0] if daily else None,
                selected_store_count=len(query.store_ids),
                observed_store_days=observed,
                expected_store_days=expected,
                missing_store_days=expected - observed,
                total_sales=sum((row[1] for row in daily), Decimal(0)) if daily else None,
                open_store_days=sum(row[2] - row[3] for row in daily),
                closed_store_days=sum(row[3] for row in daily),
                closed_positive_sales_days=sum(row[4] for row in daily),
                series=series,
                by_store=tuple(
                    StoreActual(
                        store_id=store,
                        sales=by_store[store][1] if store in by_store else None,
                        observed_store_days=by_store[store][2] if store in by_store else 0,
                        open_store_days=by_store[store][2] - by_store[store][3]
                        if store in by_store
                        else 0,
                        closed_store_days=by_store[store][3] if store in by_store else 0,
                    )
                    for store in query.store_ids
                ),
                weekdays=tuple(
                    WeekdayActual(
                        weekday=day,
                        observations=weekdays[day][2] if day in weekdays else 0,
                        sales=weekdays[day][1] if day in weekdays else None,
                        mean_sales=(weekdays[day][1] / weekdays[day][2]).quantize(SALES_QUANTUM)
                        if day in weekdays
                        else None,
                    )
                    for day in range(1, 8)
                ),
            )

    @staticmethod
    def _periods(
        query: HistoryQuery, daily: dict[date, tuple[Decimal, int]]
    ) -> tuple[ActualPeriod, ...]:
        """Calendar buckets include holes as null, never invented zero-sales observations."""
        groups: dict[tuple[date, date], list[date]] = defaultdict(list)
        for offset in range((query.end_date - query.start_date).days + 1):
            day = query.start_date + timedelta(days=offset)
            groups[period_bounds(day, query.frequency)].append(day)
        return tuple(
            ActualPeriod(
                period_start=start,
                period_end=end,
                covered_from=days[0],
                covered_through=days[-1],
                expected_store_days=len(days) * len(query.store_ids),
                observed_store_days=sum(daily[day][1] for day in days if day in daily),
                sales=sum((daily[day][0] for day in days if day in daily), Decimal(0))
                if any(day in daily for day in days)
                else None,
            )
            for (start, end), days in sorted(groups.items())
        )


def history_csv(summary: HistorySummary) -> str:
    """Export the same filtered calendar totals and coverage shown in the dashboard."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "dataset_version_id",
            "source_checksum",
            "store_ids",
            "frequency",
            "requested_from",
            "requested_through",
            "period_start",
            "period_end",
            "covered_from",
            "covered_through",
            "observed_store_days",
            "expected_store_days",
            "observed_sales",
            "sales_unit",
        )
    )
    for row in summary.series:
        writer.writerow(
            (
                summary.query.dataset_version_id,
                summary.checksum,
                "|".join(map(str, summary.query.store_ids)),
                summary.query.frequency,
                summary.query.start_date,
                summary.query.end_date,
                row.period_start,
                row.period_end,
                row.covered_from,
                row.covered_through,
                row.observed_store_days,
                row.expected_store_days,
                format(row.sales, ".4f") if row.sales is not None else "",
                summary.sales_unit,
            )
        )
    return stream.getvalue()
