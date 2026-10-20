"""Nonblocking training queue and optional recurring-schedule HTTP contracts."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from models import model_registry

from retailforecast.forecasting.contracts import ErrorResponse
from retailforecast.lifecycle.job_contracts import (
    CreateTrainingJob,
    JobView,
    ScheduleRequest,
    ScheduleView,
)
from retailforecast.lifecycle.jobs import JobService
from retailforecast.lifecycle.scheduling import ScheduleService

router = APIRouter(
    prefix="/api/v1",
    tags=["training"],
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


@lru_cache(maxsize=1)
def job_service() -> JobService:
    """Construct a lazy queue facade; it neither launches a child nor runs a timer."""
    return JobService(model_registry())


JobsDependency = Annotated[JobService, Depends(job_service)]


@router.post("/training-jobs", status_code=202, response_model=JobView)
def enqueue_training(
    request: CreateTrainingJob,
    jobs: JobsDependency,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None,
) -> JobView:
    """Persist a request immediately; only the separately started worker may train."""
    return jobs.enqueue(
        request, trigger_key="manual:" + idempotency_key if idempotency_key else None
    )


@router.get("/training-jobs/{job_id}", response_model=JobView)
def get_training(job_id: UUID, jobs: JobsDependency) -> JobView:
    """Read durable state, actual stage, heartbeat and bounded attempt summaries."""
    return jobs.get(str(job_id))


@router.post("/training-jobs/{job_id}/cancel", response_model=JobView)
def cancel_training(job_id: UUID, jobs: JobsDependency) -> JobView:
    """Cancel only queued work, avoiding unsafe mid-fit or mid-promotion termination."""
    return jobs.cancel(str(job_id))


@router.get("/retraining-schedule", response_model=ScheduleView)
def get_schedule(jobs: JobsDependency) -> ScheduleView:
    """Default manual/disabled; configuration never claims the laptop worker is running."""
    return ScheduleService(jobs).get()


@router.put("/retraining-schedule", response_model=ScheduleView)
def put_schedule(request: ScheduleRequest, jobs: JobsDependency) -> ScheduleView:
    """Save timezone/calendar recurrence idempotently without executing any training."""
    return ScheduleService(jobs).put(request)
