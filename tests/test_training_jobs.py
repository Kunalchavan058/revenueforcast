"""Durable queue/scheduler, additional actuals and genuine standalone CPU job integration."""

from __future__ import annotations

import csv
import shutil
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest
from conftest import migrate_schema
from fastapi.testclient import TestClient
from forecasts import forecast_service
from main import create_app
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.orm import Session
from test_model_lifecycle import activate
from test_model_lifecycle import completed_training as completed_training
from test_model_lifecycle import registry as registry
from training_jobs import job_service

from retailforecast.data import import_actuals as actuals
from retailforecast.data.ingestion import insert_file
from retailforecast.data.lineage import is_descendant
from retailforecast.features.snapshot import load_feature_builder
from retailforecast.forecasting.contracts import ForecastRequest
from retailforecast.forecasting.errors import ForecastError
from retailforecast.forecasting.service import ForecastService
from retailforecast.lifecycle.job_contracts import CreateTrainingJob, JobSettings, ScheduleRequest
from retailforecast.lifecycle.job_execution import LostOwnership, execute_job, set_stage
from retailforecast.lifecycle.job_worker import (
    recover_running,
    run_claim,
    worker_ownership,
    write_runtime,
)
from retailforecast.lifecycle.jobs import JobService
from retailforecast.lifecycle.registry import ModelRegistry, TrainingRecord
from retailforecast.lifecycle.scheduling import ScheduleService, next_occurrence
from retailforecast.storage.database import ROOT
from retailforecast.storage.models import (
    DailySale,
    DatasetLineage,
    DatasetVersion,
    ForecastInput,
    ImportJob,
    ModelEvent,
    ModelVersion,
    Store,
    TrainingAttempt,
    TrainingJob,
)
from retailforecast.training.contracts import TrainingRequest
from retailforecast.training.workflow import refit_history_without_holdout


@pytest.fixture
def jobs(registry: ModelRegistry, completed_training: Path, tmp_path: Path) -> JobService:
    """Use real migrated SQL plus genuine synthetic source/native fixtures, initially inactive."""
    root = tmp_path / "project"
    (root / "configs").mkdir(parents=True)
    shutil.copyfile(completed_training.parents[2] / "configs/data.yaml", root / "configs/data.yaml")
    shutil.copyfile(ROOT / "uv.lock", root / "uv.lock")
    record = TrainingRecord.model_validate_json((completed_training / "training.json").read_bytes())
    with registry.sessions.begin() as session:
        source_id = session.scalar(select(DatasetVersion.id))
        assert source_id
        for name in ("store.csv", "train.csv", "test.csv"):
            insert_file(
                session, completed_training.parents[2] / "data/raw/synthetic" / name, source_id
            )
    return JobService(
        registry,
        root=root,
        training=record.training_config,
        backtest=record.protocol.config,
        settings=JobSettings(
            training_mode="dev",
            retry_seconds=0,
            heartbeat_seconds=0.1,
            lease_seconds=2,
            poll_seconds=0.1,
        ),
    )


@pytest.fixture
def active_jobs(jobs: JobService, completed_training: Path) -> JobService:
    """Retain an approved model while appended data or a failed candidate is processed."""
    activate(jobs.registry, jobs.registry.register(completed_training), 0)
    return jobs


@pytest.fixture
def client(jobs: JobService) -> Iterator[TestClient]:
    """HTTP only gets the queue facade, never an executor or training function."""
    app = create_app()
    app.dependency_overrides[job_service] = lambda: jobs
    app.dependency_overrides[forecast_service] = lambda: ForecastService(jobs.registry)
    with TestClient(app) as http:
        yield http


def source_id(jobs: JobService) -> str:
    """Return the original fixture's source identity."""
    with jobs.sessions() as session:
        value = session.scalar(select(DatasetVersion.id).order_by(DatasetVersion.ingested_at))
        assert value
        return value


def additional_csv(path: Path, *, days: int = 3) -> Path:
    """Create explicitly synthetic August observations, including an observed Sunday closure."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "Store",
                "Date",
                "DayOfWeek",
                "Sales",
                "Customers",
                "Open",
                "Promo",
                "StateHoliday",
                "SchoolHoliday",
            ],
        )
        writer.writeheader()
        for offset in range(days):
            day = date(2015, 8, 1) + timedelta(days=offset)
            for store in (9001, 9002):
                opened = day.isoweekday() != 7
                writer.writerow(
                    {
                        "Store": store,
                        "Date": day.isoformat(),
                        "DayOfWeek": day.isoweekday(),
                        "Sales": 250 + offset if opened else 0,
                        "Customers": 5 if opened else 0,
                        "Open": int(opened),
                        "Promo": 0,
                        "StateHoliday": "0",
                        "SchoolHoliday": 0,
                    }
                )
    return path


def append_actuals(jobs: JobService, tmp_path: Path) -> str:
    """Publish future labeled synthetic observations through the real import contract."""
    result = actuals.import_actuals(
        jobs.registry.sessions.kw["bind"],
        source_id(jobs),
        additional_csv(tmp_path / "actuals.csv"),
        "Explicitly synthetic operator observations",
        synthetic=True,
        raw_root=jobs.root / "data/raw/additional",
    )
    return str(result["dataset_version_id"])


def test_http_enqueues_without_fitting_and_supports_idempotency(
    client: TestClient, jobs: JobService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """202 means durable queued work, never an inline fit or a ready forecast promise."""

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("HTTP must not train")

    monkeypatch.setattr("retailforecast.training.train.run_training", forbidden)
    monkeypatch.setattr("retailforecast.lifecycle.job_execution.run_training", forbidden)
    headers = {"Idempotency-Key": "first-training"}
    response = client.post("/api/v1/training-jobs", json={"algorithm": "xgboost"}, headers=headers)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["state"] == "queued" and body["attempt_count"] == 0 and body["worker_required"]
    assert (
        client.post("/api/v1/training-jobs", json={"algorithm": "xgboost"}, headers=headers).json()[
            "id"
        ]
        == body["id"]
    )
    assert (
        client.post(
            "/api/v1/training-jobs", json={"algorithm": "lightgbm"}, headers=headers
        ).status_code
        == 409
    )
    assert client.post("/api/v1/training-jobs", json={"algorithm": "bad"}).status_code == 422
    assert (
        client.post(
            "/api/v1/training-jobs", json={"algorithm": "auto", "max_depth": 20}
        ).status_code
        == 422
    )
    assert client.get(f"/api/v1/training-jobs/{body['id']}").json()["state"] == "queued"
    assert client.post(f"/api/v1/training-jobs/{body['id']}/cancel").json()["state"] == "cancelled"
    assert client.post(f"/api/v1/training-jobs/{body['id']}/cancel").status_code == 409
    assert jobs.registry.slot().active_model_version_id is None


def test_duplicate_triggers_and_claims_are_serialized(jobs: JobService) -> None:
    """Concurrent callers share one pending job and SQL admits exactly one running claim."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: jobs.enqueue(CreateTrainingJob(algorithm="auto")), range(2))
        )
    assert results[0].id == results[1].id
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: jobs.claim(), range(2)))
    assert sum(claim is not None for claim in claims) == 1
    assert jobs.get(results[0].id).state == "running"
    with pytest.raises(ForecastError, match="Only queued"):
        jobs.cancel(results[0].id)


def test_existing_withheld_labels_do_not_count_as_new(active_jobs: JobService) -> None:
    """The existing July 30/31 final labels are already in the trained dataset watermark."""
    row = active_jobs.enqueue(CreateTrainingJob(algorithm="lightgbm"))
    assert active_jobs.claim() is None
    result = active_jobs.get(row.id)
    assert result.state == "skipped" and result.message == "skipped: no new labeled observations"
    assert result.attempt_count == 0


def test_append_only_import_is_idempotent_and_fresh_forecasts_do_not_retrain(
    active_jobs: JobService, tmp_path: Path
) -> None:
    """Add visible history while retaining old weights and source snapshots."""
    service = ForecastService(active_jobs.registry)
    before = service.create(
        ForecastRequest(store_ids=(9001,), cutoff_date=date(2015, 7, 29), horizon_days=1)
    )
    child = append_actuals(active_jobs, tmp_path)
    repeat = actuals.import_actuals(
        active_jobs.registry.sessions.kw["bind"],
        source_id(active_jobs),
        tmp_path / "actuals.csv",
        "Explicitly synthetic operator observations",
        synthetic=True,
        raw_root=active_jobs.root / "data/raw/additional",
    )
    assert repeat["state"] == "duplicate" and repeat["dataset_version_id"] == child
    unchanged = service.create(before.request)
    assert (
        before.points == unchanged.points
        and before.input_fingerprint == unchanged.input_fingerprint
    )
    fresh = service.create(
        ForecastRequest(store_ids=(9001,), cutoff_date=date(2015, 8, 3), horizon_days=7)
    )
    assert fresh.model == before.model and fresh.data.actual_data_cutoff == date(2015, 8, 3)
    assert fresh.data.dataset_version_id == child and fresh.data.history[0].observations == 93
    with active_jobs.sessions() as session:
        assert is_descendant(session, child, source_id(active_jobs))
        assert session.scalar(select(func.count()).select_from(TrainingJob)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(DailySale)
                .where(DailySale.source_version == source_id(active_jobs))
            )
            == 180
        )
        assert (
            session.scalar(
                select(func.count()).select_from(DailySale).where(DailySale.source_version == child)
            )
            == 186
        )


@pytest.mark.parametrize(
    "failure",
    [
        "missing_sales",
        "invalid_date",
        "negative",
        "duplicate",
        "old_date",
        "unknown_store",
        "future_date",
    ],
)
def test_bad_additional_actuals_are_rejected(
    jobs: JobService, tmp_path: Path, failure: str
) -> None:
    """Observed labels require a strict schema and valid append-only date/store identities."""
    path = additional_csv(tmp_path / "bad.csv", days=1)
    text = path.read_text(encoding="utf-8")
    if failure == "missing_sales":
        text = text.replace("Sales,", "Unknown,")
    elif failure == "invalid_date":
        text = text.replace("2015-08-01", "not-a-date")
    elif failure == "negative":
        text = text.replace(",250,", ",-1,")
    elif failure == "duplicate":
        text += text.splitlines()[1] + "\n"
    elif failure == "old_date":
        text = text.replace("2015-08-01,6", "2015-07-31,5")
    elif failure == "unknown_store":
        text = text.replace("9001,", "999999,")
    else:
        text = text.replace("2015-08-01,6", "2099-08-01,6")
    path.write_text(text, encoding="utf-8", newline="\n")
    with pytest.raises(ValueError):
        actuals.import_actuals(
            jobs.registry.sessions.kw["bind"],
            source_id(jobs),
            path,
            "Synthetic invalid input",
            dry_run=True,
            synthetic=True,
        )
    with jobs.sessions() as session:
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 1


def test_additional_import_rollback(
    jobs: JobService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A copy failure rolls back the child and keeps a separate failed-import audit."""
    original = actuals.clone_rows

    def fail(
        session: Session,
        model: type[Store] | type[DailySale] | type[ForecastInput],
        parent_id: str,
        child_id: str,
    ) -> None:
        if model is DailySale:
            raise RuntimeError("Controlled copy failure")
        original(session, model, parent_id, child_id)

    monkeypatch.setattr(actuals, "clone_rows", fail)
    with pytest.raises(RuntimeError, match="Controlled"):
        append_actuals(jobs, tmp_path)
    with jobs.sessions() as session:
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 1
        assert session.scalar(select(func.count()).select_from(DatasetLineage)) == 0
        assert session.scalar(select(ImportJob.state)) == "failed"


def test_manual_defaults_and_schedule_restart_idempotency(
    client: TestClient, jobs: JobService
) -> None:
    """Record missed slots, coalesce one check and make repeated ticks/PUT idempotent."""
    assert client.get("/api/v1/retraining-schedule").json()["cadence"] == "manual"
    assert (
        client.put(
            "/api/v1/retraining-schedule", json={"cadence": "manual", "enabled": True}
        ).status_code
        == 422
    )
    assert (
        client.put("/api/v1/retraining-schedule", json={"timezone": "Mars/Olympus"}).status_code
        == 422
    )
    schedules = ScheduleService(jobs)
    start = datetime(2026, 1, 1, 9, tzinfo=UTC)
    request = ScheduleRequest(
        cadence="weekly", timezone="Europe/Berlin", enabled=True, anchor_at=start
    )
    first = schedules.put(request, now=start)
    assert schedules.put(request, now=start + timedelta(days=1)) == first
    later = start + timedelta(days=28, hours=1)
    assert schedules.tick(now=later) == 4
    assert ScheduleService(jobs).tick(now=later) == 0
    with jobs.sessions() as session:
        rows = list(session.scalars(select(TrainingJob).order_by(TrainingJob.scheduled_for)))
        assert [row.state for row in rows] == ["skipped", "skipped", "skipped", "queued"]
        assert len({row.trigger_key for row in rows}) == 4


def test_monthly_quarterly_and_dst_calendar_boundaries() -> None:
    """Calendar recurrence keeps the original month-end anchor and normalizes DST gaps."""
    anchor = datetime(2026, 1, 31, 10, tzinfo=UTC)
    feb = next_occurrence(anchor, anchor, "monthly", "UTC")
    assert feb == datetime(2026, 2, 28, 10, tzinfo=UTC)
    assert next_occurrence(anchor, feb, "monthly", "UTC") == datetime(2026, 3, 31, 10, tzinfo=UTC)
    assert next_occurrence(anchor, anchor, "quarterly", "UTC") == datetime(
        2026, 4, 30, 10, tzinfo=UTC
    )
    spring = datetime(2026, 3, 22, 1, 30, tzinfo=UTC)
    assert next_occurrence(spring, spring, "weekly", "Europe/Berlin") == datetime(
        2026, 3, 29, 1, 30, tzinfo=UTC
    )


def test_restart_fences_old_attempt_and_retries_with_audited_limit(jobs: JobService) -> None:
    """An unacknowledged child cannot publish after its worker restarts and changes the token."""
    row = jobs.enqueue(CreateTrainingJob(algorithm="xgboost"))
    claim = jobs.claim()
    assert claim
    with worker_ownership(jobs):
        with pytest.raises(RuntimeError, match="Another local worker"):
            with worker_ownership(jobs):
                pass
        recover_running(jobs)
    recovered = jobs.get(row.id)
    assert recovered.state == "queued" and recovered.attempts[0].state == "failed"
    second = jobs.claim()
    assert second and second[1] != claim[1]
    with pytest.raises(LostOwnership):
        set_stage(jobs, *claim, "complete", "late old result")
    jobs.finish_failed(*claim, "Late obsolete failure", retryable=False)
    assert jobs.get(row.id).state == "running"
    jobs.finish_failed(*second, "Second attempt failed", retryable=True)
    assert jobs.get(row.id).state == "failed" and jobs.get(row.id).attempt_count == 2


def test_crash_after_registration_reuses_weights_and_one_model(
    jobs: JobService, completed_training: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retrying completed publication never fits again or registers another version for the job."""
    row = jobs.enqueue(CreateTrainingJob(algorithm="xgboost"))
    claim = jobs.claim()
    assert claim
    with jobs.sessions() as session:
        attempt = session.scalar(select(TrainingAttempt).where(TrainingAttempt.job_id == row.id))
        assert attempt
        output = jobs.root / attempt.output_relative
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(completed_training, output)
    original = jobs.registry.register

    def registered_then_crashed(path: Path, *, training_job_id: str | None = None) -> str:
        original(path, training_job_id=training_job_id)
        raise RuntimeError("Crash after registration")

    monkeypatch.setattr(jobs.registry, "register", registered_then_crashed)
    with pytest.raises(RuntimeError, match="Crash after"):
        execute_job(jobs, *claim)
    jobs.finish_failed(*claim, "Coordinator interrupted after publication", retryable=True)
    monkeypatch.setattr(jobs.registry, "register", original)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Completed fitting must not be repeated")

    monkeypatch.setattr("retailforecast.lifecycle.job_execution.run_training", forbidden)
    next_claim = jobs.claim()
    assert next_claim
    execute_job(jobs, *next_claim)
    assert jobs.get(row.id).state == "succeeded"
    with jobs.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ModelVersion)) == 1
        assert (
            session.scalar(
                select(func.count()).select_from(ModelEvent).where(ModelEvent.action == "activated")
            )
            == 1
        )


def test_standalone_process_genuinely_trains_bootstraps_and_skips_unchanged(
    jobs: JobService,
) -> None:
    """The real worker/child/native stack creates a measured saved model without an HTTP fit."""
    row = jobs.enqueue(CreateTrainingJob(algorithm="xgboost"))
    with worker_ownership(jobs):
        runtime = write_runtime(jobs)
        claim = jobs.claim()
        assert claim
        run_claim(jobs, claim, runtime)
    result = jobs.get(row.id)
    assert result.state == "succeeded", result.model_dump_json()
    assert (
        result.attempt_count == 1
        and result.model_version_id == jobs.registry.slot().active_model_version_id
    )
    assert result.model_version_id
    model, record = jobs.registry.load(result.model_version_id)
    assert model.trained_until == date(
        2015, 7, 29
    ) and record.business_dataset_version_id == source_id(jobs)
    repeat = jobs.enqueue(CreateTrainingJob(algorithm="auto"))
    assert jobs.claim() is None
    assert jobs.get(repeat.id).state == "skipped"


def test_append_retraining_masks_holdout_and_compares_shared_windows(
    active_jobs: JobService, tmp_path: Path
) -> None:
    """Refit on new labels while excluding protected final observations entirely."""
    original = active_jobs.registry.slot()
    child = append_actuals(active_jobs, tmp_path)
    row = active_jobs.enqueue(CreateTrainingJob(algorithm="xgboost"))
    assert row.dataset_version_id == child
    with worker_ownership(active_jobs):
        runtime = write_runtime(active_jobs)
        claim = active_jobs.claim()
        assert claim
        run_claim(active_jobs, claim, runtime)
    result = active_jobs.get(row.id)
    assert result.state == "succeeded", result.model_dump_json()
    assert result.model_version_id
    model, record = active_jobs.registry.load(result.model_version_id)
    assert model.trained_until == date(2015, 8, 3)
    assert record.protected_holdout and record.protected_holdout.target_end == date(2015, 7, 31)
    assert record.refit_excluded_observations == 4
    view = next(
        version
        for version in active_jobs.registry.list_versions()
        if version.id == result.model_version_id
    )
    comparison = view.evidence["comparison"]
    assert (
        isinstance(comparison, dict)
        and comparison["eligible"]
        and comparison["basis"] == "retained_rolling_origin_models"
    )
    assert all(
        fold.target_end <= date(2015, 7, 29)
        for fold in record.protocol.plan.folds
        if fold.role == "development"
    )
    with active_jobs.sessions() as session:
        job = session.get(TrainingJob, row.id)
        assert job
        output = active_jobs.root / str(job.request_context["training_output"])
    request = TrainingRequest.model_validate_json((output / "request.json").read_bytes())
    builder = load_feature_builder(
        Path(request.data_config),
        request.profile,
        store_ids=request.backtest.store_ids,
        assumptions=request.backtest.assumptions,
    )
    history, excluded = refit_history_without_holdout(builder, request, date(2015, 8, 3))
    assert excluded == 4
    assert any(observation.date == date(2015, 8, 3) for observation in history.observations)
    assert all(
        not date(2015, 7, 29) < observation.date <= date(2015, 7, 31)
        for observation in history.observations
    )
    assert active_jobs.registry.slot().active_model_version_id in (
        original.active_model_version_id,
        result.model_version_id,
    )


def test_failed_training_keeps_incumbent_forecasts(
    active_jobs: JobService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Record a training failure while the incumbent serves fresh observed history."""
    append_actuals(active_jobs, tmp_path)
    slot = active_jobs.registry.slot()
    row = active_jobs.enqueue(CreateTrainingJob(algorithm="lightgbm"))
    claim = active_jobs.claim()
    assert claim

    entered, release = Event(), Event()

    def fail(*args: object, **kwargs: object) -> None:
        entered.set()
        if not release.wait(timeout=20):
            raise RuntimeError("Test did not release the controlled training failure")
        raise RuntimeError("Controlled fitting failure")

    monkeypatch.setattr("retailforecast.lifecycle.job_execution.run_training", fail)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execute_job, active_jobs, *claim)
        try:
            assert entered.wait(timeout=20)
            assert active_jobs.get(row.id).state == "running"
            during = ForecastService(active_jobs.registry).create(
                ForecastRequest(store_ids=(9001,), cutoff_date=date(2015, 8, 3), horizon_days=1)
            )
            assert during.model.version_id == slot.active_model_version_id
            assert not future.done()
        finally:
            release.set()
        with pytest.raises(RuntimeError, match="Controlled"):
            future.result(timeout=30)
    active_jobs.finish_failed(*claim, "Native training failed", retryable=False)
    assert active_jobs.get(row.id).state == "failed" and active_jobs.registry.slot() == slot
    forecast = ForecastService(active_jobs.registry).create(
        ForecastRequest(store_ids=(9001,), cutoff_date=date(2015, 8, 3), horizon_days=1)
    )
    assert forecast.model.version_id == slot.active_model_version_id


def test_worker_migration_roundtrip(postgres_database: tuple[Engine, str]) -> None:
    """A reversible frozen migration preserves existing forecast/lifecycle tables."""
    engine, schema = postgres_database
    migrate_schema(engine, schema, "a10f0c03b002", downgrade=True)
    assert "training_attempts" not in inspect(engine).get_table_names(schema=schema)
    migrate_schema(engine, schema, "head")
    assert {"training_attempts", "dataset_lineage"} <= set(
        inspect(engine).get_table_names(schema=schema)
    )


def test_stale_heartbeat_is_reported_without_api_reclaim(jobs: JobService) -> None:
    """Reading status exposes expiry but never competes with the standalone worker."""
    row = jobs.enqueue(CreateTrainingJob(algorithm="auto"))
    claim = jobs.claim()
    assert claim
    with jobs.sessions.begin() as session:
        record = session.get(TrainingJob, row.id)
        assert record
        record.heartbeat_at = datetime(2000, 1, 1, tzinfo=UTC)
    view = jobs.get(row.id)
    assert view.worker_heartbeat_stale and view.lease_expires_at is not None
    assert view.state == "running" and jobs.claim() is None


def test_divergent_append_branch_is_rejected(active_jobs: JobService, tmp_path: Path) -> None:
    """An operator must extend the latest child rather than silently forking visible actuals."""
    append_actuals(active_jobs, tmp_path)
    path = additional_csv(tmp_path / "different.csv", days=4)
    with pytest.raises(ValueError, match="Parent already extended"):
        actuals.import_actuals(
            active_jobs.sessions.kw["bind"],
            source_id(active_jobs),
            path,
            "Explicitly synthetic other observations",
            synthetic=True,
            raw_root=active_jobs.root / "data/raw/additional",
        )
