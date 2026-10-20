"""Local PostgreSQL-backed MLflow tracking; SQLite is an explicit test backend only."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import cast

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

from mlflow.tracking import MlflowClient

from retailforecast.data.pipeline_config import canonical_json
from retailforecast.lifecycle.settings import tracking_uri


class LocalTracker:
    """Log complete parent/trial metadata and expose IDs for interrupted-run recovery."""

    def __init__(self, root: Path, output: Path) -> None:
        """Use separate PostgreSQL metadata and local files; never store model bytes in SQL."""
        root.mkdir(parents=True, exist_ok=True)
        self.client = MlflowClient(tracking_uri=tracking_uri(root))
        experiment = self.client.get_experiment_by_name("retailforecast-training")
        self.experiment_id = (
            experiment.experiment_id
            if experiment is not None
            else self.client.create_experiment(
                "retailforecast-training", artifact_location=(root / "artifacts").as_uri()
            )
        )
        self.output = output
        self.ids: list[str] = []

    def start(self, name: str, parent: str | None = None) -> str:
        """Create one audited run; parent and trial runs share the experiment."""
        tags = {"mlflow.runName": name}
        if parent is not None:
            tags["mlflow.parentRunId"] = parent
        run_id = cast(str, self.client.create_run(self.experiment_id, tags=tags).info.run_id)
        self.ids.append(run_id)
        (self.output / "mlflow-runs.json").write_bytes(canonical_json(self.ids))
        return run_id

    def params(self, run_id: str, values: Mapping[str, str | int | float]) -> None:
        """Preserve exact internal parameters rather than exposing tuning controls in UI."""
        for name, value in values.items():
            self.client.log_param(run_id, name, value)

    def metrics(self, run_id: str, values: Mapping[str, float]) -> None:
        """Record only genuine finite calculated metrics, omitting undefined values."""
        for name, value in values.items():
            self.client.log_metric(run_id, name, value)

    def artifact(self, run_id: str, path: Path, group: str = "metadata") -> None:
        """Copy an inspectable local artifact; no model bytes enter the metadata database."""
        self.client.log_artifact(run_id, str(path), artifact_path=group)

    def finish(self, run_id: str, success: bool) -> None:
        """Close successful or failed trials explicitly."""
        self.client.set_terminated(run_id, status="FINISHED" if success else "FAILED")


def close_interrupted_runs(root: Path, output: Path) -> None:
    """Mark still-running MLflow records failed after an owned worker is terminated."""
    import json

    path = output / "mlflow-runs.json"
    if not path.exists():
        return
    client = MlflowClient(tracking_uri=tracking_uri(root))
    for run_id in json.loads(path.read_bytes()):
        if client.get_run(run_id).info.status == "RUNNING":
            client.set_terminated(run_id, status="FAILED")
