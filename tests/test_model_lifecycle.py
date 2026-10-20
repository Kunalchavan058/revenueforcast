"""Real PostgreSQL lifecycle concurrency, artifact gates, rollback and fixed-weight scoring."""

from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Barrier

import pyarrow.parquet as pq
import pytest
from conftest import migrate_schema
from fastapi.testclient import TestClient
from main import create_app
from models import model_registry
from sqlalchemy import Engine, event, func, inspect, select
from sqlalchemy.orm import Session
from test_training_workflow import request_fixture

from retailforecast.evaluation.artifacts import verify_results
from retailforecast.features.builder import FeatureRow
from retailforecast.features.contracts import ForecastKey
from retailforecast.features.snapshot import load_feature_builder
from retailforecast.lifecycle.comparison import compare_models, shared_folds
from retailforecast.lifecycle.registry import ModelRegistry, TrainingRecord, schema_fingerprint
from retailforecast.storage.database import session_factory
from retailforecast.storage.models import (
    DatasetVersion,
    ModelEvent,
    ModelRegistration,
    ModelVersion,
)
from retailforecast.training.adapters import NativeTreeAdapter, TreeModel
from retailforecast.training.contracts import InternalParameters
from retailforecast.training.train import run_training


@pytest.fixture(scope="module")
def completed_training(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Fit genuine tiny synthetic weights once, without consuming the real final holdout."""
    root = tmp_path_factory.mktemp("lifecycle_training")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("RETAILFORECAST_TEST_MLFLOW_SQLITE", "1")
        request = request_fixture(root, "xgboost")
        output = root / "artifacts/training/verified"
        assert run_training(request, output, root=root)["state"] == "succeeded"
    return output


@pytest.fixture
def registry(
    postgres_database: tuple[Engine, str],
    tmp_path: Path,
    completed_training: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ModelRegistry:
    """Use real migrated business tables and explicitly disposable MLflow metadata."""
    monkeypatch.setenv("RETAILFORECAST_TEST_MLFLOW_SQLITE", "1")
    engine, _ = postgres_database
    record = TrainingRecord.model_validate_json((completed_training / "training.json").read_bytes())
    with session_factory(engine).begin() as session:
        session.add(
            DatasetVersion(
                source="synthetic-only lifecycle test",
                checksum=record.ingestion_dataset_checksum,
                version=record.protocol.snapshot.dataset_fingerprint,
                rows=180,
                available_through=date(2015, 7, 31),
                availability_policy="Explicit test assumptions",
                raw_uri="synthetic-only",
                validation_report={},
            )
        )
    return ModelRegistry(engine, tmp_path / "registry", tmp_path / "mlflow")


def remove_legacy_validation(registry: ModelRegistry, version: str) -> None:
    """Represent a pre-fix registration that did not retain fold model references."""
    with registry.sessions.begin() as session:
        row = session.get(ModelRegistration, version)
        assert row is not None
        row.evidence = {
            key: value
            for key, value in row.evidence.items()
            if key not in ("validation_directory", "validation_sha256")
        }


@pytest.fixture(scope="module")
def one_tree_training(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Fit a second genuine recipe so promotion can be tested using measured differences."""
    root = tmp_path_factory.mktemp("lifecycle_one_tree")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("RETAILFORECAST_TEST_MLFLOW_SQLITE", "1")
        request = request_fixture(root, "xgboost")
        settings = request.training.model_copy(
            update={
                "search": (
                    InternalParameters(trees=1, max_depth=2, learning_rate=0.1, min_leaf_rows=2),
                )
            }
        )
        request = request.model_copy(update={"training": settings})
        output = root / "artifacts/training/one-tree"
        assert run_training(request, output, root=root)["state"] == "succeeded"
    return output


def activate(registry: ModelRegistry, version: str, generation: int, **kwargs: object) -> None:
    """Apply a transition using test dataset configuration only."""
    reason = kwargs.get("approval_reason")
    registry.activate(
        version,
        expected_generation=generation,
        data_config=Path("unused-for-insufficient-evidence.yaml"),
        profile="synthetic",
        approval_reason=reason if isinstance(reason, str) else None,
        rollback=bool(kwargs.get("rollback", False)),
    )


def test_bootstrap_pending_approval_and_checked_rollback(
    registry: ModelRegistry,
    completed_training: Path,
) -> None:
    """No eligible shared window means pending approval, never an invented improvement."""
    first = registry.register(completed_training)
    second = registry.register(completed_training)
    activate(registry, first, 0)
    model, record = registry.load(first)
    pinned = registry.pin(record.trained_until, schema_fingerprint(model))
    builder = load_feature_builder(
        completed_training.parents[2] / "configs/data.yaml",
        "synthetic",
        store_ids=record.protocol.config.store_ids,
        assumptions=record.protocol.config.assumptions,
    )
    probe = builder.build(
        ForecastKey(store_id=9001, cutoff_date=record.trained_until, horizon_days=48)
    )
    prediction_before = pinned.model.predict(probe)
    remove_legacy_validation(registry, first)
    remove_legacy_validation(registry, second)
    activate(registry, second, 1)
    assert registry.slot().active_model_version_id == first
    assert next(item for item in registry.list_versions() if item.id == second).approval_required
    activate(
        registry, second, 1, approval_reason="Synthetic test: explicitly accept missing evidence"
    )
    assert registry.slot().active_model_version_id == second
    assert pinned.version_id == first
    assert pinned.model.predict(probe) == prediction_before
    assert pinned.model.trained_until == model.trained_until
    activate(
        registry,
        first,
        2,
        rollback=True,
        approval_reason="Restore retained compatible test version",
    )
    assert registry.slot().generation == 3
    assert registry.slot().active_model_version_id == first
    assert {item.status for item in registry.list_versions()} == {"active", "archived"}
    with pytest.raises(ValueError, match="cutoff or feature schema"):
        registry.pin(date(2015, 7, 28), schema_fingerprint(model))
    with pytest.raises(ValueError, match="cutoff or feature schema"):
        registry.pin(record.trained_until, "incorrect-schema")


@pytest.mark.parametrize("damage", ["missing", "model", "preprocessing", "manifest"])
def test_corruption_never_replaces_incumbent(
    registry: ModelRegistry,
    completed_training: Path,
    damage: str,
) -> None:
    """Both implicit and explicit promotion must fail before mutating the pointer."""
    first, second = registry.register(completed_training), registry.register(completed_training)
    activate(registry, first, 0)
    directory = registry.artifact_root / second / "model"
    path = (
        directory
        / {
            "missing": "model.json",
            "model": "model.json",
            "preprocessing": "preprocessing.json",
            "manifest": "bundle.json",
        }[damage]
    )
    if damage == "missing":
        path.unlink()
    else:
        path.write_text("corrupted bytes")
    with pytest.raises((ValueError, FileNotFoundError)):
        activate(registry, second, 1, approval_reason="Must not bypass corruption")
    assert registry.slot().generation == 1
    assert registry.slot().active_model_version_id == first
    rejected = next(item for item in registry.list_versions() if item.id == second)
    assert rejected.status == "rejected" and rejected.decision_reason


def test_concurrent_promotions_require_generation_token(
    registry: ModelRegistry,
    completed_training: Path,
) -> None:
    """Two simultaneous bootstrap attempts yield exactly one winner and one stale request."""
    versions = (registry.register(completed_training), registry.register(completed_training))
    barrier = Barrier(2)

    def promote(version: str) -> str:
        barrier.wait(timeout=20)
        try:
            activate(registry, version, 0)
            return "activated"
        except ValueError as error:
            assert "Stale generation" in str(error)
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(promote, versions)) == ["activated", "stale"]
    with registry.sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ModelVersion)
                .where(ModelVersion.status == "active")
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(ModelEvent)) == 1


def test_failed_pointer_transaction_restores_incumbent(
    registry: ModelRegistry,
    completed_training: Path,
) -> None:
    """A failure after archiving but before commit rolls back pointer, roles and audit."""
    first, second = registry.register(completed_training), registry.register(completed_training)
    activate(registry, first, 0)

    def fail_event(session: Session, context: object, instances: object) -> None:
        if any(
            isinstance(item, ModelEvent) and item.model_version_id == second for item in session.new
        ):
            raise RuntimeError("Controlled audit failure after incumbent flush")

    remove_legacy_validation(registry, first)
    remove_legacy_validation(registry, second)
    event.listen(registry.sessions, "before_flush", fail_event)
    try:
        with pytest.raises(RuntimeError, match="Controlled audit failure"):
            activate(registry, second, 1, approval_reason="Synthetic transactional failure test")
    finally:
        event.remove(registry.sessions, "before_flush", fail_event)
    assert registry.slot().active_model_version_id == first and registry.slot().generation == 1
    assert {item.id: item.status for item in registry.list_versions()} == {
        first: "active",
        second: "candidate",
    }


def test_fixed_weights_use_shared_development_windows(completed_training: Path) -> None:
    """Real predictions are scored identically; refitted final weights have no eligible folds."""
    record = TrainingRecord.model_validate_json((completed_training / "training.json").read_bytes())
    first_fold = next(fold for fold in record.protocol.plan.folds if fold.role == "development")
    model = NativeTreeAdapter("xgboost").load(
        completed_training / "folds" / record.selected_trial / first_fold.cutoff_date.isoformat()
    )
    root = completed_training.parents[2]
    result = compare_models(
        model,
        model,
        record.protocol,
        record.protocol,
        data_config=root / "configs/data.yaml",
        profile="synthetic",
    )
    assert result.eligible and not result.improves
    assert len(result.folds) == 2
    assert any(
        item.axis == "horizon_day" and item.metrics.mae is not None for item in result.summaries
    )
    saved = NativeTreeAdapter("xgboost").load(completed_training / "model")
    assert shared_folds(saved, saved, record.protocol, record.protocol) == ()


def test_lifecycle_migration_roundtrip(postgres_database: tuple[Engine, str]) -> None:
    """The frozen migration can be removed and reapplied without touching source records."""
    engine, schema = postgres_database
    migrate_schema(engine, schema, "52b92c66f920", downgrade=True)
    assert "model_slots" not in inspect(engine).get_table_names(schema=schema)
    migrate_schema(engine, schema, "head")
    assert {"model_slots", "model_events", "model_registrations"}.issubset(
        inspect(engine).get_table_names(schema=schema)
    )


def test_measured_loser_is_rejected(
    registry: ModelRegistry, completed_training: Path, tmp_path: Path
) -> None:
    """Identical early saved weights yield a genuine tie, which retains the incumbent."""
    source = tmp_path / "early_synthetic_candidate"
    source.mkdir()
    record = TrainingRecord.model_validate_json((completed_training / "training.json").read_bytes())
    origin = next(
        fold.cutoff_date for fold in record.protocol.plan.folds if fold.role == "development"
    )
    shutil.copytree(
        completed_training / "folds" / record.selected_trial / origin.isoformat(), source / "model"
    )
    shutil.copytree(completed_training / "comparison", source / "comparison")
    shutil.copytree(completed_training / "folds", source / "folds")
    values = json.loads((completed_training / "training.json").read_bytes())
    values["trained_until"] = origin.isoformat()
    (source / "training.json").write_text(json.dumps(values))
    (source / "status.json").write_text('{"state":"succeeded"}')
    first, second = registry.register(source), registry.register(source)
    activate(registry, first, 0)
    registry.activate(
        second,
        expected_generation=1,
        data_config=completed_training.parents[2] / "configs/data.yaml",
        profile="synthetic",
    )
    rejected = next(item for item in registry.list_versions() if item.id == second)
    assert rejected.status == "rejected" and not rejected.approval_required
    assert rejected.evidence["comparison"]
    assert registry.slot().active_model_version_id == first
    assert registry.slot().generation == 1


def test_failed_training_is_not_publishable(
    registry: ModelRegistry, completed_training: Path, tmp_path: Path
) -> None:
    """An unsuccessful attempt cannot be turned into a candidate by reusing model files."""
    source = tmp_path / "failed_training"
    source.mkdir()
    (source / "status.json").write_text('{"state":"failed"}')
    with pytest.raises(ValueError, match="successfully completed"):
        registry.register(source)
    assert registry.slot().active_model_version_id is None


def test_model_api_uses_same_registry_gates(
    registry: ModelRegistry, completed_training: Path
) -> None:
    """HTTP requests require a generation token and expose actual persisted decisions."""
    version = registry.register(completed_training)
    app = create_app()
    app.dependency_overrides[model_registry] = lambda: registry
    with TestClient(app) as client:
        assert client.get("/api/v1/models/active").json()["generation"] == 0
        assert client.get("/api/v1/models/unknown").status_code == 404
        assert client.post(f"/api/v1/models/{version}/activate", json={}).status_code == 422
        assert (
            client.post(
                f"/api/v1/models/{version}/activate", json={"expected_generation": 0}
            ).status_code
            == 200
        )
        assert client.get(f"/api/v1/models/{version}").json()["status"] == "active"
        assert (
            client.post(
                f"/api/v1/models/{version}/activate", json={"expected_generation": 0}
            ).status_code
            == 409
        )
        assert client.get("/api/v1/health").json()["status"] == "ok"


def test_retained_validation_resolves_final_refit_comparison(
    registry: ModelRegistry,
    completed_training: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final models include validation dates; original fold models still provide valid evidence."""
    first, second = registry.register(completed_training), registry.register(completed_training)
    activate(registry, first, 0)
    model, record = registry.load(first)
    original_predict = TreeModel.predict

    def reject_final_model_backdating(self: TreeModel, features: FeatureRow) -> float:
        if self.trained_until == record.trained_until:
            raise AssertionError("Final refit must not produce historical validation predictions")
        return original_predict(self, features)

    monkeypatch.setattr(TreeModel, "predict", reject_final_model_backdating)
    registry.activate(
        second,
        expected_generation=1,
        data_config=completed_training.parents[2] / "configs/data.yaml",
        profile="synthetic",
    )
    compared = next(item for item in registry.list_versions() if item.id == second)
    assert compared.status == "rejected" and not compared.approval_required
    evidence = compared.evidence["comparison"]
    assert isinstance(evidence, dict) and evidence["eligible"] is True
    assert evidence["basis"] == "retained_rolling_origin_models"
    assert len(evidence["recipe_fingerprints"]) == 2
    output = next((registry.artifact_root / second / "comparisons").iterdir())
    report = verify_results(output)
    assert report.selected_method == "incumbent"
    final_cutoff = next(
        fold.cutoff_date for fold in record.protocol.plan.folds if fold.role == "final"
    )
    points = pq.read_table(output / "predictions.parquet").to_pylist()
    assert points and all(point["trained_until"] == point["cutoff_date"] for point in points)
    assert all(point["target_date"] <= final_cutoff for point in points)
    assert all(item.metrics.coverage == 1 for item in report.summaries if item.axis == "fold")
    assert registry.slot().active_model_version_id == first


def test_measured_winner_is_promoted_without_override(
    registry: ModelRegistry,
    completed_training: Path,
    one_tree_training: Path,
) -> None:
    """Re-score two genuine recipes, then promote the measured winner without human override."""
    first, second = registry.register(completed_training), registry.register(one_tree_training)
    candidate, record = registry.load(first)
    incumbent, other_record = registry.load(second)
    config = completed_training.parents[2] / "configs/data.yaml"
    result = compare_models(
        candidate,
        incumbent,
        record.protocol,
        other_record.protocol,
        data_config=config,
        profile="synthetic",
        candidate_validation=registry.validation_models(first, candidate, record),
        incumbent_validation=registry.validation_models(second, incumbent, other_record),
    )
    assert result.eligible
    scores = {
        method: sum(
            item.metrics.rmspe
            for item in result.summaries
            if item.axis == "fold" and item.method == method and item.metrics.rmspe is not None
        )
        for method in ("candidate", "incumbent")
    }
    assert scores["candidate"] != scores["incumbent"]
    better, worse = (first, second) if result.improves else (second, first)
    registry.activate(worse, expected_generation=0, data_config=config, profile="synthetic")
    registry.activate(better, expected_generation=1, data_config=config, profile="synthetic")
    assert registry.slot().active_model_version_id == better and registry.slot().generation == 2
    winner = next(item for item in registry.list_versions() if item.id == better)
    assert winner.status == "active" and not winner.approval_required
    comparison = winner.evidence["comparison"]
    assert isinstance(comparison, dict) and comparison["improves"] is True


def test_legacy_validation_recovery_is_sealed_and_idempotent(
    registry: ModelRegistry,
    completed_training: Path,
) -> None:
    """Recover historical fold evidence without changing native weights or requiring approval."""
    version = registry.register(completed_training)
    remove_legacy_validation(registry, version)
    registry.attach_validation(version, completed_training)
    registry.attach_validation(version, completed_training)
    model, record = registry.load(version)
    assert registry.validation_models(version, model, record) is not None
    with registry.sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ModelEvent)
                .where(ModelEvent.action == "validation_attached")
            )
            == 1
        )


def test_future_fitted_validation_model_is_rejected(
    registry: ModelRegistry,
    completed_training: Path,
    tmp_path: Path,
) -> None:
    """A final model cannot masquerade as the earlier fold model, even with valid native hashes."""
    source = tmp_path / "wrong-fold"
    shutil.copytree(completed_training, source)
    record = TrainingRecord.model_validate_json((source / "training.json").read_bytes())
    cutoff = next(
        fold.cutoff_date for fold in record.protocol.plan.folds if fold.role == "development"
    )
    fold_path = source / "folds" / record.selected_trial / cutoff.isoformat()
    # These are generated temporary test files, never the repository's dataset or models.
    for path in fold_path.iterdir():
        path.unlink()
    for path in (source / "model").iterdir():
        shutil.copy2(path, fold_path / path.name)
    with pytest.raises(ValueError, match="fitting cutoff mismatch"):
        registry.register(source)
    assert registry.slot().active_model_version_id is None


@pytest.mark.parametrize("damage", ["manifest", "weights"])
def test_corrupt_validation_cannot_replace_active(
    registry: ModelRegistry,
    completed_training: Path,
    damage: str,
) -> None:
    """Registration seals protect fold evidence as well as the final model artifact."""
    first, second = registry.register(completed_training), registry.register(completed_training)
    activate(registry, first, 0)
    target = registry.artifact_root / second / "validation"
    if damage == "manifest":
        (target / "validation.json").write_text("corrupt validation provenance")
    else:
        fold_directory = next(path for path in target.iterdir() if path.is_dir())
        (fold_directory / "model.json").write_text("corrupt validation native weights")
    with pytest.raises(ValueError, match="checksum"):
        registry.activate(
            second,
            expected_generation=1,
            data_config=completed_training.parents[2] / "configs/data.yaml",
            profile="synthetic",
        )
    assert registry.slot().active_model_version_id == first and registry.slot().generation == 1
    assert next(item for item in registry.list_versions() if item.id == second).status == "rejected"
