"""Synthetic end-to-end tuning, MLflow audit, Auto selection and failure isolation."""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from mlflow.tracking import MlflowClient
from test_backtesting import config
from test_file_pipeline import fixture_project

from retailforecast.data.file_pipeline import run_pipeline
from retailforecast.training.adapters import NativeTreeAdapter
from retailforecast.training.contracts import TrainingConfig, TrainingRequest
from retailforecast.training.train import run_training
from retailforecast.training.workflow import execute

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt into disposable SQLite metadata explicitly; production requires PostgreSQL."""
    monkeypatch.setenv("RETAILFORECAST_TEST_MLFLOW_SQLITE", "1")


def request_fixture(root: Path, algorithm: str = "auto") -> TrainingRequest:
    """Create 90 explicitly synthetic store-days, enough for supervised warmup and folds."""
    data_config = fixture_project(root)
    path = root / "data/raw/synthetic/train.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        fields = csv.DictReader(handle).fieldnames
    assert fields is not None
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for offset in range(90):
            day = date(2015, 5, 3) + timedelta(days=offset)
            for store in (9001, 9002):
                opened = int(day.isoweekday() != 7)
                writer.writerow(
                    {
                        "Store": store,
                        "Date": day.isoformat(),
                        "DayOfWeek": day.isoweekday(),
                        "Sales": float(100 + offset + store % 10) if opened else 0.0,
                        "Customers": 4 if opened else 0,
                        "Open": opened,
                        "Promo": 0,
                        "StateHoliday": "0",
                        "SchoolHoliday": 0,
                    }
                )
    run_pipeline(data_config, "synthetic")
    values = yaml.safe_load((ROOT / "configs/training.yaml").read_text())
    values["search"] = [{"trees": 4, "max_depth": 2, "learning_rate": 0.1, "min_leaf_rows": 2}]
    for mode in values["modes"].values():
        mode.update(max_trials_per_algorithm=1, max_rows=192, elapsed_seconds=120)
    values["resources"].update(n_jobs=1, min_available_memory_mb=0)
    return TrainingRequest.model_validate(
        {
            "algorithm": algorithm,
            "mode": "dev",
            "training": TrainingConfig.model_validate(values),
            "backtest": config(2, (9001, 9002)),
            "data_config": str(data_config),
            "profile": "synthetic",
        }
    )


def test_supervised_auto_fits_saves_preprocessing_and_logs_real_metrics(tmp_path: Path) -> None:
    """Exercise the real worker process and both families without Kaggle or an MLflow server."""
    request = request_fixture(tmp_path)
    output = tmp_path / "artifacts/training/auto"
    status = run_training(request, output, root=tmp_path)
    assert status["state"] == "succeeded"
    summary = json.loads((output / "training.json").read_bytes())
    assert summary["requested_algorithm"] == "auto"
    assert summary["resolved_algorithm"] in {"xgboost", "lightgbm"}
    assert {trial["algorithm"] for trial in summary["trials"]} == {"xgboost", "lightgbm"}
    assert all(trial["status"] == "evaluated" for trial in summary["trials"])
    assert summary["final_holdout_scored"] is False
    assert {
        item["value"] for item in summary["comparison_summaries"] if item["axis"] == "horizon_day"
    } == {"1", "2"}
    assert summary["trained_until"] == "2015-07-29"
    assert (output / "model/preprocessing.json").exists()
    assert not (output / "candidate").exists()
    assert not (output / "comparison/selection.json").exists()
    model = NativeTreeAdapter(summary["resolved_algorithm"]).load(output / "model")
    assert model.metadata.training_span.label_end <= date(2015, 7, 29)
    client = MlflowClient(
        tracking_uri="sqlite:///" + (tmp_path / "artifacts/mlflow/metadata.db").as_posix()
    )
    for trial in summary["trials"]:
        recorded = client.get_run(trial["mlflow_run_id"])
        assert recorded.info.status == "FINISHED"
        assert recorded.data.params["trees"] == "4"
        assert "native.objective" in recorded.data.params
        assert any("horizon." in key and key.endswith("mae") for key in recorded.data.metrics)
    assert client.get_run(summary["mlflow_run_id"]).info.status == "FINISHED"


def test_failed_requested_algorithm_does_not_publish_or_silently_use_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every failed ML candidate leaves a failed audit rather than a fake baseline success."""
    request = request_fixture(tmp_path, "lightgbm")
    output = tmp_path / "artifacts/training/failed"
    output.mkdir(parents=True)
    (output / "request.json").write_text(request.model_dump_json())

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("controlled native fitting failure")

    monkeypatch.setattr(NativeTreeAdapter, "fit", fail)
    with pytest.raises(ValueError, match="No eligible tree candidate"):
        execute(request, output, root=tmp_path)
    trials = json.loads((output / "trials.json").read_bytes())
    assert trials[0]["status"] == "failed"
    assert not (output / "candidate").exists() and not (output / "model").exists()
    client = MlflowClient(
        tracking_uri="sqlite:///" + (tmp_path / "artifacts/mlflow/metadata.db").as_posix()
    )
    assert client.get_run(trials[0]["mlflow_run_id"]).info.status == "FAILED"
