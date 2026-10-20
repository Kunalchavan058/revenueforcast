"""Real saved-model/SQL prediction contracts, temporal isolation and atomic persistence."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import migrate_schema
from fastapi.testclient import TestClient
from forecasts import forecast_service
from main import create_app
from models import model_registry
from sqlalchemy import Engine, delete, event, func, inspect, select, update
from sqlalchemy.orm import Session
from test_model_lifecycle import activate, remove_legacy_validation
from test_model_lifecycle import completed_training as completed_training
from test_model_lifecycle import registry as registry

from retailforecast.data.ingestion import insert_file
from retailforecast.features.builder import FeatureRow
from retailforecast.features.contracts import ForecastKey
from retailforecast.features.snapshot import load_feature_builder
from retailforecast.forecasting.contracts import ForecastRequest, ForecastResponse
from retailforecast.forecasting.errors import ForecastError
from retailforecast.forecasting.service import ForecastService
from retailforecast.forecasting.snapshot import load_sql_inputs
from retailforecast.lifecycle.registry import ModelRegistry
from retailforecast.storage.models import (
    DailySale,
    DatasetVersion,
    ForecastPoint,
    ForecastRun,
    ModelEvent,
    Store,
    TrainingJob,
)
from retailforecast.training.adapters import NativeTreeAdapter, TreeModel

CUTOFF = date(2015, 7, 29)


def request_body(horizon: int = 7) -> dict[str, object]:
    """Use only fixture-supported stores and a cutoff no earlier than fitted weights."""
    return {"store_ids": [9002, 9001], "cutoff_date": CUTOFF.isoformat(), "horizon_days": horizon}


@pytest.fixture
def service(registry: ModelRegistry, completed_training: Path) -> ForecastService:
    """Publish actual synthetic CSV rows and activate an actually fitted tiny model."""
    with registry.sessions.begin() as session:
        source_id = session.scalar(select(DatasetVersion.id))
        assert source_id is not None
        root = completed_training.parents[2] / "data/raw/synthetic"
        for name in ("store.csv", "train.csv", "test.csv"):
            insert_file(session, root / name, source_id)
    version = registry.register(completed_training)
    activate(registry, version, 0)
    return ForecastService(registry)


@pytest.fixture
def client(service: ForecastService) -> Iterator[TestClient]:
    """Exercise HTTP contracts against isolated migrated PostgreSQL and saved native files."""
    app = create_app()
    app.dependency_overrides[forecast_service] = lambda: service
    app.dependency_overrides[model_registry] = lambda: service.registry
    with TestClient(app) as http:
        yield http


@pytest.mark.parametrize("horizon", [1, 7, 48])
def test_shape_determinism_and_saved_totals(client: TestClient, horizon: int) -> None:
    """Every selected store has every direct horizon; all aggregate views sum stored values."""
    first = client.post("/api/v1/forecasts", json=request_body(horizon))
    assert first.status_code == 201, first.text
    response = ForecastResponse.model_validate(first.json())
    second = ForecastResponse.model_validate(
        client.post("/api/v1/forecasts", json=request_body(horizon)).json()
    )
    assert response.points == second.points
    assert response.totals == second.totals
    assert response.input_fingerprint == second.input_fingerprint
    assert response.forecast_id != second.forecast_id
    assert len(response.points) == 2 * horizon
    assert [(p.target_date, p.store_id) for p in response.points] == sorted(
        (p.target_date, p.store_id) for p in response.points
    )
    assert {p.horizon for p in response.points} == set(range(1, horizon + 1))
    assert all(p.target_date == CUTOFF + timedelta(days=p.horizon) for p in response.points)
    grand = sum((p.predicted_sales for p in response.points), Decimal(0))
    assert grand == response.totals.predicted_sales
    for totals in (
        response.totals.by_store,
        response.totals.daily,
        response.totals.weekly,
        response.totals.monthly,
    ):
        assert sum((p.predicted_sales for p in totals), Decimal(0)) == grand
    assert all(p.known_open is None for p in response.points)
    assert response.data.actual_data_cutoff == CUTOFF
    assert response.data.source_available_through == date(2015, 7, 31)
    assert response.generated_at.tzinfo is not None
    assert "2015-07-31" in response.warnings[0]
    assert response.totals.weekly[0].covered_from == date(2015, 7, 30)
    saved = client.get(f"/api/v1/forecasts/{response.forecast_id}")
    assert saved.status_code == 200 and saved.json() == first.json()


def test_reuses_weights_without_fitting_and_download_needs_no_model(
    client: TestClient, service: ForecastService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST never fits, registers or changes training state; GET/CSV reuse frozen SQL values."""

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Prediction must not fit or train")

    monkeypatch.setattr(NativeTreeAdapter, "fit", forbidden)
    monkeypatch.setattr("retailforecast.training.train.run_training", forbidden)
    monkeypatch.setattr("retailforecast.training.workflow.execute", forbidden)
    monkeypatch.setattr(service.registry, "register", forbidden)
    with service.sessions() as session:
        jobs = session.scalar(select(func.count()).select_from(TrainingJob))
        events = session.scalar(select(func.count()).select_from(ModelEvent))
    slot = service.registry.slot()
    result = client.post("/api/v1/forecasts", json=request_body())
    assert result.status_code == 201, result.text
    body = result.json()
    with service.sessions() as session:
        assert session.scalar(select(func.count()).select_from(TrainingJob)) == jobs
        assert session.scalar(select(func.count()).select_from(ModelEvent)) == events
    assert service.registry.slot() == slot
    monkeypatch.setattr(service.registry, "load", forbidden)
    assert client.get(f"/api/v1/forecasts/{body['forecast_id']}").json() == body
    exported = client.get(f"/api/v1/forecasts/{body['forecast_id']}/download.csv")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert len(rows) == 14
    assert sum((Decimal(row["predicted_sales"]) for row in rows), Decimal(0)) == Decimal(
        body["totals"]["predicted_sales"]
    )
    assert all(row["model_version_id"] == slot.active_model_version_id for row in rows)
    assert all(
        row["cutoff_date"] == CUTOFF.isoformat() and row["source_available_through"] == "2015-07-31"
        for row in rows
    )


@pytest.mark.parametrize("erase", [False, True])
def test_future_sales_mutation_cannot_change_predictions(
    client: TestClient, service: ForecastService, erase: bool
) -> None:
    """Even horizons past available labels cannot consume July 30/31 Sales or Customers."""
    before = client.post("/api/v1/forecasts", json=request_body(48)).json()
    with service.sessions.begin() as session:
        if erase:
            session.execute(delete(DailySale).where(DailySale.date > CUTOFF))
        else:
            session.execute(
                update(DailySale)
                .where(DailySale.date > CUTOFF)
                .values(sales=999999, customers=99999)
            )
    after = client.post("/api/v1/forecasts", json=request_body(48)).json()
    assert after["points"] == before["points"]
    assert after["input_fingerprint"] == before["input_fingerprint"]


def test_sql_and_training_feature_builders_match(
    service: ForecastService, completed_training: Path
) -> None:
    """SQL serving and normalized Parquet training use identical values, missingness and context."""
    version = service.registry.slot().active_model_version_id
    assert version is not None
    _, record = service.registry.load(version)
    request = ForecastRequest.model_validate(request_body(48))
    parquet = load_feature_builder(
        completed_training.parents[2] / "configs/data.yaml",
        "synthetic",
        store_ids=request.store_ids,
        assumptions=record.protocol.config.assumptions,
    )
    with service.sessions() as session:
        source_id = session.scalar(select(DatasetVersion.id))
        assert source_id is not None
        sql = load_sql_inputs(session, source_id, request, record.protocol.snapshot).builder
    for store_id in request.store_ids:
        for horizon in (1, 7, 48):
            key = ForecastKey(store_id=store_id, cutoff_date=CUTOFF, horizon_days=horizon)
            assert sql.build(key) == parquet.build(key)


def test_scenario_closures_and_unknown_categories(client: TestClient) -> None:
    """Explicit known closures follow evaluated policy; unseen category IDs use saved encoding."""
    body = request_body(7)
    body["scenarios"] = [
        {
            "store_id": 9001,
            "target_date": "2015-08-02",
            "available_as_of": "2015-07-29",
            "provenance": "Synthetic opening plan",
            "is_open": False,
            "state_holiday": "regional",
        }
    ]
    response = client.post("/api/v1/forecasts", json=body)
    assert response.status_code == 201, response.text
    parsed = ForecastResponse.model_validate(response.json())
    closed = next(
        p for p in parsed.points if p.store_id == 9001 and p.target_date == date(2015, 8, 2)
    )
    assert closed.predicted_sales == 0 and closed.closure_adjusted and closed.known_open is False
    other = next(
        p for p in parsed.points if p.store_id == 9002 and p.target_date == date(2015, 8, 2)
    )
    assert other.known_open is None and not other.closure_adjusted
    assert any("unseen" in message for message in parsed.warnings)


@pytest.mark.parametrize(
    "override",
    [
        {"store_ids": []},
        {"store_ids": [9001, 9001]},
        {"store_ids": [True]},
        {"horizon_days": 0},
        {"horizon_days": 49},
        {"horizon_days": "7"},
        {"Sales": 1},
        {"Customers": 1},
        {"algorithm": "auto"},
        {
            "scenarios": [
                {
                    "store_id": 9001,
                    "target_date": "2015-07-30",
                    "available_as_of": "2015-07-30",
                    "provenance": "Late plan",
                    "is_open": True,
                }
            ]
        },
        {
            "scenarios": [
                {
                    "store_id": 9001,
                    "target_date": "2015-08-30",
                    "available_as_of": "2015-07-29",
                    "provenance": "Wrong date",
                    "is_open": True,
                }
            ]
        },
    ],
)
def test_invalid_request_contract(client: TestClient, override: dict[str, object]) -> None:
    """Reject unsupported actuals, controls, empty stores and future-knowledge claims."""
    assert client.post("/api/v1/forecasts", json={**request_body(), **override}).status_code == 422


@pytest.mark.parametrize(
    ("override", "status", "code"),
    [
        ({"store_ids": [123456]}, 422, "unknown_store"),
        ({"cutoff_date": "2015-07-28"}, 409, "model_trained_after_cutoff"),
        ({"cutoff_date": "2026-10-20"}, 422, "cutoff_beyond_observed_data"),
    ],
)
def test_honest_domain_errors(
    client: TestClient, override: dict[str, object], status: int, code: str
) -> None:
    """Historical sources and post-cutoff fitted weights must not masquerade as compatible."""
    response = client.post("/api/v1/forecasts", json={**request_body(), **override})
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def test_no_active_model_and_empty_catalog(registry: ModelRegistry) -> None:
    """Empty infrastructure returns useful metadata and requires explicit model activation."""
    app = create_app()
    app.dependency_overrides[forecast_service] = lambda: ForecastService(registry)
    with TestClient(app) as client:
        response = client.post("/api/v1/forecasts", json=request_body())
        assert response.status_code == 503 and response.json()["error"]["code"] == "no_active_model"
        assert client.get("/api/v1/stores").json()["items"] == []
        assert (
            client.get("/api/v1/datasets/status").json()["active_model_dataset_version_id"] is None
        )


def test_catalog_search_pagination_and_model_alias(client: TestClient) -> None:
    """Discover source dates, supported store cohort and versions before asking for predictions."""
    status = client.get("/api/v1/datasets/status").json()
    assert status["latest"]["available_through"] == "2015-07-31"
    assert status["active_model_dataset_version_id"] == status["latest"]["id"]
    page = client.get("/api/v1/stores", params={"search": "900", "page_size": 1, "page": 2}).json()
    assert page["total"] == 2 and page["items"][0]["store_id"] == 9002
    assert page["items"][0]["forecast_supported"]
    assert client.get("/api/v1/stores", params={"search": "%"}).json()["total"] == 0
    assert client.get("/api/v1/stores", params={"page_size": 101}).status_code == 422
    versions = client.get("/api/v1/models/versions")
    assert versions.status_code == 200 and len(versions.json()) == 1
    assert (
        client.get("/api/v1/models/active").json()["active_model_version_id"]
        == versions.json()[0]["id"]
    )
    registry_response = client.get("/api/v1/model/feature-registry").json()
    assert len(registry_response["fingerprint"]) == 64
    assert all(
        not feature["predictor"]
        for feature in registry_response["features"]
        if "customer" in feature["name"].lower()
    )


def test_missing_history_and_unseen_store(client: TestClient, service: ForecastService) -> None:
    """Distinguish stores outside the trained cohort from missing actuals."""
    with service.sessions.begin() as session:
        source_id = session.scalar(select(DatasetVersion.id))
        assert source_id is not None
        session.add(Store(source_version=source_id, store_id=9999))
        session.execute(delete(DailySale).where(DailySale.store_id == 9001))
    assert (
        client.post("/api/v1/forecasts", json={**request_body(), "store_ids": [9999]}).json()[
            "error"
        ]["code"]
        == "unsupported_store"
    )
    result = client.post("/api/v1/forecasts", json=request_body())
    assert result.status_code == 422 and result.json()["error"]["code"] == "missing_history"


def test_gap_and_cross_store_isolation(client: TestClient, service: ForecastService) -> None:
    """Isolate stores and disclose missing selected dates as gaps."""
    body = {**request_body(), "store_ids": [9001]}
    before = client.post("/api/v1/forecasts", json=body).json()
    with service.sessions.begin() as session:
        session.execute(update(DailySale).where(DailySale.store_id == 9002).values(sales=999999))
    isolated = client.post("/api/v1/forecasts", json=body).json()
    assert (
        before["points"] == isolated["points"]
        and before["input_fingerprint"] == isolated["input_fingerprint"]
    )
    with service.sessions.begin() as session:
        session.execute(
            delete(DailySale).where(
                DailySale.store_id == 9001, DailySale.date == CUTOFF - timedelta(days=1)
            )
        )
    gap = client.post("/api/v1/forecasts", json=body)
    assert gap.status_code == 201, gap.text
    assert gap.json()["data"]["history"][0]["missing_days_in_last_28"] == 1
    assert any("missing" in warning for warning in gap.json()["warnings"])


def test_point_write_failure_rolls_back_and_releases_slot(service: ForecastService) -> None:
    """A database failure cannot leave a partial run or permanently occupy the prediction slot."""

    def fail_points(session: Session, *args: object) -> None:
        if any(isinstance(row, ForecastPoint) for row in session.new):
            raise RuntimeError("controlled point write failure")

    event.listen(Session, "before_flush", fail_points)
    try:
        with pytest.raises(RuntimeError, match="controlled point"):
            service.create(ForecastRequest.model_validate(request_body()))
    finally:
        event.remove(Session, "before_flush", fail_points)
    with service.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ForecastRun)) == 0
        assert session.scalar(select(func.count()).select_from(ForecastPoint)) == 0
    assert len(service.create(ForecastRequest.model_validate(request_body())).points) == 14


@pytest.mark.parametrize("damage", ["corrupt", "missing"])
def test_corrupt_model_and_missing_forecast(
    client: TestClient, service: ForecastService, damage: str
) -> None:
    """Missing/corrupt native weights fail honestly without a training fallback."""
    version = service.registry.slot().active_model_version_id
    assert version is not None
    weights = service.registry.artifact_root / version / "model/model.json"
    if damage == "missing":
        weights.unlink()
    else:
        weights.write_text("corrupt", encoding="utf-8")
    result = client.post("/api/v1/forecasts", json=request_body())
    assert result.status_code == 503 and result.json()["error"]["code"] == "model_unavailable"
    assert client.get(f"/api/v1/forecasts/{uuid4()}").status_code == 404


def test_active_switch_does_not_mix_versions(
    service: ForecastService, completed_training: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An in-flight request keeps its pinned weights even if rollback archives that version."""
    old = service.registry.slot().active_model_version_id
    assert old is not None
    current = service.registry.register(completed_training)
    remove_legacy_validation(service.registry, old)
    remove_legacy_validation(service.registry, current)
    activate(service.registry, current, 1, approval_reason="Synthetic-only concurrent serving test")
    original_predict = TreeModel.predict
    switched = False

    def switch(model: TreeModel, features: FeatureRow) -> float:
        nonlocal switched
        if not switched:
            switched = True
            activate(
                service.registry,
                old,
                2,
                rollback=True,
                approval_reason="Synthetic-only in-flight rollback test",
            )
        return original_predict(model, features)

    monkeypatch.setattr(TreeModel, "predict", switch)
    response = service.create(ForecastRequest.model_validate(request_body()))
    assert response.model.version_id == current and response.model.generation == 2
    assert service.registry.slot().active_model_version_id == old
    assert service.registry.slot().generation == 3
    assert service.get(response.forecast_id) == response


def test_forecast_migration_roundtrip(postgres_database: tuple[Engine, str]) -> None:
    """Frozen migration upgrade/downgrade installs the context and point disclosure columns."""
    engine, schema = postgres_database
    migrate_schema(engine, schema, "719de0a9b001", downgrade=True)
    assert "request_context" not in {
        column["name"] for column in inspect(engine).get_columns("forecast_runs", schema=schema)
    }
    migrate_schema(engine, schema, "head")
    assert "request_context" in {
        column["name"] for column in inspect(engine).get_columns("forecast_runs", schema=schema)
    }
    assert {"known_open", "closure_adjusted", "nonnegative_clamped"} <= {
        column["name"] for column in inspect(engine).get_columns("forecast_points", schema=schema)
    }


def test_openapi_contract_is_current() -> None:
    """Public schemas include every phase-10 route and Decimal strings, matching the snapshot."""
    specification = create_app().openapi()
    expected = json.loads(
        (Path(__file__).resolve().parents[1] / "docs/openapi.json").read_text(encoding="utf-8")
    )
    assert specification == expected
    for suffix in (
        "health",
        "datasets/status",
        "stores",
        "models/active",
        "models/versions",
        "forecasts",
        "forecasts/{forecast_id}",
        "forecasts/{forecast_id}/download.csv",
        "model/feature-registry",
    ):
        assert f"/api/v1/{suffix}" in specification["paths"]
    point = specification["components"]["schemas"]["ForecastDay"]["properties"]
    assert point["predicted_sales"]["type"] == "string"
    request = specification["components"]["schemas"]["ForecastRequest"]["properties"]
    assert request["horizon_days"]["minimum"] == 1 and request["horizon_days"]["maximum"] == 48


def test_bounded_inference_and_range_failures(
    service: ForecastService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Busy, nonfinite and oversized model outputs fail rather than corrupt stored reports."""
    assert service._prediction_slots.acquire(blocking=False)
    try:
        with pytest.raises(ForecastError) as busy:
            service.create(ForecastRequest.model_validate(request_body()))
        assert busy.value.code == "forecast_busy"
    finally:
        service._prediction_slots.release()
    monkeypatch.setattr(TreeModel, "predict", lambda *args: 1e100)
    with pytest.raises(ForecastError) as huge:
        service.create(ForecastRequest.model_validate(request_body()))
    assert huge.value.code == "prediction_out_of_range"
    monkeypatch.setattr(TreeModel, "predict", lambda *args: float("nan"))
    with pytest.raises(ForecastError) as nonfinite:
        service.create(ForecastRequest.model_validate(request_body()))
    assert nonfinite.value.code == "feature_schema_incompatible"
    with service.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ForecastRun)) == 0


def test_negative_output_uses_evaluated_policy(
    service: ForecastService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative raw outputs use the same disclosed clamp tested in evaluation."""
    monkeypatch.setattr(TreeModel, "predict", lambda *args: -5.0)
    response = service.create(ForecastRequest.model_validate(request_body(1)))
    assert all(
        point.predicted_sales == 0 and point.nonnegative_clamped for point in response.points
    )
    assert response.totals.predicted_sales == 0
    assert any("clipped" in warning for warning in response.warnings)


def test_dashboard_options_and_saved_store_views(
    client: TestClient, service: ForecastService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dashboard setup/subset views reuse saved weights and exact totals, never training."""

    def forbid_fit(*args: object, **kwargs: object) -> None:
        raise AssertionError("Dashboard must never train")

    monkeypatch.setattr(NativeTreeAdapter, "fit", forbid_fit)
    setup = client.get("/api/v1/forecasts/options")
    assert setup.status_code == 200, setup.text
    options = setup.json()
    assert options["model"]["version_id"] == service.registry.slot().active_model_version_id
    assert {row["store_id"] for row in options["stores"]} == {9001, 9002}
    created = client.post("/api/v1/forecasts", json=request_body(7)).json()
    saved = client.get(
        f"/api/v1/forecasts/{created['forecast_id']}/view", params={"store_id": 9001}
    )
    assert saved.status_code == 200, saved.text
    view = saved.json()
    expected = [row for row in created["points"] if row["store_id"] == 9001]
    assert view["points"] == expected
    assert Decimal(view["totals"]["predicted_sales"]) == sum(
        Decimal(row["predicted_sales"]) for row in expected
    )
    assert sum(Decimal(row["predicted_sales"]) for row in view["totals"]["weekly"]) == Decimal(
        view["totals"]["predicted_sales"]
    )
    assert (
        client.get(
            f"/api/v1/forecasts/{created['forecast_id']}/view", params={"store_id": 99999}
        ).status_code
        == 422
    )
