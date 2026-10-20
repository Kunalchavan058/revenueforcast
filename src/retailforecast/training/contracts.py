"""Typed internal training settings and portable model-bundle metadata."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from retailforecast.evaluation.contracts import BacktestConfig, BacktestPlan, Fold
from retailforecast.features.builder import FeatureRow
from retailforecast.features.contracts import SnapshotContext

Algorithm = Literal["xgboost", "lightgbm"]
RequestedAlgorithm = Literal["xgboost", "lightgbm", "auto"]
Mode = Literal["dev", "full"]


class InternalParameters(BaseModel):
    """Bounded search candidate; these controls are never normal UI inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    trees: Annotated[int, Field(ge=1, le=300)]
    max_depth: Annotated[int, Field(ge=1, le=6)]
    learning_rate: Annotated[float, Field(gt=0, le=0.3)]
    min_leaf_rows: Annotated[int, Field(ge=1, le=100)]


class ResourceSettings(BaseModel):
    """One supervised CPU job with explicit process-tree RSS and wall-clock limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    n_jobs: Annotated[int, Field(ge=1, le=2)] = 2
    concurrent_jobs: Literal[1] = 1
    warning_memory_mb: Annotated[int, Field(gt=0)] = 1536
    max_memory_mb: Annotated[int, Field(gt=0)] = 2048
    min_available_memory_mb: Annotated[int, Field(ge=0)] = 256
    poll_seconds: Annotated[float, Field(ge=0.05, le=2)] = 0.25

    @model_validator(mode="after")
    def validate_limits(self) -> ResourceSettings:
        """Require a useful warning threshold before the hard stop."""
        if self.warning_memory_mb >= self.max_memory_mb:
            raise ValueError("Memory warning must be below the hard memory limit")
        return self


class ModeSettings(BaseModel):
    """Explicit deterministic history/origin sampling, never randomized temporal splitting."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    lookback_days: Annotated[int, Field(ge=30)] | None
    origin_stride_days: Annotated[int, Field(ge=1, le=28)]
    max_rows: Annotated[int, Field(ge=48, le=50000)]
    max_trials_per_algorithm: Annotated[int, Field(ge=1, le=3)]
    elapsed_seconds: Annotated[float, Field(gt=0, le=7200)]


class TrainingConfig(BaseModel):
    """Versioned backend search/budget configuration; users choose algorithm and mode."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    seed: int = 42
    resources: ResourceSettings
    modes: dict[Mode, ModeSettings]
    search: tuple[InternalParameters, ...]

    @model_validator(mode="after")
    def validate_search(self) -> TrainingConfig:
        """Reject incomplete modes or a trial cap larger than its declared search space."""
        if set(self.modes) != {"dev", "full"}:
            raise ValueError("Both dev and full modes are required")
        if not self.search or len(self.search) > 3:
            raise ValueError("Declare between one and three internal search candidates")
        if any(mode.max_trials_per_algorithm > len(self.search) for mode in self.modes.values()):
            raise ValueError("Trial cap exceeds the configured internal search candidates")
        return self


class Capabilities(BaseModel):
    """Adapter compatibility advertised independently of concrete native libraries."""

    cpu_only: bool = True
    minimum_horizon: int = 1
    maximum_horizon: int = 48
    supports_unseen_stores: bool = False
    encoding: str = "training-vocabulary one-hot categories; numeric median/missing flags"
    serialization: str = "native model plus validated JSON preprocessing, never pickle"


class TrainingSpan(BaseModel):
    """Actual eligible row coverage and deterministic sampling provenance."""

    origin_start: date
    origin_end: date
    label_start: date
    label_end: date
    rows: int
    origins: int
    origin_stride_days: int
    origin_cap_applied: bool
    store_ids: tuple[int, ...]


class BundleMetadata(BaseModel):
    """Portable fitted-model contract, with checksums and no private absolute paths."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    algorithm: Algorithm
    model_class: str
    parameters: InternalParameters
    native_parameters: dict[str, str | int | float]
    seed: int
    n_jobs: int
    trained_until: date
    training_span: TrainingSpan
    context: SnapshotContext | None
    preprocessing_version: int = 1
    encoded_columns: tuple[str, ...]
    library_versions: dict[str, str]
    checksums: dict[str, str]
    capabilities: Capabilities = Capabilities()


class SavedForecaster(Protocol):
    """Common fitted contract for either CPU tree family."""

    @property
    def trained_until(self) -> date:
        """Return the latest permitted fitting label date."""
        ...

    def predict(self, features: FeatureRow) -> float | None:
        """Predict a valid supported store/horizon using saved preprocessing."""
        ...

    def save(self, path: Path) -> None:
        """Save native parameters and preprocessing in a new verified bundle."""
        ...


class TrainingRequest(BaseModel):
    """Validated coordinator-to-worker request with internal settings frozen at launch."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    algorithm: RequestedAlgorithm
    mode: Mode
    training: TrainingConfig
    backtest: BacktestConfig
    data_config: str
    profile: Literal["synthetic", "rossmann"] = "rossmann"

    validation_plan: BacktestPlan | None = None
    refit_until: date | None = None
    protected_holdout: Fold | None = None
    business_dataset_version_id: str | None = None
    business_source_checksum: str | None = None

    @model_validator(mode="after")
    def validate_retraining_policy(self) -> TrainingRequest:
        """Retain the original validation calendar and protected window for later refits."""
        if self.refit_until is not None:
            if self.validation_plan is None or self.protected_holdout is None:
                raise ValueError(
                    "Later refits require a fixed validation plan and protected holdout"
                )
            if (
                self.protected_holdout != self.validation_plan.folds[-1]
                or self.refit_until <= self.protected_holdout.target_end
            ):
                raise ValueError("Retraining refit must follow the fixed protected holdout")
        return self
