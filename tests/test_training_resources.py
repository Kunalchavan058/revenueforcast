"""Training concurrency, hard resource limits and failure publication boundaries."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from retailforecast.evaluation.contracts import BacktestConfig
from retailforecast.training.contracts import ResourceSettings, TrainingConfig, TrainingRequest
from retailforecast.training.resources import ResourceLimitError, supervise, training_lock
from retailforecast.training.train import run_training

ROOT = Path(__file__).resolve().parents[1]


def test_single_training_lock_rejects_another_job_and_releases(tmp_path: Path) -> None:
    """Two CLI jobs cannot train concurrently on the same laptop slot."""
    path = tmp_path / "training.lock"
    first = training_lock(path)
    try:
        with pytest.raises(RuntimeError, match="Another training job"):
            training_lock(path)
    finally:
        first.release()
    second = training_lock(path)
    second.release()


def test_elapsed_limit_kills_owned_worker() -> None:
    """The budget can interrupt native work, rather than waiting for a trial boundary."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    settings = ResourceSettings(
        warning_memory_mb=3000, max_memory_mb=4000, min_available_memory_mb=0, poll_seconds=0.05
    )
    with pytest.raises(ResourceLimitError, match="elapsed-time"):
        supervise(child, settings, 0.05)
    assert child.poll() is not None


def test_memory_limit_warns_and_kills_owned_worker() -> None:
    """Sampled RSS warnings are visible and hard memory excess stops the job."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    settings = ResourceSettings(
        warning_memory_mb=1, max_memory_mb=2, min_available_memory_mb=0, poll_seconds=0.05
    )
    with pytest.warns(RuntimeWarning, match="RSS"):
        with pytest.raises(ResourceLimitError, match="memory budget"):
            supervise(child, settings, 10)
    assert child.poll() is not None


def test_failed_worker_does_not_publish_model_and_releases_slot(tmp_path: Path) -> None:
    """A genuinely failing subprocess leaves audit/logs and cannot replace an earlier model."""
    config = TrainingConfig.model_validate(
        yaml.safe_load((ROOT / "configs/training.yaml").read_text())
    )
    evaluation = BacktestConfig.model_validate(
        yaml.safe_load((ROOT / "configs/backtest.yaml").read_text())
    )
    request = TrainingRequest(
        algorithm="lightgbm",
        mode="dev",
        training=config,
        backtest=evaluation,
        data_config=str(tmp_path / "missing.yaml"),
    )
    prior = tmp_path / "artifacts/training/previous/model"
    prior.mkdir(parents=True)
    (prior / "sentinel").write_text("retained")
    output = tmp_path / "artifacts/training/failed"
    with pytest.raises(RuntimeError, match="worker exited"):
        run_training(request, output, root=tmp_path)
    assert json.loads((output / "status.json").read_bytes())["state"] == "failed"
    assert not (output / "model").exists()
    assert (prior / "sentinel").read_text() == "retained"
    lock = training_lock(tmp_path / "artifacts/training/.training.lock")
    lock.release()
