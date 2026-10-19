"""Exercise atomic imports and constraints against migrated PostgreSQL, not SQLite."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from conftest import migrate_schema
from rossmann_fixtures import write_bundle
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from retailforecast.data import ingestion
from retailforecast.data.contracts import ImportRequest
from retailforecast.storage.database import session_factory
from retailforecast.storage.models import (
    DailySale,
    DatasetVersion,
    ForecastInput,
    ImportJob,
    ModelVersion,
    Store,
)

pytestmark = pytest.mark.integration


def import_request(source: Path) -> ImportRequest:
    """Build an actual publication request with stable validation bounds."""
    return ImportRequest(
        source_dir=str(source),
        dry_run=False,
        maximum_date=date(2026, 12, 31),
    )


def test_duplicate_import_and_label_separation(
    tmp_path: Path,
    postgres_database: tuple[Engine, str],
) -> None:
    """Repeat import without duplicate business rows; persist every import attempt."""
    engine, _ = postgres_database
    request = import_request(write_bundle(tmp_path / "source"))
    first = ingestion.import_bundle(request, engine, tmp_path / "raw")
    second = ingestion.import_bundle(request, engine, tmp_path / "raw")
    assert first.state == "succeeded"
    assert second.state == "duplicate"
    assert first.dataset_version_id == second.dataset_version_id
    with session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 1
        assert session.scalar(select(func.count()).select_from(DailySale)) == 2
        assert session.scalar(select(func.count()).select_from(ForecastInput)) == 1
        assert session.scalar(select(func.count()).select_from(ImportJob)) == 2
        actual = session.scalar(select(DailySale).where(DailySale.date == date(2015, 7, 31)))
        assert actual is not None and actual.sales == 0 and not actual.is_open


def test_transaction_rollback_keeps_failure_audit(
    tmp_path: Path,
    postgres_database: tuple[Engine, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail after store inserts and prove dataset/stores/actuals roll back together."""
    engine, _ = postgres_database
    request = import_request(write_bundle(tmp_path / "source"))
    original = ingestion.insert_file

    def fail_during_sales(session: Session, path: Path, dataset_id: str) -> None:
        if path.name == "train.csv":
            raise RuntimeError("Controlled transaction failure")
        original(session, path, dataset_id)

    monkeypatch.setattr(ingestion, "insert_file", fail_during_sales)
    with pytest.raises(RuntimeError, match="Controlled"):
        ingestion.import_bundle(request, engine, tmp_path / "raw")
    with session_factory(engine)() as session:
        for model in [DatasetVersion, Store, DailySale, ForecastInput]:
            assert session.scalar(select(func.count()).select_from(model)) == 0
        audit = session.scalar(select(ImportJob))
        assert audit is not None and audit.state == "failed"
        assert audit.error_code == "RuntimeError"


def test_broken_import_records_failure_without_dataset(
    tmp_path: Path,
    postgres_database: tuple[Engine, str],
) -> None:
    """Reject a broken source bundle before any business data is published."""
    engine, _ = postgres_database
    result = ingestion.import_bundle(import_request(tmp_path), engine, tmp_path / "raw")
    assert result.state == "rejected"
    with session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 0
        audit = session.scalar(select(ImportJob))
        assert audit is not None and audit.error_code == "validation_failed"


def test_one_active_model_per_scope(
    tmp_path: Path,
    postgres_database: tuple[Engine, str],
) -> None:
    """PostgreSQL rejects a second active artifact reference in the same scope."""
    engine, _ = postgres_database
    imported = ingestion.import_bundle(
        import_request(write_bundle(tmp_path / "source")),
        engine,
        tmp_path / "raw",
    )
    for attempt in [1, 2]:

        def add_active(attempt_id: int = attempt) -> None:
            with session_factory(engine).begin() as session:
                session.add(
                    ModelVersion(
                        dataset_version_id=imported.dataset_version_id,
                        scope="fixture-lineage:features-v1:lightgbm:cutoff-policy-v1",
                        algorithm="lightgbm",
                        trained_until=date(2015, 7, 31),
                        artifact_uri=f"fixture-only-{attempt_id}",
                        feature_schema_fingerprint="0" * 64,
                        status="active",
                    )
                )

        if attempt == 1:
            add_active()
        else:
            with pytest.raises(IntegrityError):
                add_active()


def test_migration_downgrade_and_upgrade(
    postgres_database: tuple[Engine, str],
) -> None:
    """Round-trip the migration only in a disposable, generated schema."""
    engine, schema = postgres_database
    assert inspect(engine).has_table("daily_sales", schema=schema)
    migrate_schema(engine, schema, "base", downgrade=True)
    assert not inspect(engine).has_table("daily_sales", schema=schema)
    migrate_schema(engine, schema, "head")
    assert inspect(engine).has_table("forecast_inputs", schema=schema)


def test_concurrent_duplicate_imports(
    tmp_path: Path,
    postgres_database: tuple[Engine, str],
) -> None:
    """Equal concurrent requests publish exactly one snapshot under an advisory lock."""
    from concurrent.futures import ThreadPoolExecutor

    engine, _ = postgres_database
    request = import_request(write_bundle(tmp_path / "source"))

    def publish() -> str:
        return ingestion.import_bundle(request, engine, tmp_path / "raw").state

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: publish(), range(2)))
    assert sorted(results) == ["duplicate", "succeeded"]
    with session_factory(engine)() as session:
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 1
        assert session.scalar(select(func.count()).select_from(DailySale)) == 2
