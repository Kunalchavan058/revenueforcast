"""Execute one fenced background request; HTTP never imports or invokes this entrypoint."""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from pathlib import Path

import psutil
from sqlalchemy import select

from retailforecast.evaluation.contracts import BacktestConfig
from retailforecast.lifecycle.job_snapshot import materialize_snapshot
from retailforecast.lifecycle.jobs import JobService
from retailforecast.lifecycle.registry import TrainingRecord
from retailforecast.storage.database import utc_now
from retailforecast.storage.models import DatasetVersion, ModelVersion, TrainingAttempt, TrainingJob
from retailforecast.training.contracts import TrainingRequest
from retailforecast.training.train import run_training


class LostOwnership(RuntimeError):
    """A stale process must not publish a result for another attempt."""


def set_stage(service: JobService, job_id: str, token: str, stage: str, message: str) -> None:
    """Fence every stage publication against the claimed attempt's opaque owner token."""
    with service.sessions.begin() as session:
        job = session.get(TrainingJob, job_id)
        attempt = session.scalar(
            select(TrainingAttempt).where(
                TrainingAttempt.job_id == job_id, TrainingAttempt.owner_token == token
            )
        )
        if job is None or attempt is None or job.state != "running" or attempt.state != "running":
            raise LostOwnership("Training attempt no longer owns this request")
        job.stage, job.message = stage, message
        attempt.summary = message


def execute_job(service: JobService, job_id: str, token: str) -> None:
    """Fit a pinned snapshot in the worker and publish through checked promotion."""
    set_stage(
        service,
        job_id,
        token,
        "preparing_data",
        "Preparing validated labeled data and provenance",
    )
    with service.sessions() as session:
        job = session.get(TrainingJob, job_id)
        attempt = session.scalar(
            select(TrainingAttempt).where(
                TrainingAttempt.job_id == job_id, TrainingAttempt.owner_token == token
            )
        )
        assert job is not None and attempt is not None and job.dataset_version_id
        context = dict(job.request_context)
        source = session.get(DatasetVersion, job.dataset_version_id)
        assert source is not None
        if source.checksum != context.get("dataset_checksum"):
            raise ValueError("Pinned dataset metadata changed")
        output = service.root / attempt.output_relative
        algorithm = job.requested_algorithm
        data_id = source.id
        # A completed earlier attempt is reused after a crash during registration
        # or promotion; retrying must not fit the same request meaninglessly.
        prior = session.scalars(
            select(TrainingAttempt)
            .where(TrainingAttempt.job_id == job_id)
            .order_by(TrainingAttempt.number)
        )
        completed = None
        for previous in prior:
            candidate = service.root / previous.output_relative
            status = candidate / "status.json"
            if status.exists() and json.loads(status.read_bytes()).get("state") == "succeeded":
                completed = candidate
                break
        if completed is None:
            config_path, profile, checksum = materialize_snapshot(
                session,
                source,
                service.root / f"artifacts/jobs/{job_id}/snapshot-{attempt.number}",
                service.root,
            )
            baseline_id = context.get("baseline_model_version_id")
            baseline_record = None
            if isinstance(baseline_id, str):
                _, baseline_record = service.registry.load(baseline_id)
            backtest = (
                baseline_record.protocol.config
                if baseline_record
                else BacktestConfig.model_validate(context["backtest"])
            )
            request = TrainingRequest.model_validate(
                {
                    "algorithm": algorithm,
                    "mode": context["mode"],
                    "training": context["training"],
                    "backtest": backtest.model_dump(mode="json"),
                    "data_config": str(config_path),
                    "profile": profile,
                    "business_dataset_version_id": source.id,
                    "business_source_checksum": source.checksum,
                    "validation_plan": baseline_record.protocol.plan.model_dump(mode="json")
                    if baseline_record
                    else None,
                    "protected_holdout": baseline_record.protocol.plan.folds[-1].model_dump(
                        mode="json"
                    )
                    if baseline_record
                    else None,
                    "refit_until": source.available_through.isoformat()
                    if baseline_record
                    else None,
                }
            )
        else:
            output = completed
            old = TrainingRecord.model_validate_json((output / "training.json").read_bytes())
            checksum = old.ingestion_dataset_checksum
            request = None
            config_path = Path(json.loads((output / "request.json").read_bytes())["data_config"])
            profile = json.loads((output / "request.json").read_bytes())["profile"]
    with service.sessions.begin() as session:
        row = session.get(TrainingJob, job_id)
        assert row is not None and row.state == "running"
        row.request_context = {
            **row.request_context,
            "materialized_ingestion_checksum": checksum,
            "training_output": str(output.relative_to(service.root)),
        }
    if request is not None:
        set_stage(
            service,
            job_id,
            token,
            "training",
            "Fitting CPU trials on chronological validation; retain active forecasts",
        )
        run_training(request, output, root=service.root)
    set_stage(service, job_id, token, "registering", "Registering the verified completed candidate")
    version_id = service.registry.register(output, training_job_id=job_id)
    set_stage(
        service,
        job_id,
        token,
        "evaluating",
        "Checking shared-window promotion; retain active model on failure",
    )
    with service.sessions() as session:
        version = session.get(ModelVersion, version_id)
        assert version is not None and version.dataset_version_id == data_id
        is_candidate = version.status == "candidate"
    if is_candidate:
        slot = service.registry.slot()
        service.registry.activate(
            version_id,
            expected_generation=slot.generation,
            data_config=config_path,
            profile=profile,
        )
    with service.sessions.begin() as session:
        row = session.get(TrainingJob, job_id)
        attempt = session.scalar(
            select(TrainingAttempt).where(
                TrainingAttempt.job_id == job_id, TrainingAttempt.owner_token == token
            )
        )
        if row is None or attempt is None or row.state != "running" or attempt.state != "running":
            raise LostOwnership("A late completion cannot overwrite a restarted attempt")
        version = session.get(ModelVersion, version_id)
        assert version is not None
        message = (
            "Training succeeded; candidate is active"
            if version.status == "active"
            else f"Training succeeded; candidate {version.status}; incumbent retained"
        )
        row.state, row.stage, row.message = "succeeded", "complete", message
        row.completed_at, row.result_model_version_id, row.exit_code = utc_now(), version_id, 0
        attempt.state, attempt.completed_at, attempt.summary, attempt.exit_code = (
            "succeeded",
            utc_now(),
            message,
            0,
        )


def main() -> None:
    """Only a worker-launched owned process may execute a token-authorized request."""
    from retailforecast.lifecycle.job_worker import load_runtime

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--owner-token", required=True)
    args = parser.parse_args()
    service = load_runtime(args.runtime)
    try:
        # Cover the spawn/PID-publication crash gap: an unacknowledged child
        # cannot begin fitting, and a restarted owner changes this opaque token.
        for _ in range(100):
            with service.sessions() as session:
                attempt = session.scalar(
                    select(TrainingAttempt).where(
                        TrainingAttempt.job_id == args.job_id,
                        TrainingAttempt.owner_token == args.owner_token,
                    )
                )
                job = session.get(TrainingJob, args.job_id)
                if (
                    attempt is None
                    or job is None
                    or attempt.state != "running"
                    or job.state != "running"
                ):
                    raise LostOwnership("Request was requeued before process authorization")
                # Windows virtualenv redirectors can launch Python as a child
                # of Popen.pid. Verify PID plus creation time in the live ancestry,
                # not just the interpreter PID, before authorizing any fitting.
                lineage = [psutil.Process(os.getpid()), *psutil.Process(os.getpid()).parents()]
                if any(
                    member.pid == attempt.process_id
                    and attempt.process_created_at is not None
                    and abs(member.create_time() - attempt.process_created_at) < 0.01
                    for member in lineage
                ):
                    break
            time.sleep(0.1)
        else:
            raise LostOwnership("Worker did not authorize this child process")
        with service.sessions.begin() as session:
            attempt = session.scalar(
                select(TrainingAttempt).where(
                    TrainingAttempt.job_id == args.job_id,
                    TrainingAttempt.owner_token == args.owner_token,
                )
            )
            job = session.get(TrainingJob, args.job_id)
            if (
                attempt is None
                or job is None
                or attempt.state != "running"
                or job.state != "running"
            ):
                raise LostOwnership("Attempt was fenced before interpreter authorization")
            # Persist the real interpreter rather than a Windows launcher PID, so
            # restart recovery can identify it even if the launcher disappears.
            attempt.process_id = os.getpid()
            attempt.process_created_at = psutil.Process(os.getpid()).create_time()
        execute_job(service, args.job_id, args.owner_token)
    except Exception as error:
        traceback.print_exc()
        # Keep public summaries free of credentials, SQL and arbitrary native logs.
        service.finish_failed(
            args.job_id,
            args.owner_token,
            f"Attempt failed: {type(error).__name__}",
            retryable=isinstance(error, (RuntimeError, OSError))
            and not isinstance(error, LostOwnership),
            exit_code=1,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
