"""Transactional training queue with explicit dataset watermarks and fenced attempts."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import yaml
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from retailforecast.data.lineage import is_descendant, latest_descendant
from retailforecast.data.pipeline_config import content_hash
from retailforecast.evaluation.contracts import BacktestConfig
from retailforecast.forecasting.errors import ForecastError
from retailforecast.lifecycle.job_contracts import (
    AttemptView,
    CreateTrainingJob,
    JobSettings,
    JobView,
)
from retailforecast.lifecycle.registry import ModelRegistry
from retailforecast.storage.database import ROOT, new_id, utc_now
from retailforecast.storage.models import (
    DatasetVersion,
    ModelSlot,
    ModelVersion,
    TrainingAttempt,
    TrainingJob,
)
from retailforecast.training.contracts import TrainingConfig

QUEUE_LOCK_KEY = 721105001
TERMINAL_STATES = {"succeeded", "failed", "skipped", "cancelled"}


def queue_lock(session: Session) -> None:
    """Serialize short queue/schedule transactions, never native training or forecast reads."""
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": QUEUE_LOCK_KEY})


def job_view(session: Session, row: TrainingJob, *, lease_seconds: int = 60) -> JobView:
    """Project bounded structured status; raw native logs remain local to the operator."""
    attempts = session.scalars(
        select(TrainingAttempt)
        .where(TrainingAttempt.job_id == row.id)
        .order_by(TrainingAttempt.number)
    )
    return JobView(
        id=row.id,
        algorithm=row.requested_algorithm,
        state=row.state,
        stage=row.stage,
        message=row.message,
        dataset_version_id=row.dataset_version_id,
        initiated_at=row.initiated_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        heartbeat_at=row.heartbeat_at,
        retry_after=row.retry_after,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        model_version_id=row.result_model_version_id,
        lease_expires_at=row.heartbeat_at + timedelta(seconds=lease_seconds)
        if row.state == "running" and row.heartbeat_at
        else None,
        worker_heartbeat_stale=row.state == "running"
        and (
            row.heartbeat_at is None
            or utc_now() - row.heartbeat_at > timedelta(seconds=lease_seconds)
        ),
        attempts=tuple(
            AttemptView(
                number=a.number,
                state=a.state,
                started_at=a.started_at,
                completed_at=a.completed_at,
                heartbeat_at=a.heartbeat_at,
                exit_code=a.exit_code,
                summary=a.summary,
            )
            for a in attempts
        ),
    )


class JobService:
    """HTTP only enqueues; a standalone process claims, executes and records attempts."""

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        root: Path = ROOT,
        settings: JobSettings | None = None,
        training: TrainingConfig | None = None,
        backtest: BacktestConfig | None = None,
    ) -> None:
        """Load backend-only settings; test callers may supply explicitly isolated budgets."""
        self.registry, self.sessions, self.root = registry, registry.sessions, root.resolve()
        self.settings = settings or JobSettings.model_validate(
            yaml.safe_load((root / "configs/jobs.yaml").read_text(encoding="utf-8"))
        )
        self.training = training or TrainingConfig.model_validate(
            yaml.safe_load((root / "configs/training.yaml").read_text(encoding="utf-8"))
        )
        self.backtest = backtest or BacktestConfig.model_validate(
            yaml.safe_load((root / "configs/backtest.yaml").read_text(encoding="utf-8"))
        )

    def enqueue(self, request: CreateTrainingJob, *, trigger_key: str | None = None) -> JobView:
        """Return an existing duplicate or persist a queued request without fitting anything."""
        with self.sessions.begin() as session:
            queue_lock(session)
            row = self.enqueue_in_transaction(
                session, request, trigger_key=trigger_key or "manual:" + new_id()
            )
            session.flush()
            return job_view(session, row, lease_seconds=self.settings.lease_seconds)

    def enqueue_in_transaction(
        self,
        session: Session,
        request: CreateTrainingJob,
        *,
        trigger_key: str,
        scheduled_for: datetime | None = None,
        skip_reason: str | None = None,
    ) -> TrainingJob:
        """Share idempotent publication with the scheduler under its caller-owned queue lock."""
        previous = session.scalar(select(TrainingJob).where(TrainingJob.trigger_key == trigger_key))
        public_hash = content_hash(request.model_dump(mode="json"))
        if previous:
            if previous.request_fingerprint != public_hash:
                raise ForecastError(
                    "idempotency_conflict",
                    "This idempotency key was used for another algorithm",
                    409,
                )
            return previous
        slot = session.get(ModelSlot, "global-v1")
        baseline = (
            session.get(ModelVersion, slot.active_model_version_id)
            if slot and slot.active_model_version_id
            else None
        )
        source = (
            latest_descendant(session, baseline.dataset_version_id)
            if baseline
            else session.scalar(
                select(DatasetVersion)
                .order_by(
                    DatasetVersion.available_through.desc(), DatasetVersion.ingested_at.desc()
                )
                .limit(1)
            )
        )
        if source is None and scheduled_for is None:
            raise ForecastError(
                "dataset_required", "Import validated labeled sales before requesting training", 503
            )
        frozen = {
            "training": self.training.model_dump(mode="json"),
            "backtest": self.backtest.model_dump(mode="json"),
            "mode": self.settings.training_mode,
            "dataset_checksum": source.checksum if source else None,
            "baseline_model_version_id": baseline.id if baseline else None,
        }
        if skip_reason is None:
            duplicate = session.scalar(
                select(TrainingJob)
                .where(
                    TrainingJob.requested_algorithm == request.algorithm,
                    TrainingJob.dataset_version_id == (source.id if source else None),
                    TrainingJob.state.in_(("queued", "running")),
                )
                .order_by(TrainingJob.initiated_at)
                .limit(1)
            )
            if duplicate:
                if scheduled_for is None:
                    return duplicate
                skip_reason = "skipped: equivalent training request is already queued or running"
        if source is None:
            skip_reason = "skipped: no validated labeled dataset is available"
        row = TrainingJob(
            dataset_version_id=source.id if source else None,
            requested_algorithm=request.algorithm,
            trigger_key=trigger_key,
            request_fingerprint=public_hash,
            request_context=frozen,
            state="skipped" if skip_reason else "queued",
            stage="complete" if skip_reason else "queued",
            message=skip_reason or "Queued for the standalone worker; HTTP does not train",
            max_attempts=self.settings.max_attempts,
            scheduled_for=scheduled_for,
            completed_at=utc_now() if skip_reason else None,
        )
        session.add(row)
        return row

    def get(self, job_id: str) -> JobView:
        """Inspect a durable attempt log even when the worker or laptop has stopped."""
        with self.sessions() as session:
            row = session.get(TrainingJob, job_id)
            if row is None:
                raise ForecastError("training_job_not_found", "Unknown training job", 404)
            return job_view(session, row, lease_seconds=self.settings.lease_seconds)

    def cancel(self, job_id: str) -> JobView:
        """Cancel queued work without interrupting native fitting or model publication."""
        with self.sessions.begin() as session:
            queue_lock(session)
            row = session.get(TrainingJob, job_id)
            if row is None:
                raise ForecastError("training_job_not_found", "Unknown training job", 404)
            if row.state != "queued":
                raise ForecastError(
                    "cancellation_unsafe", "Only queued jobs can be cancelled safely", 409
                )
            row.state, row.stage, row.message, row.completed_at = (
                "cancelled",
                "complete",
                "Cancelled before execution",
                utc_now(),
            )
            session.flush()
            return job_view(session, row, lease_seconds=self.settings.lease_seconds)

    def eligibility(self, session: Session, row: TrainingJob) -> str | None:
        """Require new selected-store observations beyond the last consumed source watermark.

        A June-13 model's existing July holdout is not a newly imported dataset.
        Both successful attempts and the active model's entire source are watermarks.
        """
        source = (
            session.get(DatasetVersion, row.dataset_version_id) if row.dataset_version_id else None
        )
        if source is None:
            return "skipped: no validated labeled observations"
        from sqlalchemy import func

        from retailforecast.storage.models import DailySale

        store_ids = BacktestConfig.model_validate(row.request_context["backtest"]).store_ids
        latest = session.scalar(
            select(func.max(DailySale.date)).where(
                DailySale.source_version == source.id, DailySale.store_id.in_(store_ids)
            )
        )
        if latest is None:
            return "skipped: no labeled observations for the configured store cohort"
        prior_sources: set[str] = set()
        baseline_id = row.request_context.get("baseline_model_version_id")
        if isinstance(baseline_id, str):
            baseline = session.get(ModelVersion, baseline_id)
            if baseline:
                prior_sources.add(baseline.dataset_version_id)
                if latest <= baseline.trained_until:
                    return "skipped: no new labeled observations"
        succeeded = session.scalars(
            select(TrainingJob).where(TrainingJob.state == "succeeded", TrainingJob.id != row.id)
        )
        prior_sources.update(job.dataset_version_id for job in succeeded if job.dataset_version_id)
        for prior_id in prior_sources:
            if is_descendant(session, source.id, prior_id):
                watermark = session.scalar(
                    select(func.max(DailySale.date)).where(
                        DailySale.source_version == prior_id, DailySale.store_id.in_(store_ids)
                    )
                )
                if watermark is not None and latest <= watermark:
                    return "skipped: no new labeled observations"
        return None

    def claim(self, *, now: datetime | None = None) -> tuple[str, str] | None:
        """Claim one runnable request after eligibility; SQL enforces at most one running job."""
        current = now or utc_now()
        with self.sessions.begin() as session:
            queue_lock(session)
            if session.scalar(
                select(TrainingJob.id).where(TrainingJob.state == "running").limit(1)
            ):
                return None
            rows = session.scalars(
                select(TrainingJob)
                .where(TrainingJob.state == "queued")
                .order_by(TrainingJob.initiated_at, TrainingJob.id)
            )
            for row in rows:
                if row.retry_after and row.retry_after > current:
                    continue
                if not row.request_context or row.attempt_count >= row.max_attempts:
                    row.state, row.stage, row.message, row.completed_at = (
                        "failed",
                        "complete",
                        "Invalid or exhausted legacy request; enqueue a new request",
                        current,
                    )
                    continue
                reason = self.eligibility(session, row)
                if reason:
                    row.state, row.stage, row.message, row.completed_at = (
                        "skipped",
                        "complete",
                        reason,
                        current,
                    )
                    continue
                row.state, row.stage, row.message = (
                    "running",
                    "validating",
                    "Worker claimed the request",
                )
                row.attempt_count += 1
                row.started_at, row.heartbeat_at, row.retry_after = current, current, None
                token = new_id()
                session.add(
                    TrainingAttempt(
                        job_id=row.id,
                        number=row.attempt_count,
                        owner_token=token,
                        started_at=current,
                        heartbeat_at=current,
                        output_relative=f"artifacts/training/job-{row.id}-attempt-{row.attempt_count}",
                    )
                )
                return row.id, token
        return None

    def finish_failed(
        self, job_id: str, token: str, reason: str, *, retryable: bool, exit_code: int | None = None
    ) -> None:
        """Fence late results and retain each failed attempt before a bounded retry."""
        with self.sessions.begin() as session:
            queue_lock(session)
            row = session.get(TrainingJob, job_id)
            attempt = session.scalar(
                select(TrainingAttempt).where(
                    TrainingAttempt.job_id == job_id, TrainingAttempt.owner_token == token
                )
            )
            if (
                row is None
                or attempt is None
                or row.state != "running"
                or attempt.state != "running"
            ):
                return
            current = utc_now()
            attempt.state, attempt.completed_at, attempt.summary, attempt.exit_code = (
                "failed",
                current,
                reason,
                exit_code,
            )
            retry = retryable and row.attempt_count < row.max_attempts
            row.state = "queued" if retry else "failed"
            row.stage = "retry_wait" if retry else "complete"
            row.message = reason + (
                "; bounded retry queued" if retry else "; no active model was replaced"
            )
            row.completed_at = None if retry else current
            row.retry_after = (
                current + timedelta(seconds=self.settings.retry_seconds) if retry else None
            )
            row.exit_code = exit_code
