"""Train CPU models with one job, enforced budgets and no user-facing tuning knobs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from retailforecast.data.pipeline_config import DEFAULT_CONFIG, canonical_json
from retailforecast.evaluation.contracts import BacktestConfig
from retailforecast.training.contracts import TrainingConfig, TrainingRequest
from retailforecast.training.resources import supervise, training_lock

ROOT = Path(__file__).resolve().parents[3]


def run_training(request: TrainingRequest, output: Path, *, root: Path = ROOT) -> dict[str, object]:
    """Own the lock, supervise one child, and atomically publish only a verified candidate.

    Failures retain logs/audit but never replace a previous bundle or create a
    completed model directory. No PostgreSQL approval/active pointer is touched.
    """
    allowed = (root / "artifacts/training").resolve()
    output = output.resolve()
    if (
        not output.is_relative_to(allowed)
        or output == allowed
        or not allowed.is_relative_to(root.resolve())
    ):
        raise ValueError("Training output must be a subdirectory of artifacts/training")
    if output.exists():
        raise ValueError("Training output already exists; choose a new run directory")
    lock = training_lock(allowed / ".training.lock")
    try:
        output.mkdir(parents=True)
        (output / "request.json").write_bytes(canonical_json(request.model_dump(mode="json")))
        status: dict[str, object] = {
            "state": "running",
            "requested_algorithm": request.algorithm,
            "mode": request.mode,
            "started_at": datetime.now(UTC).isoformat(),
        }
        status_path = output / "status.json"
        status_path.write_bytes(canonical_json(status))
        environment = os.environ.copy()
        for key in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
        ):
            environment[key] = str(request.training.resources.n_jobs)
        environment["MLFLOW_DISABLE_AGENT_HINT"] = "1"
        process: subprocess.Popen[bytes] | None = None
        try:
            with (output / "worker.log").open("wb") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "retailforecast.training.worker",
                        "--output",
                        str(output),
                        "--root",
                        str(root),
                    ],
                    cwd=root,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                resource_metrics = supervise(
                    process,
                    request.training.resources,
                    request.training.modes[request.mode].elapsed_seconds,
                )
            ready = json.loads((output / "ready.json").read_bytes())
            from retailforecast.training.adapters import NativeTreeAdapter

            NativeTreeAdapter(ready["algorithm"]).load(output / "candidate")
            from retailforecast.training.tracking import LocalTracker

            tracker = LocalTracker(root / "artifacts/mlflow", output)
            tracker.metrics(ready["mlflow_run_id"], resource_metrics)

            # A successful native process and verified saved state are both
            # required before making the model directory visible as completed.
            (output / "candidate").rename(output / "model")
            status.update(
                state="succeeded",
                completed_at=datetime.now(UTC).isoformat(),
                resolved_algorithm=ready["algorithm"],
                mlflow_run_id=ready["mlflow_run_id"],
                resources=resource_metrics,
                model_location="model",
            )
        except BaseException as exc:
            from retailforecast.training.resources import terminate_job

            if process is not None and process.poll() is None:
                terminate_job(process)
            status.update(
                state="failed",
                completed_at=datetime.now(UTC).isoformat(),
                error=f"{type(exc).__name__}: {exc}",
            )
            status_path.write_bytes(canonical_json(status))
            from retailforecast.training.tracking import close_interrupted_runs

            close_interrupted_runs(root / "artifacts/mlflow", output)
            raise
        status_path.write_bytes(canonical_json(status))
        return status
    finally:
        lock.release()


def main() -> None:
    """Select algorithm and dev/full mode; all tuning parameters stay in backend config."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algorithm", choices=("xgboost", "lightgbm", "auto"), required=True)
    parser.add_argument("--mode", choices=("dev", "full"), default="dev")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/training.yaml")
    parser.add_argument("--backtest-config", type=Path, default=ROOT / "configs/backtest.yaml")
    parser.add_argument("--data-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--profile", choices=("synthetic", "rossmann"), default="rossmann")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        request = TrainingRequest(
            algorithm=args.algorithm,
            mode=args.mode,
            training=TrainingConfig.model_validate(
                yaml.safe_load(args.config.read_text(encoding="utf-8"))
            ),
            backtest=BacktestConfig.model_validate(
                yaml.safe_load(args.backtest_config.read_text(encoding="utf-8"))
            ),
            data_config=str(args.data_config.resolve()),
            profile=args.profile,
        )
        relative = (
            args.output or f"artifacts/training/{args.algorithm}-{args.mode}-{uuid4().hex[:10]}"
        )
        if Path(relative).is_absolute():
            raise ValueError("Output must be a relative directory under artifacts/training")
        output = ROOT / relative
        status = run_training(request, output)
        print(json.dumps(status, indent=2))
        print(f"Run files: {output.relative_to(ROOT).as_posix()}")
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(2, f"Training failed: {exc}\n")


if __name__ == "__main__":
    main()
