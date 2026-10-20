"""Sealed local model publication and PostgreSQL-authoritative serving transitions."""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from mlflow.exceptions import MlflowException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from retailforecast.data.pipeline_config import content_hash
from retailforecast.data.validation import file_checksum
from retailforecast.evaluation.artifacts import EvaluationProtocol, verify_results
from retailforecast.features.registry import registry_fingerprint
from retailforecast.lifecycle.comparison import Comparison, compare_models
from retailforecast.lifecycle.validation import (
    ValidationModels,
    open_validation_models,
    preserve_validation_models,
)
from retailforecast.storage.database import new_id, session_factory
from retailforecast.storage.models import (
    DatasetVersion,
    ModelEvent,
    ModelRegistration,
    ModelSlot,
    ModelVersion,
)
from retailforecast.training.adapters import NativeTreeAdapter, TreeModel
from retailforecast.training.contracts import Algorithm, InternalParameters, Mode, TrainingConfig
from retailforecast.training.tracking import LocalTracker
from retailforecast.training.workflow import log_scores

SCOPE = "global-v1"
MLFLOW_MODEL_NAME = "retailforecast-global-v1"


class TrialRecord(BaseModel):
    """Bind the selected evaluated trial to the actual saved family and fit parameters."""

    model_config = ConfigDict(extra="ignore")
    name: str
    algorithm: Algorithm
    parameters: InternalParameters
    status: str


class TrainingRecord(BaseModel):
    """Read the successful training provenance needed for publication, not tuning controls."""

    model_config = ConfigDict(extra="ignore")
    resolved_algorithm: Algorithm
    selected_trial: str
    ingestion_dataset_checksum: str
    trained_until: date
    trained_at: datetime
    protocol: EvaluationProtocol
    final_holdout_scored: Literal[False]
    mlflow_run_id: str
    trials: tuple[TrialRecord, ...]
    mode: Mode
    training_config: TrainingConfig


class VersionView(BaseModel):
    """Stable inspectable model metadata with no database credentials or binary payloads."""

    id: str
    status: str
    algorithm: str
    trained_until: date
    trained_at: datetime
    dataset_version_id: str
    feature_schema_fingerprint: str
    artifact_uri: str
    evaluation_reference: str | None
    dataset_fingerprint: str
    mlflow_run_id: str | None
    mlflow_model_name: str
    mlflow_model_version: str
    approval_required: bool
    decision_reason: str | None
    evidence: dict[str, object]


class SlotView(BaseModel):
    """Generation is the required compare-and-swap token for every serving mutation."""

    generation: int
    active_model_version_id: str | None


@dataclass(frozen=True)
class PinnedModel:
    """A request owns this version and loaded weights across later pointer switches."""

    version_id: str
    generation: int
    model: TreeModel


def schema_fingerprint(model: TreeModel) -> str:
    """Bind registry, expanded columns and preprocessing format into one serving contract."""
    return content_hash(
        {
            "registry": model.preprocessing.registry_sha256,
            "columns": model.metadata.encoded_columns,
            "preprocessing_version": model.metadata.preprocessing_version,
        }
    )


class ModelRegistry:
    """Own publication and explicit transactions; model files are immutable and retained."""

    def __init__(self, engine: Engine, artifact_root: Path, tracking_root: Path) -> None:
        """Construct lazy infrastructure; readers never consult mutable MLflow aliases."""
        self.sessions = session_factory(engine)
        self.artifact_root = artifact_root.resolve()
        self.tracking_root = tracking_root.resolve()

    def slot(self) -> SlotView:
        """Read the committed pointer without blocking on an in-progress promotion."""
        with self.sessions() as session:
            slot = session.get(ModelSlot, SCOPE)
            return SlotView(
                generation=slot.generation if slot else 0,
                active_model_version_id=slot.active_model_version_id if slot else None,
            )

    def list_versions(self) -> list[VersionView]:
        """Return global V1 versions, including their latest decision and evidence."""
        with self.sessions() as session:
            pairs = session.execute(
                select(ModelVersion, ModelRegistration)
                .join(ModelRegistration, ModelRegistration.model_version_id == ModelVersion.id)
                .where(ModelVersion.scope == SCOPE)
                .order_by(ModelVersion.trained_at, ModelVersion.id)
            ).all()
            return [
                VersionView(
                    id=model.id,
                    status=model.status,
                    algorithm=model.algorithm,
                    trained_until=model.trained_until,
                    trained_at=model.trained_at,
                    dataset_version_id=model.dataset_version_id,
                    feature_schema_fingerprint=model.feature_schema_fingerprint,
                    artifact_uri=model.artifact_uri,
                    evaluation_reference=model.evaluation_reference,
                    dataset_fingerprint=registration.dataset_fingerprint,
                    mlflow_run_id=model.mlflow_run_id,
                    mlflow_model_name=registration.mlflow_model_name,
                    mlflow_model_version=registration.mlflow_model_version,
                    approval_required=registration.approval_required,
                    decision_reason=registration.decision_reason,
                    evidence=registration.evidence,
                )
                for model, registration in pairs
            ]

    def register(self, training_directory: Path) -> str:
        """Publish a genuine completed run as a non-serving candidate; legacy runs stay intact."""
        source = training_directory.resolve()
        if json.loads((source / "status.json").read_bytes()).get("state") != "succeeded":
            raise ValueError("Only a successfully completed training job can be registered")
        record = TrainingRecord.model_validate_json((source / "training.json").read_bytes())
        model = NativeTreeAdapter(record.resolved_algorithm).load(source / "model")
        report = verify_results(source / "comparison")
        selected = [trial for trial in record.trials if trial.name == record.selected_trial]
        if (
            len(selected) != 1
            or selected[0].status != "evaluated"
            or selected[0].algorithm != model.metadata.algorithm
            or selected[0].parameters != model.metadata.parameters
            or model.metadata.training_span.label_end != model.trained_until
            or model.metadata.seed != record.protocol.config.seed
        ):
            raise ValueError("Saved model does not match the selected evaluated trial")
        if (
            report.stage != "development"
            or report.protocol != record.protocol
            or model.trained_until != record.trained_until
            or model.metadata.context != record.protocol.snapshot
        ):
            raise ValueError("Training, model and evaluation provenance disagree")
        metrics = [
            item.metrics
            for item in report.summaries
            if item.method == record.selected_trial and item.axis == "fold"
        ]
        if len(metrics) != record.protocol.config.development_folds or any(
            item.coverage != 1 or item.rmspe is None or not math.isfinite(item.rmspe)
            for item in metrics
        ):
            raise ValueError("Candidate requires complete chronological validation metrics")
        if not any(
            fold.role == "final" and record.trained_until <= fold.cutoff_date
            for fold in record.protocol.plan.folds
        ):
            raise ValueError("Training must preserve the reserved final holdout")
        with self.sessions() as session:
            dataset = session.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.checksum == record.ingestion_dataset_checksum
                )
            )
            if dataset is None:
                raise ValueError("Import this exact validated dataset into PostgreSQL first")
            dataset_id = dataset.id
        version_id = new_id()
        target = self.artifact_root / version_id
        target.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source / "model", target / "model")
        shutil.copy2(source / "training.json", target / "training.json")
        shutil.copytree(source / "comparison", target / "comparison")
        NativeTreeAdapter(record.resolved_algorithm).load(target / "model")
        preserve_validation_models(
            source,
            target / "validation",
            selected_trial=record.selected_trial,
            protocol=record.protocol,
            model=model,
            mode_settings=record.training_config.modes[record.mode],
        )
        tracker = LocalTracker(self.tracking_root, target)
        # Legacy SQLite runs are preserved. An adoption run records the original ID
        # rather than pretending the old run already exists in the new backend.
        run_id = tracker.start("register-" + version_id)
        try:
            tracker.params(
                run_id,
                {
                    "source_training_run_id": record.mlflow_run_id,
                    "dataset_fingerprint": record.protocol.snapshot.dataset_fingerprint,
                    "trained_until": record.trained_until.isoformat(),
                    "app_model_version_id": version_id,
                },
            )
            tracker.params(
                run_id,
                {
                    "algorithm": record.resolved_algorithm,
                    "code_revision": record.protocol.code_revision,
                    "seed": model.metadata.seed,
                    **{
                        f"native.{name}": value
                        for name, value in model.metadata.native_parameters.items()
                    },
                },
            )
            log_scores(tracker, run_id, list(report.summaries), record.selected_trial)
            tracker.artifact(run_id, target / "training.json")
            tracker.artifact(run_id, target / "comparison/results.json", "evaluation")
            tracker.client.log_artifacts(
                run_id, str(target / "validation"), artifact_path="validation"
            )
            for path in (target / "model").iterdir():
                tracker.artifact(run_id, path, "model")
            try:
                tracker.client.create_registered_model(MLFLOW_MODEL_NAME)
            except MlflowException as error:
                if error.error_code != "RESOURCE_ALREADY_EXISTS":
                    raise
            registered = tracker.client.create_model_version(
                MLFLOW_MODEL_NAME,
                (target / "model").as_uri(),
                run_id,
                tags={"app_model_version_id": version_id},
            )
            if registered.status != "READY":
                raise ValueError("MLflow model version is not ready")
            tracker.finish(run_id, True)
            with self.sessions.begin() as session:
                session.add(
                    ModelVersion(
                        id=version_id,
                        dataset_version_id=dataset_id,
                        scope=SCOPE,
                        algorithm=record.resolved_algorithm,
                        trained_until=model.trained_until,
                        trained_at=record.trained_at,
                        artifact_uri=(target / "model").as_uri(),
                        feature_schema_fingerprint=schema_fingerprint(model),
                        mlflow_run_id=run_id,
                        evaluation_reference=(target / "comparison/results.json").as_uri(),
                        status="candidate",
                    )
                )
                session.flush()
                session.add(
                    ModelRegistration(
                        model_version_id=version_id,
                        bundle_sha256=file_checksum(target / "model/bundle.json"),
                        dataset_fingerprint=record.protocol.snapshot.dataset_fingerprint,
                        mlflow_model_name=MLFLOW_MODEL_NAME,
                        mlflow_model_version=str(registered.version),
                        evidence={
                            "training_sha256": file_checksum(target / "training.json"),
                            "evaluation_sha256": file_checksum(target / "comparison/results.json"),
                            "validation_directory": "validation",
                            "validation_sha256": file_checksum(
                                target / "validation/validation.json"
                            ),
                        },
                        approval_required=False,
                    )
                )
            return version_id
        except Exception:
            tracker.finish(run_id, False)
            raise

    def load(self, version_id: str) -> tuple[TreeModel, TrainingRecord]:
        """Verify sealed bytes, ordering, lineage and the current registry before use."""
        with self.sessions() as session:
            row = session.get(ModelVersion, version_id)
            registration = session.get(ModelRegistration, version_id)
            if row is None or registration is None or row.scope != SCOPE:
                raise ValueError("Unknown registered global V1 model")
            target = self.artifact_root / row.id
            if (
                row.artifact_uri != (target / "model").as_uri()
                or registration.bundle_sha256 != file_checksum(target / "model/bundle.json")
                or registration.evidence["training_sha256"]
                != file_checksum(target / "training.json")
                or registration.evidence["evaluation_sha256"]
                != file_checksum(target / "comparison/results.json")
            ):
                raise ValueError("Sealed model provenance checksum mismatch")
            model = NativeTreeAdapter(
                TrainingRecord.model_validate_json(
                    (target / "training.json").read_bytes()
                ).resolved_algorithm
            ).load(target / "model")
            record = TrainingRecord.model_validate_json((target / "training.json").read_bytes())
            verify_results(target / "comparison")
            if (
                schema_fingerprint(model) != row.feature_schema_fingerprint
                or model.preprocessing.registry_sha256 != registry_fingerprint()
                or model.trained_until != row.trained_until
                or model.metadata.algorithm != row.algorithm
                or model.metadata.context != record.protocol.snapshot
                or record.protocol.snapshot.dataset_fingerprint != registration.dataset_fingerprint
            ):
                raise ValueError("Model schema, cutoff or dataset lineage mismatch")
            return model, record

    def pin(self, cutoff_date: date, feature_schema_fingerprint: str) -> PinnedModel:
        """Pin the committed immutable version; switching never changes an existing request."""
        slot = self.slot()
        if slot.active_model_version_id is None:
            raise ValueError("No active model")
        model, _ = self.load(slot.active_model_version_id)
        if (
            model.trained_until > cutoff_date
            or schema_fingerprint(model) != feature_schema_fingerprint
        ):
            raise ValueError("Requested cutoff or feature schema is incompatible with active model")
        return PinnedModel(slot.active_model_version_id, slot.generation, model)

    def activate(
        self,
        version_id: str,
        *,
        expected_generation: int,
        data_config: Path,
        profile: str,
        approval_reason: str | None = None,
        rollback: bool = False,
    ) -> SlotView:
        """Check evidence and replace atomically, retaining the pointer on validation failure.

        Explicit approval can waive insufficient metric evidence only. It cannot waive
        artifact/schema/lineage validation or turn a measured losing candidate into a winner.
        """
        if approval_reason is not None and not approval_reason.strip():
            raise ValueError("Explicit approval requires a nonempty reason")
        try:
            candidate, candidate_record = self.load(version_id)
            candidate_validation = self.validation_models(version_id, candidate, candidate_record)
        except (ValueError, OSError) as error:
            self._record_invalid_candidate(version_id, expected_generation, type(error).__name__)
            raise
        with self.sessions.begin() as session:
            session.execute(
                insert(ModelSlot).values(scope=SCOPE, generation=0).on_conflict_do_nothing()
            )
            slot = session.scalar(
                select(ModelSlot).where(ModelSlot.scope == SCOPE).with_for_update()
            )
            assert slot is not None
            if slot.generation != expected_generation:
                raise ValueError("Stale generation; inspect the active slot and retry explicitly")
            row = session.get(ModelVersion, version_id)
            registration = session.get(ModelRegistration, version_id)
            assert row is not None and registration is not None
            allowed = "archived" if rollback else "candidate"
            if row.status != allowed:
                raise ValueError(f"Operation requires a {allowed} model")
            incumbent_id = slot.active_model_version_id
            decision = Comparison(eligible=True, improves=True, reason="First validated candidate")
            if incumbent_id is not None:
                incumbent, incumbent_record = self.load(incumbent_id)
                if (
                    candidate.metadata.context != incumbent.metadata.context
                    or candidate.metadata.training_span.store_ids
                    != incumbent.metadata.training_span.store_ids
                    or schema_fingerprint(candidate) != schema_fingerprint(incumbent)
                ):
                    raise ValueError(
                        "Replacement must preserve dataset context, schema and store coverage"
                    )
                if rollback:
                    if approval_reason is None:
                        raise ValueError("Rollback requires an explicit reason")
                    decision = Comparison(
                        eligible=True, improves=True, reason="Checked rollback: " + approval_reason
                    )
                else:
                    try:
                        decision = compare_models(
                            candidate,
                            incumbent,
                            candidate_record.protocol,
                            incumbent_record.protocol,
                            data_config=data_config,
                            profile=profile,
                            candidate_validation=candidate_validation,
                            incumbent_validation=self.validation_models(
                                incumbent_id, incumbent, incumbent_record
                            ),
                            output=self.artifact_root / version_id / "comparisons" / new_id(),
                        )
                    except (ValueError, OSError) as error:
                        decision = Comparison(
                            eligible=True,
                            improves=False,
                            reason="Shared evaluation failed validation: " + type(error).__name__,
                        )
            registration.evidence = {
                **registration.evidence,
                "comparison": decision.model_dump(mode="json"),
            }
            registration.decision_reason = decision.reason
            if not decision.eligible and approval_reason is None:
                registration.approval_required = True
                session.add(
                    ModelEvent(
                        model_version_id=version_id,
                        previous_model_version_id=incumbent_id,
                        generation=slot.generation,
                        action="approval_required",
                        reason=decision.reason,
                    )
                )
                return SlotView(generation=slot.generation, active_model_version_id=incumbent_id)
            if decision.eligible and not decision.improves:
                row.status = "rejected"
                registration.approval_required = False
                session.add(
                    ModelEvent(
                        model_version_id=version_id,
                        previous_model_version_id=incumbent_id,
                        generation=slot.generation,
                        action="rejected",
                        reason=decision.reason,
                    )
                )
                return SlotView(generation=slot.generation, active_model_version_id=incumbent_id)
            if incumbent_id is not None:
                incumbent_row = session.get(ModelVersion, incumbent_id)
                assert incumbent_row is not None
                incumbent_row.status = "archived"
                # Flush the incumbent first: PostgreSQL's partial unique index is immediate.
                session.flush()
            row.status = "active"
            slot.active_model_version_id = version_id
            slot.generation += 1
            registration.approval_required = False
            registration.decision_reason = approval_reason or decision.reason
            session.add(
                ModelEvent(
                    model_version_id=version_id,
                    previous_model_version_id=incumbent_id,
                    generation=slot.generation,
                    action="rollback" if rollback else "activated",
                    reason=registration.decision_reason,
                )
            )
            return SlotView(generation=slot.generation, active_model_version_id=version_id)

    def validation_models(
        self, version_id: str, model: TreeModel, record: TrainingRecord
    ) -> ValidationModels | None:
        """Resolve sealed historical fits; missing legacy evidence is distinct from corruption."""
        with self.sessions() as session:
            registration = session.get(ModelRegistration, version_id)
            if registration is None:
                raise ValueError("Unknown registered model")
            directory = registration.evidence.get("validation_directory")
            seal = registration.evidence.get("validation_sha256")
            if directory is None and seal is None:
                return None
            if (
                not isinstance(directory, str)
                or not isinstance(seal, str)
                or Path(directory).name != directory
            ):
                raise ValueError("Unsafe or incomplete validation evidence reference")
            validation = open_validation_models(
                self.artifact_root / version_id / directory,
                expected_sha256=seal,
                training_sha256=str(registration.evidence["training_sha256"]),
                refit_bundle_sha256=registration.bundle_sha256,
                protocol=record.protocol,
                model=model,
            )
            if validation.manifest.mode_settings != record.training_config.modes[record.mode]:
                raise ValueError(
                    "Validation fitting policy differs from registered training recipe"
                )
            for fold in validation.manifest.folds:
                validation.load(fold.cutoff_date)
            return validation

    def attach_validation(self, version_id: str, training_directory: Path) -> None:
        """Recover original fold evidence for a legacy registration without changing model bytes."""
        model, record = self.load(version_id)
        if self.validation_models(version_id, model, record) is not None:
            return
        source = training_directory.resolve()
        target = self.artifact_root / version_id
        if file_checksum(source / "training.json") != file_checksum(
            target / "training.json"
        ) or file_checksum(source / "model/bundle.json") != file_checksum(
            target / "model/bundle.json"
        ):
            raise ValueError("Original training evidence must match the registered sealed model")
        directory = "validation-" + new_id()
        preserve_validation_models(
            source,
            target / directory,
            selected_trial=record.selected_trial,
            protocol=record.protocol,
            model=model,
            mode_settings=record.training_config.modes[record.mode],
        )
        with self.sessions.begin() as session:
            session.execute(
                insert(ModelSlot).values(scope=SCOPE, generation=0).on_conflict_do_nothing()
            )
            slot = session.scalar(
                select(ModelSlot).where(ModelSlot.scope == SCOPE).with_for_update()
            )
            registration = session.get(ModelRegistration, version_id)
            assert slot is not None and registration is not None
            if "validation_sha256" in registration.evidence:
                return
            registration.evidence = {
                **registration.evidence,
                "validation_directory": directory,
                "validation_sha256": file_checksum(target / directory / "validation.json"),
            }
            session.add(
                ModelEvent(
                    model_version_id=version_id,
                    previous_model_version_id=slot.active_model_version_id,
                    generation=slot.generation,
                    action="validation_attached",
                    reason="Recovered original sealed chronological validation fits",
                )
            )

    def _record_invalid_candidate(
        self, version_id: str, expected_generation: int, error_kind: str
    ) -> None:
        """Persist failed validation independently; an archived rollback target retains its role."""
        with self.sessions.begin() as session:
            session.execute(
                insert(ModelSlot).values(scope=SCOPE, generation=0).on_conflict_do_nothing()
            )
            slot = session.scalar(
                select(ModelSlot).where(ModelSlot.scope == SCOPE).with_for_update()
            )
            assert slot is not None
            if slot.generation != expected_generation:
                raise ValueError("Stale generation; inspect the active slot before retrying")
            row = session.get(ModelVersion, version_id)
            registration = session.get(ModelRegistration, version_id)
            if row is None or registration is None or row.status == "active":
                return
            reason = "Artifact/schema validation failed: " + error_kind
            if row.status == "candidate":
                row.status = "rejected"
            registration.decision_reason = reason
            registration.approval_required = False
            session.add(
                ModelEvent(
                    model_version_id=version_id,
                    previous_model_version_id=slot.active_model_version_id,
                    generation=slot.generation,
                    action="validation_failed",
                    reason=reason,
                )
            )
