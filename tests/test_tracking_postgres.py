"""Verify the normal tracking path uses the dedicated local PostgreSQL backend."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from retailforecast.lifecycle.settings import tracking_uri
from retailforecast.storage.database import DatabaseSettings
from retailforecast.training.tracking import LocalTracker


@pytest.mark.integration
def test_real_postgresql_tracking_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise a real metadata run and local file artifact with no SQLite fallback."""
    monkeypatch.delenv("RETAILFORECAST_TEST_MLFLOW_SQLITE", raising=False)
    output = tmp_path / "output"
    output.mkdir()
    uri = tracking_uri(tmp_path / "tracking")
    business = make_url(DatabaseSettings().database_url.get_secret_value())
    backend = make_url(uri)
    assert backend.database != business.database and backend.username != business.username
    engine = create_engine(uri, hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == "retailforecast_mlflow"
    finally:
        engine.dispose()
    tracker = LocalTracker(tmp_path / "tracking", output)
    run_id = tracker.start("synthetic-only-postgresql-integration")
    tracker.params(run_id, {"fixture": "synthetic-only", "seed": 42})
    note = output / "fixture.txt"
    note.write_text("Synthetic-only tracking test; no model metric is claimed.", encoding="utf-8")
    tracker.artifact(run_id, note)
    tracker.finish(run_id, True)
    run = tracker.client.get_run(run_id)
    assert run.info.status == "FINISHED" and run.data.params["seed"] == "42"
    assert run.info.artifact_uri.startswith("file:")
    assert tracker.client.list_artifacts(run_id, "metadata")[0].path == "metadata/fixture.txt"
