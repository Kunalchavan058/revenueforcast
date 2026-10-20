"""Bounded chronological search, honest baseline comparison and final candidate refit."""

from __future__ import annotations

import gc
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from retailforecast.data.file_pipeline import verify_manifest
from retailforecast.data.pipeline_config import canonical_json
from retailforecast.evaluation.artifacts import ROOT, build_protocol, reserve_holdout, write_results
from retailforecast.evaluation.contracts import TrainingHistory
from retailforecast.evaluation.metrics import Segment, choose_method, summarize
from retailforecast.evaluation.runner import (
    PredictionPoint,
    generate_predictions,
    score_predictions,
)
from retailforecast.evaluation.snapshot import historical_span, load_outcomes
from retailforecast.evaluation.splits import make_plan
from retailforecast.features.builder import FeatureBuilder
from retailforecast.features.contracts import ForecastKey
from retailforecast.features.snapshot import load_feature_builder
from retailforecast.forecasting.baselines import BASELINE_NAMES, BaselineFactory
from retailforecast.training.adapters import NativeTreeAdapter, TreeModel
from retailforecast.training.contracts import (
    Algorithm,
    InternalParameters,
    ModeSettings,
    TrainingRequest,
)
from retailforecast.training.dataset import PreparedData, prepare_training_data
from retailforecast.training.tracking import LocalTracker


class TrialRecord(BaseModel):
    """Internal search audit; failed/incomplete candidates cannot win Auto selection."""

    name: str
    algorithm: Algorithm
    parameters: InternalParameters
    mlflow_run_id: str
    status: str
    duration_seconds: float
    error: str | None = None


@dataclass
class TreeFactory:
    """Bridge the common evaluation factory to fold-local prepared supervised data."""

    name: str
    algorithm: Algorithm
    parameters: InternalParameters
    builder: FeatureBuilder
    settings: ModeSettings
    seed: int
    n_jobs: int
    output: Path
    tracker: LocalTracker
    run_id: str
    cache: dict[date, PreparedData] = field(default_factory=dict)

    def fit(self, history: TrainingHistory) -> TreeModel:
        """Fit from a physically available history; reuse only identical fold preprocessing."""
        if history.cutoff_date not in self.cache:
            self.cache[history.cutoff_date] = prepare_training_data(
                self.builder, history, self.settings
            )
        data = self.cache[history.cutoff_date]
        started = time.monotonic()
        model = NativeTreeAdapter(self.algorithm).fit(
            data, self.parameters, seed=self.seed, n_jobs=self.n_jobs
        )
        location = self.output / "folds" / self.name / history.cutoff_date.isoformat()
        model.save(location)
        restored = NativeTreeAdapter(self.algorithm).load(location)
        probe = self.builder.build(
            ForecastKey(
                store_id=data.span.store_ids[0], cutoff_date=history.cutoff_date, horizon_days=48
            )
        )
        if abs(model.predict(probe) - restored.predict(probe)) > 1e-5:
            raise ValueError("Fold model serialization round trip changed its prediction")
        self.tracker.metrics(
            self.run_id,
            {
                f"fit_{history.cutoff_date}_seconds": time.monotonic() - started,
                f"fit_{history.cutoff_date}_rows": float(data.span.rows),
            },
        )
        self.tracker.params(
            self.run_id,
            {f"native.{key}": value for key, value in model.metadata.native_parameters.items()},
        )
        self.tracker.artifact(self.run_id, location / "bundle.json", f"folds/{history.cutoff_date}")
        return model


def log_scores(tracker: LocalTracker, run_id: str, segments: list[Segment], method: str) -> None:
    """Log calculated aggregate/fold/horizon metrics without inventing undefined scores."""
    values: dict[str, float] = {}
    for segment in segments:
        if segment.method != method or segment.axis not in {
            "aggregate",
            "fold",
            "horizon",
            "horizon_day",
        }:
            continue
        for key, value in segment.metrics.model_dump().items():
            if isinstance(value, (float, int)):
                values[f"{method}.{segment.axis}.{segment.value}.{key}"] = float(value)
    tracker.metrics(run_id, values)


def refit_history_without_holdout(
    builder: FeatureBuilder, request: TrainingRequest, cutoff: date
) -> tuple[TrainingHistory, int]:
    """Remove protected Sales from targets and all lag/rolling inputs of a later refit.

    Original June 14..July 31 labels remain unavailable to fitting, even when
    legitimate August observations are appended and the serving cutoff advances.
    Development cutoffs remain the original pre-holdout dates.
    """
    observations = tuple(builder.history_at_cutoff(request.backtest.store_ids, cutoff))
    safe = observations
    if request.protected_holdout:
        protected = request.protected_holdout
        safe = tuple(
            row
            for row in observations
            if not protected.cutoff_date < row.date <= protected.target_end
        )
    return TrainingHistory(cutoff_date=cutoff, observations=safe), len(observations) - len(safe)


def execute(request: TrainingRequest, output: Path, *, root: Path = ROOT) -> None:
    """Fit/evaluate every bounded trial, select on development only, and stage a refit model.

    The reserved final target window never enters tuning or final-candidate fitting.
    Only a successfully supervised coordinator may publish candidate/ as model/.
    """
    started = time.monotonic()
    settings = request.training.modes[request.mode]
    data_config = Path(request.data_config)
    builder = load_feature_builder(
        data_config,
        request.profile,
        store_ids=request.backtest.store_ids,
        assumptions=request.backtest.assumptions,
    )
    if builder.context is None:
        raise ValueError("Training requires a verified dataset context")
    start, end = historical_span(data_config, request.profile)
    plan = request.validation_plan or make_plan(start, end, request.backtest)
    protocol = build_protocol(request.backtest, plan, builder.context)
    reserve_holdout(root / "artifacts/evaluation/holdout_locks", protocol)
    tracker = LocalTracker(root / "artifacts/mlflow", output)
    parent = tracker.start(f"{request.algorithm}-{request.mode}")
    try:
        tracker.params(
            parent,
            {
                "requested_algorithm": request.algorithm,
                "mode": request.mode,
                "seed": request.training.seed,
                "n_jobs": request.training.resources.n_jobs,
                "dataset_fingerprint": builder.context.dataset_fingerprint,
                "code_revision": protocol.code_revision,
                "selection_policy": "mean_development_fold_rmspe_then_mae_then_name",
                "refit_cutoff": plan.folds[-1].cutoff_date.isoformat(),
            },
        )
        tracker.artifact(parent, output / "request.json")
        predictions: list[PredictionPoint] = generate_predictions(
            builder,
            plan.folds[:-1],
            request.backtest,
            [BaselineFactory(name, request.backtest.seasonal_weeks) for name in BASELINE_NAMES],
        )
        families: tuple[Algorithm, ...] = (
            ("xgboost", "lightgbm") if request.algorithm == "auto" else (request.algorithm,)
        )
        records: list[TrialRecord] = []
        cache: dict[date, PreparedData] = {}
        for algorithm in families:
            for index, parameters in enumerate(
                request.training.search[: settings.max_trials_per_algorithm], 1
            ):
                name = f"{algorithm}_trial_{index}"
                run_id = tracker.start(name, parent)
                tracker.params(
                    run_id,
                    {
                        "algorithm": algorithm,
                        "seed": request.training.seed,
                        "n_jobs": request.training.resources.n_jobs,
                        **parameters.model_dump(),
                    },
                )
                trial_started = time.monotonic()
                factory = TreeFactory(
                    name,
                    algorithm,
                    parameters,
                    builder,
                    settings,
                    request.training.seed,
                    request.training.resources.n_jobs,
                    output,
                    tracker,
                    run_id,
                    cache,
                )
                try:
                    points = generate_predictions(
                        builder, plan.folds[:-1], request.backtest, [factory]
                    )
                    predictions.extend(points)
                    record = TrialRecord(
                        name=name,
                        algorithm=algorithm,
                        parameters=parameters,
                        mlflow_run_id=run_id,
                        status="evaluated",
                        duration_seconds=time.monotonic() - trial_started,
                    )
                except Exception as exc:
                    record = TrialRecord(
                        name=name,
                        algorithm=algorithm,
                        parameters=parameters,
                        mlflow_run_id=run_id,
                        status="failed",
                        duration_seconds=time.monotonic() - trial_started,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    tracker.finish(run_id, False)
                records.append(record)
                (output / "trials.json").write_bytes(
                    canonical_json([item.model_dump(mode="json") for item in records])
                )
                gc.collect()
        # Labels are exposed only after all candidate prediction paths complete.
        outcomes = load_outcomes(
            data_config, request.profile, request.backtest.store_ids, request.backtest.assumptions
        )
        scored = score_predictions(
            predictions,
            outcomes,
            scoring_as_of=end + timedelta(days=request.backtest.assumptions.sales_delay_days),
        )
        segments = summarize(scored, exact_horizons=True)
        eligible_names = {item.name for item in records if item.status == "evaluated"}
        selected = choose_method([item for item in segments if item.method in eligible_names])
        for record in records:
            if record.status == "evaluated":
                log_scores(tracker, record.mlflow_run_id, segments, record.name)
                tracker.metrics(
                    record.mlflow_run_id, {"trial_duration_seconds": record.duration_seconds}
                )
                tracker.finish(record.mlflow_run_id, True)
        for baseline in BASELINE_NAMES:
            log_scores(tracker, parent, segments, baseline)
        if selected is None:
            raise ValueError(
                "No eligible tree candidate completed every validation fold; "
                "baselines are not a silent fallback"
            )
        winner = next(item for item in records if item.name == selected)
        comparison = write_results(
            output / "comparison",
            protocol,
            "development",
            tuple(dict.fromkeys(point.method for point in scored)),
            scored,
            segments,
            selected,
            emit_selection=False,
        )
        tracker.artifact(parent, output / "comparison/results.json", "evaluation")
        # Refit only through the reserved final origin (June 13 in this snapshot),
        # not July 31. Holding back final labels is as important as excluding them
        # from hyperparameter selection.
        refit_cutoff = request.refit_until or plan.folds[-1].cutoff_date
        refit_history, excluded_count = refit_history_without_holdout(
            builder, request, refit_cutoff
        )
        refit_data = prepare_training_data(builder, refit_history, settings)
        model = NativeTreeAdapter(winner.algorithm).fit(
            refit_data,
            winner.parameters,
            seed=request.training.seed,
            n_jobs=request.training.resources.n_jobs,
        )
        model.save(output / "candidate")
        loaded = NativeTreeAdapter(winner.algorithm).load(output / "candidate")
        for horizon in (1, 48):
            probe = builder.build(
                ForecastKey(
                    store_id=refit_data.span.store_ids[0],
                    cutoff_date=refit_cutoff,
                    horizon_days=horizon,
                )
            )
            if abs(model.predict(probe) - loaded.predict(probe)) > 1e-5:
                raise ValueError("Candidate serialization changed predictions")
        current = verify_manifest(data_config, request.profile)
        if current.dataset_fingerprint != protocol.snapshot.dataset_fingerprint:
            raise ValueError("Dataset changed during training")
        summary = {
            "schema_version": 1,
            "requested_algorithm": request.algorithm,
            "resolved_algorithm": winner.algorithm,
            "selected_trial": selected,
            "mode": request.mode,
            "mlflow_run_id": parent,
            "trained_at": datetime.now(UTC).isoformat(),
            "training_config": request.training.model_dump(mode="json"),
            "protocol": protocol.model_dump(mode="json"),
            "protocol_fingerprint": protocol.fingerprint,
            "ingestion_dataset_checksum": current.ingestion_dataset_checksum,
            "training_span": model.metadata.training_span.model_dump(mode="json"),
            "trained_until": refit_cutoff.isoformat(),
            "model_location": "model",
            "preprocessing_location": "model/preprocessing.json",
            "comparison_location": "comparison/results.json",
            "duration_seconds": time.monotonic() - started,
            "trials": [item.model_dump(mode="json") for item in records],
            "comparison_summaries": [item.model_dump(mode="json") for item in comparison.summaries],
            "final_holdout_scored": False,
            "protected_holdout": request.protected_holdout.model_dump(mode="json")
            if request.protected_holdout
            else None,
            "refit_excluded_observations": excluded_count,
            "business_dataset_version_id": request.business_dataset_version_id,
            "business_source_checksum": request.business_source_checksum,
        }
        (output / "training.json").write_bytes(canonical_json(summary))
        tracker.params(
            parent,
            {
                "resolved_algorithm": winner.algorithm,
                "selected_trial": selected,
                "training_label_end": refit_cutoff.isoformat(),
            },
        )
        tracker.metrics(
            parent,
            {
                "duration_seconds": time.monotonic() - started,
                "refit_rows": float(refit_data.span.rows),
            },
        )
        tracker.artifact(parent, output / "training.json")
        for artifact in (output / "candidate").iterdir():
            tracker.artifact(parent, artifact, "model")
        tracker.finish(parent, True)
        (output / "ready.json").write_bytes(
            canonical_json({"algorithm": winner.algorithm, "mlflow_run_id": parent})
        )
    except BaseException:
        tracker.finish(parent, False)
        raise
