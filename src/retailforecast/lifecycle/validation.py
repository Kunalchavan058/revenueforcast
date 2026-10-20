"""Retain and verify the pre-refit models used for chronological model selection."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from retailforecast.data.pipeline_config import canonical_json, content_hash
from retailforecast.data.validation import file_checksum
from retailforecast.evaluation.artifacts import EvaluationProtocol
from retailforecast.evaluation.contracts import TrainingHistory
from retailforecast.training.adapters import NativeTreeAdapter, TreeModel
from retailforecast.training.contracts import Algorithm, InternalParameters, ModeSettings


class FoldArtifact(BaseModel):
    """Seal each validation model against its exact fitting cutoff."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    cutoff_date: date
    bundle_sha256: str


class ValidationManifest(BaseModel):
    """Link historical validation weights to the recipe and final refit they evaluate."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    training_sha256: str
    refit_bundle_sha256: str
    protocol: EvaluationProtocol
    algorithm: Algorithm
    parameters: InternalParameters
    seed: int
    n_jobs: int
    mode_settings: ModeSettings
    folds: tuple[FoldArtifact, ...]

    @property
    def recipe_fingerprint(self) -> str:
        """Identify the fitted recipe, disclosing differences in history/row sampling."""
        return content_hash(
            {
                "algorithm": self.algorithm,
                "parameters": self.parameters.model_dump(),
                "seed": self.seed,
                "mode_settings": self.mode_settings.model_dump(),
                "registry": self.protocol.registry_sha256,
            }
        )


@dataclass(frozen=True)
class ValidationModels:
    """A verified manifest and its immutable local fold model directories."""

    directory: Path
    manifest: ValidationManifest

    def load(self, cutoff_date: date) -> TreeModel:
        """Load only the matching past-fitted model, never the later final refit."""
        matches = [item for item in self.manifest.folds if item.cutoff_date == cutoff_date]
        if len(matches) != 1:
            raise ValueError("No unique retained validation model for this cutoff")
        path = self.directory / cutoff_date.isoformat()
        if file_checksum(path / "bundle.json") != matches[0].bundle_sha256:
            raise ValueError("Validation model manifest checksum mismatch")
        model = NativeTreeAdapter(self.manifest.algorithm).load(path)
        if (
            model.trained_until != cutoff_date
            or model.metadata.training_span.label_end > cutoff_date
            or model.metadata.context != self.manifest.protocol.snapshot
            or model.metadata.parameters != self.manifest.parameters
            or model.metadata.seed != self.manifest.seed
            or model.metadata.n_jobs != self.manifest.n_jobs
            or model.metadata.training_span.rows > self.manifest.mode_settings.max_rows
            or model.metadata.training_span.origin_stride_days
            != self.manifest.mode_settings.origin_stride_days
            or set(model.metadata.training_span.store_ids)
            != set(self.manifest.protocol.config.store_ids)
        ):
            raise ValueError("Validation model recipe, lineage or fitting cutoff mismatch")
        return model


def preserve_validation_models(
    source: Path,
    destination: Path,
    *,
    selected_trial: str,
    protocol: EvaluationProtocol,
    model: TreeModel,
    mode_settings: ModeSettings,
) -> ValidationModels:
    """Copy original fold models and seal their link to the completed final model.

    Final weights may include validation dates after model selection. The fold
    weights predate their own targets and are the correct selection evidence.
    """
    destination.mkdir(parents=True, exist_ok=False)
    artifacts: list[FoldArtifact] = []
    for fold in protocol.plan.folds:
        if fold.role != "development":
            continue
        original = source / "folds" / selected_trial / fold.cutoff_date.isoformat()
        target = destination / fold.cutoff_date.isoformat()
        shutil.copytree(original, target)
        artifacts.append(
            FoldArtifact(
                cutoff_date=fold.cutoff_date, bundle_sha256=file_checksum(target / "bundle.json")
            )
        )
    manifest = ValidationManifest(
        training_sha256=file_checksum(source / "training.json"),
        refit_bundle_sha256=file_checksum(source / "model/bundle.json"),
        protocol=protocol,
        algorithm=model.metadata.algorithm,
        parameters=model.metadata.parameters,
        seed=model.metadata.seed,
        n_jobs=model.metadata.n_jobs,
        mode_settings=mode_settings,
        folds=tuple(artifacts),
    )
    validation = ValidationModels(destination, manifest)
    for artifact in artifacts:
        validation.load(artifact.cutoff_date)
    (destination / "validation.json").write_bytes(canonical_json(manifest.model_dump(mode="json")))
    return validation


def open_validation_models(
    directory: Path,
    *,
    expected_sha256: str,
    training_sha256: str,
    refit_bundle_sha256: str,
    protocol: EvaluationProtocol,
    model: TreeModel,
) -> ValidationModels:
    """Verify the database seal and parent recipe before using historical fold weights."""
    path = directory / "validation.json"
    if file_checksum(path) != expected_sha256:
        raise ValueError("Validation provenance checksum mismatch")
    manifest = ValidationManifest.model_validate_json(path.read_bytes())
    if (
        manifest.training_sha256 != training_sha256
        or manifest.refit_bundle_sha256 != refit_bundle_sha256
        or manifest.protocol != protocol
        or manifest.algorithm != model.metadata.algorithm
        or manifest.parameters != model.metadata.parameters
        or manifest.seed != model.metadata.seed
        or manifest.n_jobs != model.metadata.n_jobs
        or {item.cutoff_date for item in manifest.folds}
        != {fold.cutoff_date for fold in protocol.plan.folds if fold.role == "development"}
        or len(manifest.folds) != protocol.config.development_folds
    ):
        raise ValueError("Validation evidence does not belong to the registered final model")
    return ValidationModels(directory, manifest)


@dataclass(frozen=True)
class RetainedFoldFactory:
    """Reuse each original fold fit while the evaluator hides subsequent labels."""

    name: str
    validation: ValidationModels

    def fit(self, history: TrainingHistory) -> TreeModel:
        """Resolve saved weights fitted at exactly this simulated historical origin."""
        return self.validation.load(history.cutoff_date)
