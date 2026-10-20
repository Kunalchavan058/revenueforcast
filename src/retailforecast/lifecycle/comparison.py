"""Re-score shared chronological validation with the correct pre-refit model versions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from retailforecast.data.validation import file_checksum
from retailforecast.evaluation.artifacts import EvaluationProtocol, build_protocol, write_results
from retailforecast.evaluation.contracts import (
    FittedForecaster,
    Fold,
    ForecasterFactory,
    TrainingHistory,
)
from retailforecast.evaluation.metrics import Segment, summarize
from retailforecast.evaluation.runner import generate_predictions, score_predictions
from retailforecast.evaluation.snapshot import load_outcomes
from retailforecast.features.builder import FeatureRow
from retailforecast.features.snapshot import load_feature_builder
from retailforecast.lifecycle.validation import RetainedFoldFactory, ValidationModels
from retailforecast.training.adapters import TreeModel

MINIMUM_SHARED_FOLDS = 2


class Comparison(BaseModel):
    """Computed evidence or an explicit explanation of why promotion cannot be automatic."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    basis: Literal["saved_weights", "retained_rolling_origin_models"] = "saved_weights"
    recipe_fingerprints: dict[str, str] = {}
    training_policies: dict[str, dict[str, object]] = {}
    evaluation_reference: str | None = None
    evaluation_sha256: str | None = None
    eligible: bool
    improves: bool = False
    reason: str
    folds: tuple[Fold, ...] = ()
    summaries: tuple[Segment, ...] = ()


@dataclass(frozen=True)
class FixedModel:
    """Adapt a saved model to the shared evaluator without any refitting."""

    name: str
    model: TreeModel

    def fit(self, history: TrainingHistory) -> TreeModel:
        """Return immutable weights only when they predate the simulated origin."""
        if self.model.trained_until > history.cutoff_date:
            raise ValueError("Saved weights were trained after comparison cutoff")
        return self.model


@dataclass(frozen=True)
class ContextBoundModel:
    """Use identical feature values with each model's saved context after SQL lineage proof."""

    model: TreeModel

    @property
    def trained_until(self) -> date:
        """Keep the original fit guard; context rebinding never changes chronology or weights."""
        return self.model.trained_until

    def predict(self, features: FeatureRow) -> float:
        """Rebind identity only for certified unchanged-prefix append-only comparisons."""
        return self.model.predict(replace(features, context=self.model.metadata.context))


@dataclass(frozen=True)
class AppendOnlyFactory:
    """Wrap a retained/fixed factory only after the registry verifies compatible SQL lineage."""

    factory: ForecasterFactory

    @property
    def name(self) -> str:
        """Preserve the candidate/incumbent scoring identity."""
        return self.factory.name

    def fit(self, history: TrainingHistory) -> FittedForecaster:
        """Return each historical tree without refitting or exposing future outcomes."""
        model = self.factory.fit(history)
        if not isinstance(model, TreeModel):
            raise ValueError("Append-only comparisons require verified native tree models")
        return ContextBoundModel(model)


def shared_folds(
    candidate: TreeModel,
    incumbent: TreeModel,
    protocol: EvaluationProtocol,
    incumbent_protocol: EvaluationProtocol,
) -> tuple[Fold, ...]:
    """Exclude all reserved final targets and all origins predating either saved model."""
    if (
        candidate.metadata.context != incumbent.metadata.context
        or protocol.config != incumbent_protocol.config
        or candidate.metadata.training_span.store_ids != incumbent.metadata.training_span.store_ids
        or set(protocol.config.store_ids) != set(candidate.metadata.training_span.store_ids)
    ):
        return ()
    final_starts = [
        fold.cutoff_date
        for plan in (protocol.plan, incumbent_protocol.plan)
        for fold in plan.folds
        if fold.role == "final"
    ]
    if not final_starts:
        return ()
    last_development_date = min(final_starts)
    trained_until = max(candidate.trained_until, incumbent.trained_until)
    # June-13 weights cannot be tested at a January origin. Targets after June 13
    # belong to the locked final window, so an empty result is honest insufficiency.
    return tuple(
        fold
        for fold in protocol.plan.folds
        if fold.role == "development"
        and fold.cutoff_date >= trained_until
        and fold.target_end <= last_development_date
    )


def compare_models(
    candidate: TreeModel,
    incumbent: TreeModel,
    protocol: EvaluationProtocol,
    incumbent_protocol: EvaluationProtocol,
    *,
    data_config: Path,
    profile: str,
    candidate_validation: ValidationModels | None = None,
    incumbent_validation: ValidationModels | None = None,
    output: Path | None = None,
    append_only_context: bool = False,
) -> Comparison:
    """Compare mean fold RMSPE, tie-breaking by retaining incumbent; never score final dates."""
    folds = shared_folds(candidate, incumbent, protocol, incumbent_protocol)
    factories: tuple[ForecasterFactory, ...] = (
        FixedModel("candidate", candidate),
        FixedModel("incumbent", incumbent),
    )
    basis: Literal["saved_weights", "retained_rolling_origin_models"] = "saved_weights"
    recipes: dict[str, str] = {}
    policies: dict[str, dict[str, object]] = {}
    if len(folds) < MINIMUM_SHARED_FOLDS and candidate_validation and incumbent_validation:
        if (
            protocol.config != incumbent_protocol.config
            or (protocol.snapshot != incumbent_protocol.snapshot and not append_only_context)
            or protocol.registry_sha256 != incumbent_protocol.registry_sha256
        ):
            raise ValueError(
                "Validation requires matching data, features, stores, horizons and assumptions"
            )
        final_cutoffs = [
            fold.cutoff_date
            for plan in (protocol.plan, incumbent_protocol.plan)
            for fold in plan.folds
            if fold.role == "final"
        ]
        if not final_cutoffs:
            raise ValueError("Validation requires a reserved final holdout")
        incumbent_folds = {
            fold.fold_id: fold
            for fold in incumbent_protocol.plan.folds
            if fold.role == "development"
        }
        folds = tuple(
            fold
            for fold in protocol.plan.folds
            if fold.role == "development"
            and incumbent_folds.get(fold.fold_id) == fold
            and fold.target_end <= min(final_cutoffs)
        )
        factories = (
            RetainedFoldFactory("candidate", candidate_validation),
            RetainedFoldFactory("incumbent", incumbent_validation),
        )
        basis = "retained_rolling_origin_models"
        recipes = {
            "candidate": candidate_validation.manifest.recipe_fingerprint,
            "incumbent": incumbent_validation.manifest.recipe_fingerprint,
        }
        policies = {
            "candidate": candidate_validation.manifest.mode_settings.model_dump(mode="json"),
            "incumbent": incumbent_validation.manifest.mode_settings.model_dump(mode="json"),
        }
    if len(folds) < MINIMUM_SHARED_FOLDS:
        return Comparison(
            eligible=False,
            reason="Insufficient shared validation evidence; retain original fold models",
        )
    builder = load_feature_builder(
        data_config,
        profile,
        store_ids=protocol.config.store_ids,
        assumptions=protocol.config.assumptions,
    )
    if builder.context != candidate.metadata.context:
        raise ValueError("Comparison dataset/availability context differs from the saved models")
    if protocol.snapshot.assumptions != incumbent_protocol.snapshot.assumptions:
        raise ValueError("Append-only comparison cannot change knowledge assumptions")
    if append_only_context:
        factories = tuple(AppendOnlyFactory(factory) for factory in factories)
    predictions = generate_predictions(
        builder,
        folds,
        protocol.config,
        factories,
    )
    # Outcomes enter only after both models have emitted every requested prediction.
    outcomes = load_outcomes(
        data_config, profile, protocol.config.store_ids, protocol.config.assumptions
    )
    points = score_predictions(predictions, outcomes, scoring_as_of=protocol.plan.historical_end)
    summaries = tuple(summarize(points, exact_horizons=True))
    fold_metrics = [item for item in summaries if item.axis == "fold"]
    if any(item.metrics.coverage != 1 or item.metrics.rmspe is None for item in fold_metrics):
        return Comparison(
            eligible=False,
            reason="Incomplete shared labels or undefined RMSPE",
            folds=folds,
            summaries=summaries,
        )
    means = {
        method: sum(
            item.metrics.rmspe
            for item in fold_metrics
            if item.method == method and item.metrics.rmspe is not None
        )
        / len(folds)
        for method in ("candidate", "incumbent")
    }
    improves = means["candidate"] < means["incumbent"]
    reference: str | None = None
    report_sha256: str | None = None
    if output is not None:
        current_protocol = build_protocol(protocol.config, protocol.plan, protocol.snapshot)
        write_results(
            output,
            current_protocol,
            "development",
            ("candidate", "incumbent"),
            points,
            summaries,
            "candidate" if improves else "incumbent",
            emit_selection=False,
        )
        reference = output.as_uri()
        report_sha256 = file_checksum(output / "results.json")
    return Comparison(
        basis=basis,
        recipe_fingerprints=recipes,
        training_policies=policies,
        evaluation_reference=reference,
        evaluation_sha256=report_sha256,
        eligible=True,
        improves=improves,
        reason="Lower shared mean-fold RMSPE"
        if improves
        else "Candidate did not improve shared mean-fold RMSPE",
        folds=folds,
        summaries=summaries,
    )
