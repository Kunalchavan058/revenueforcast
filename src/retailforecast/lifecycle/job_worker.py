"""Standalone local scheduler/worker; database leases are independent of API/browser lifetime."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

import psutil
from filelock import FileLock, Timeout
from sqlalchemy import Engine, select, text

from retailforecast.data.pipeline_config import canonical_json
from retailforecast.evaluation.contracts import BacktestConfig
from retailforecast.lifecycle.job_contracts import JobSettings
from retailforecast.lifecycle.jobs import JobService
from retailforecast.lifecycle.registry import ModelRegistry
from retailforecast.lifecycle.scheduling import ScheduleService
from retailforecast.storage.database import ROOT, database_engine, utc_now
from retailforecast.storage.models import TrainingAttempt, TrainingJob
from retailforecast.training.contracts import TrainingConfig
from retailforecast.training.resources import terminate_job

WORKER_LOCK_KEY = 721105002


def load_runtime(path: Path) -> JobService:
    """Load an owned runtime descriptor containing paths/settings, never database passwords."""
    values = json.loads(path.read_bytes())
    engine = database_engine()
    schema = values.get("schema")
    if schema:
        if (
            os.environ.get("RETAILFORECAST_TEST_MLFLOW_SQLITE") != "1"
            or re.fullmatch(r"rf_test_[0-9a-f]{32}", schema) is None
        ):
            raise ValueError("Isolated schemas require explicit synthetic test opt-in")
        engine = engine.execution_options(schema_translate_map={None: schema})
    registry = ModelRegistry(engine, Path(values["registry"]), Path(values["tracking"]))
    return JobService(
        registry,
        root=Path(values["root"]),
        settings=JobSettings.model_validate(values["settings"]),
        training=TrainingConfig.model_validate(values["training"]),
        backtest=BacktestConfig.model_validate(values["backtest"]),
    )


@contextmanager
def worker_ownership(service: JobService) -> Iterator[None]:
    """Hold both a host lock and a PostgreSQL session lock; only one worker may schedule/claim."""
    path = service.root / "artifacts/jobs/.worker.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(path, timeout=0)
    try:
        lock.acquire()
    except Timeout as error:
        raise RuntimeError("Another local worker owns this laptop queue") from error
    engine = cast(Engine, service.sessions.kw["bind"])
    try:
        with engine.connect() as connection:
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK_KEY}
            )
            connection.commit()
            if not acquired:
                raise RuntimeError("Another standalone worker owns this database queue")
            try:
                yield
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK_KEY}
                )
                connection.commit()
    finally:
        lock.release()


def recover_running(service: JobService) -> None:
    """Kill only verified owned orphan processes before fencing/requeuing interrupted attempts."""
    with service.sessions() as session:
        rows = list(session.scalars(select(TrainingJob).where(TrainingJob.state == "running")))
        pending = []
        for row in rows:
            attempt = session.scalar(
                select(TrainingAttempt).where(
                    TrainingAttempt.job_id == row.id, TrainingAttempt.number == row.attempt_count
                )
            )
            if attempt:
                pending.append(
                    (row.id, attempt.owner_token, attempt.process_id, attempt.process_created_at)
                )
    for job_id, token, pid, created in pending:
        if pid:
            try:
                process = psutil.Process(pid)
                if created is not None and abs(process.create_time() - created) < 0.01:
                    command = process.cmdline()
                    if (
                        "retailforecast.lifecycle.job_execution" not in command
                        or token not in command
                        or job_id not in command
                    ):
                        raise RuntimeError(
                            "Cannot verify orphan ownership; stop worker for operator inspection"
                        )
                    descendants = process.children(recursive=True)
                    for child in reversed(descendants):
                        try:
                            child.kill()
                        except psutil.NoSuchProcess:
                            pass
                    process.kill()
                    process.wait(timeout=15)
            except psutil.NoSuchProcess:
                pass
        service.finish_failed(
            job_id, token, "Worker restarted; interrupted owned attempt recovered", retryable=True
        )


def write_runtime(service: JobService) -> Path:
    """Freeze worker paths/budgets for child startup; credentials stay in the environment/.env."""
    engine = cast(Engine, service.sessions.kw["bind"])
    mapping = engine.get_execution_options().get("schema_translate_map")
    schema = mapping.get(None) if mapping else None
    path = service.root / "artifacts/jobs/runtime.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        canonical_json(
            {
                "root": str(service.root),
                "registry": str(service.registry.artifact_root),
                "tracking": str(service.registry.tracking_root),
                "settings": service.settings.model_dump(mode="json"),
                "training": service.training.model_dump(mode="json"),
                "backtest": service.backtest.model_dump(mode="json"),
                "schema": schema,
            }
        )
    )
    return path


def run_claim(service: JobService, claim: tuple[str, str], runtime: Path) -> None:
    """Supervise one coordinator, heartbeat its fenced lease and isolate every process failure."""
    job_id, token = claim
    log_path = service.root / f"artifacts/jobs/{job_id}/{token}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process: subprocess.Popen[bytes] | None = None
    try:
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "retailforecast.lifecycle.job_execution",
                    "--runtime",
                    str(runtime),
                    "--job-id",
                    job_id,
                    "--owner-token",
                    token,
                ],
                cwd=service.root,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            created = psutil.Process(process.pid).create_time()
            with service.sessions.begin() as session:
                job = session.get(TrainingJob, job_id)
                attempt = session.scalar(
                    select(TrainingAttempt).where(
                        TrainingAttempt.job_id == job_id, TrainingAttempt.owner_token == token
                    )
                )
                assert job is not None and attempt is not None
                job.logs_uri = str(log_path)
                attempt.process_id, attempt.process_created_at = process.pid, created
            while process.poll() is None:
                with service.sessions.begin() as session:
                    job = session.get(TrainingJob, job_id)
                    attempt = session.scalar(
                        select(TrainingAttempt).where(
                            TrainingAttempt.job_id == job_id, TrainingAttempt.owner_token == token
                        )
                    )
                    if job is None or attempt is None or attempt.state != "running":
                        if job is None or job.state != "succeeded":
                            terminate_job(process)
                        break
                    job.heartbeat_at, attempt.heartbeat_at = utc_now(), utc_now()
                time.sleep(service.settings.heartbeat_seconds)
            if process.poll() is None:
                process.wait(timeout=15)
            service.finish_failed(
                job_id,
                token,
                "Coordinator exited before completing the request",
                retryable=True,
                exit_code=process.returncode,
            )
    except BaseException:
        if process is not None and process.poll() is None:
            terminate_job(process)
        service.finish_failed(
            job_id, token, "Worker interrupted while supervising its owned process", retryable=True
        )
        raise


def tick(service: JobService, runtime: Path) -> bool:
    """Advance schedules and execute at most one eligible queued attempt."""
    ScheduleService(service).tick()
    claim = service.claim()
    if claim is None:
        return False
    run_claim(service, claim, runtime)
    return True


def main() -> None:
    """Start separately from API/web; --once processes at most one attempt then exits."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    service = JobService(
        ModelRegistry(database_engine(), ROOT / "artifacts/registry", ROOT / "artifacts/mlflow")
    )
    try:
        with worker_ownership(service):
            recover_running(service)
            runtime = write_runtime(service)
            print(
                "Standalone worker started; schedules require this process and an awake laptop",
                flush=True,
            )
            while True:
                tick(service, runtime)
                if args.once:
                    break
                time.sleep(service.settings.poll_seconds)
    except KeyboardInterrupt:
        print(
            "Worker stopped; interrupted work is audited and retried within its budget", flush=True
        )
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(2, f"Worker stopped: {error}\n")


if __name__ == "__main__":
    main()
