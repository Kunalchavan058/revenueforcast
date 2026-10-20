"""Public job/schedule contracts and bounded standalone worker settings."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, Field, StrictBool, field_validator, model_validator

from retailforecast.forecasting.contracts import ApiContract
from retailforecast.training.contracts import Mode, RequestedAlgorithm

JobState = Literal["queued", "running", "succeeded", "failed", "skipped", "cancelled"]
Cadence = Literal["manual", "weekly", "monthly", "quarterly"]


class JobSettings(ApiContract):
    """Backend-only budgets; normal requests select an algorithm, never native tuning knobs."""

    schema_version: Literal[1] = 1
    training_mode: Mode = "full"
    max_attempts: int = Field(default=2, ge=1, le=3)
    retry_seconds: int = Field(default=30, ge=0, le=3600)
    poll_seconds: float = Field(default=2, ge=0.05, le=30)
    heartbeat_seconds: float = Field(default=5, ge=0.05, le=30)
    lease_seconds: int = Field(default=60, ge=1, le=600)
    max_schedule_events_per_tick: int = Field(default=100, ge=1, le=100)

    @model_validator(mode="after")
    def check_lease(self) -> JobSettings:
        """Make heartbeat expiry meaningfully longer than the heartbeat interval."""
        if self.lease_seconds <= 2 * self.heartbeat_seconds:
            raise ValueError("Lease must exceed two heartbeat intervals")
        return self


class CreateTrainingJob(ApiContract):
    """The normal user selects only an algorithm; the service pins data and budgets."""

    algorithm: RequestedAlgorithm


class AttemptView(ApiContract):
    """Safe summary of a fenced process attempt; no credentials or unrestricted log content."""

    number: int
    state: str
    started_at: datetime
    completed_at: datetime | None
    heartbeat_at: datetime
    exit_code: int | None
    summary: str


class JobView(ApiContract):
    """Measured stage/state, not invented percentage progress."""

    id: str
    algorithm: str
    state: JobState
    stage: str
    message: str
    dataset_version_id: str | None
    initiated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    heartbeat_at: datetime | None
    retry_after: datetime | None
    attempt_count: int
    max_attempts: int
    model_version_id: str | None
    attempts: tuple[AttemptView, ...]
    lease_expires_at: datetime | None
    worker_heartbeat_stale: bool
    worker_required: Literal[True] = True


class ScheduleRequest(ApiContract):
    """Anchor a wall-calendar recurrence in a named IANA timezone; manual is disabled."""

    cadence: Cadence = "manual"
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    enabled: StrictBool = False
    algorithm: RequestedAlgorithm = "auto"
    anchor_at: AwareDatetime | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        """Reject unknown zones instead of silently scheduling in the laptop's local zone."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Use a valid IANA timezone, such as UTC or Europe/Berlin") from error
        return value

    @model_validator(mode="after")
    def check_manual(self) -> ScheduleRequest:
        """Manual scheduling never implies an enabled background timer."""
        if self.cadence == "manual" and self.enabled:
            raise ValueError("Manual cadence must have enabled=false")
        return self


class ScheduleView(ScheduleRequest):
    """Persisted revision and next due time; enabling a schedule does not start a process."""

    id: str | None = None
    revision: int = 0
    next_run: datetime | None = None
    last_check_at: datetime | None = None
    notice: str = "Requires the standalone worker; laptop shutdown or sleep prevents execution."
