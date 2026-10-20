"""Restart-idempotent wall-calendar scheduling owned exclusively by the local worker."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from retailforecast.lifecycle.job_contracts import CreateTrainingJob, ScheduleRequest, ScheduleView
from retailforecast.lifecycle.jobs import JobService, queue_lock
from retailforecast.storage.database import utc_now
from retailforecast.storage.models import RetrainingSchedule

SCHEDULE_SCOPE = "global-v1"


def occurrence(anchor: datetime, index: int, cadence: str, timezone: str) -> datetime:
    """Keep anchor wall time/day; clamp month ends and normalize DST gaps forward."""
    local = anchor.astimezone(ZoneInfo(timezone))
    if cadence == "weekly":
        candidate = local + timedelta(days=7 * index)
    else:
        month = local.year * 12 + local.month - 1 + index * (3 if cadence == "quarterly" else 1)
        year, offset = divmod(month, 12)
        candidate = local.replace(
            year=year,
            month=offset + 1,
            day=min(local.day, calendar.monthrange(year, offset + 1)[1]),
        )
    return candidate.astimezone(UTC)


def next_occurrence(anchor: datetime, after: datetime, cadence: str, timezone: str) -> datetime:
    """Compute a strictly future due date without drifting January 31 to every month's 28th."""
    local = after.astimezone(ZoneInfo(timezone))
    first = anchor.astimezone(ZoneInfo(timezone))
    if cadence == "weekly":
        index = max(0, (local.date() - first.date()).days // 7)
    else:
        months = (local.year - first.year) * 12 + local.month - first.month
        index = max(0, months // (3 if cadence == "quarterly" else 1))
    while occurrence(anchor, index, cadence, timezone) <= after:
        index += 1
    return occurrence(anchor, index, cadence, timezone)


def schedule_view(row: RetrainingSchedule | None) -> ScheduleView:
    """Return safe manual defaults even before the operator saves a schedule."""
    if row is None:
        return ScheduleView()
    return ScheduleView(
        id=row.id,
        cadence=row.cadence,
        timezone=row.timezone,
        enabled=row.enabled,
        algorithm=row.algorithm,
        anchor_at=row.anchor_at,
        revision=row.revision,
        next_run=row.next_run,
        last_check_at=row.last_check_at,
    )


class ScheduleService:
    """Advance durable due times and enqueue through the same transaction as skip audit."""

    def __init__(self, jobs: JobService) -> None:
        """Share the queue's short advisory lock and backend algorithm/resource settings."""
        self.jobs = jobs

    def get(self) -> ScheduleView:
        """Inspect configured intent; this never starts timers or a worker."""
        with self.jobs.sessions() as session:
            return schedule_view(
                session.scalar(
                    select(RetrainingSchedule).where(RetrainingSchedule.scope == SCHEDULE_SCOPE)
                )
            )

    def put(self, request: ScheduleRequest, *, now: datetime | None = None) -> ScheduleView:
        """Save semantic changes only; repeated identical PUT preserves revision and due time."""
        current = now or utc_now()
        with self.jobs.sessions.begin() as session:
            queue_lock(session)
            row = session.scalar(
                select(RetrainingSchedule)
                .where(RetrainingSchedule.scope == SCHEDULE_SCOPE)
                .with_for_update()
            )
            if row is None:
                row = RetrainingSchedule(scope=SCHEDULE_SCOPE)
                session.add(row)
            else:
                existing = schedule_view(row)
                supplied = request.model_copy(
                    update={"anchor_at": request.anchor_at or existing.anchor_at}
                )
                if all(
                    getattr(existing, key) == getattr(supplied, key)
                    for key in ScheduleRequest.model_fields
                ):
                    return existing
            row.cadence, row.timezone, row.enabled, row.algorithm = (
                request.cadence,
                request.timezone,
                request.enabled,
                request.algorithm,
            )
            row.anchor_at = request.anchor_at or row.anchor_at or current
            row.revision = (row.revision or 0) + 1
            row.next_run = (
                next_occurrence(row.anchor_at, current, request.cadence, request.timezone)
                if request.enabled
                else None
            )
            session.flush()
            return schedule_view(row)

    def tick(self, *, now: datetime | None = None) -> int:
        """Record missed slots as skipped and coalesce to one latest due check on restart."""
        current = now or utc_now()
        events = 0
        with self.jobs.sessions.begin() as session:
            queue_lock(session)
            row = session.scalar(
                select(RetrainingSchedule)
                .where(RetrainingSchedule.scope == SCHEDULE_SCOPE)
                .with_for_update()
            )
            if row is None or not row.enabled or row.cadence == "manual" or row.anchor_at is None:
                return 0
            row.last_check_at = current
            while (
                row.next_run
                and row.next_run <= current
                and events < self.jobs.settings.max_schedule_events_per_tick
            ):
                due = row.next_run
                following = next_occurrence(row.anchor_at, due, row.cadence, row.timezone)
                reason = (
                    "skipped: missed scheduled occurrence while worker unavailable"
                    if following <= current
                    else None
                )
                self.jobs.enqueue_in_transaction(
                    session,
                    CreateTrainingJob(algorithm=row.algorithm),
                    trigger_key=f"schedule:{row.id}:{row.revision}:{due.astimezone(UTC).isoformat()}",
                    scheduled_for=due,
                    skip_reason=reason,
                )
                row.next_run = following
                events += 1
        return events
