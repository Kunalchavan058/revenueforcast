"""Shared native CPU tree adapter and validated portable model bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

import lightgbm as lgb
import numpy as np
import xgboost as xgb

from retailforecast.data.pipeline_config import canonical_json
from retailforecast.data.validation import file_checksum
from retailforecast.features.builder import FeatureRow
from retailforecast.features.preprocessing import FittedPreprocessor
from retailforecast.training.contracts import (
    Algorithm,
    BundleMetadata,
    Capabilities,
    InternalParameters,
)
from retailforecast.training.dataset import PreparedData, encode_row, encoded_columns


class AlgorithmAdapter(Protocol):
    """Fit, predict through returned state, save/load and advertised compatibility."""

    algorithm: Algorithm

    def capabilities(self) -> Capabilities:
        """Describe supported horizons, CPU use, category encoding and model format."""
        ...

    def fit(
        self, data: PreparedData, parameters: InternalParameters, *, seed: int, n_jobs: int
    ) -> TreeModel:
        """Fit a native estimator on a prevalidated fold-local matrix."""
        ...

    def load(self, path: Path) -> TreeModel:
        """Load saved parameters and training-fitted preprocessing without fitting."""
        ...


@dataclass
class TreeModel:
    """Fitted native booster and its immutable preprocessing/order/coverage contract."""

    booster: xgb.Booster | lgb.Booster
    preprocessing: FittedPreprocessor
    metadata: BundleMetadata

    @property
    def trained_until(self) -> date:
        """Return the shared cutoff guard for evaluation and later serving."""
        return self.metadata.trained_until

    def predict(self, features: FeatureRow) -> float:
        """Return a finite raw estimate; the shared runner applies closure/nonnegative policy."""
        if features.key.store_id not in self.metadata.training_span.store_ids:
            raise ValueError("Model does not advertise coverage for this unseen store")
        if features.context != self.metadata.context:
            raise ValueError("Feature dataset/availability context differs from the saved model")
        matrix = encode_row(features, self.preprocessing).reshape(1, -1)
        if isinstance(self.booster, xgb.Booster):
            prediction = self.booster.predict(xgb.DMatrix(matrix, nthread=self.metadata.n_jobs))
        else:
            prediction = np.asarray(self.booster.predict(matrix, num_threads=self.metadata.n_jobs))
        result = float(prediction[0])
        if not np.isfinite(result):
            raise ValueError("Native model produced a nonfinite estimate")
        return result

    def save(self, path: Path) -> None:
        """Write a new native model/JSON preprocessing bundle, manifest last; never overwrite."""
        if path.exists():
            raise ValueError("Model bundle already exists")
        path.mkdir(parents=True)
        filename = "model.json" if self.metadata.algorithm == "xgboost" else "model.txt"
        self.booster.save_model(str(path / filename))
        self.preprocessing.save(path / "preprocessing.json")
        metadata = self.metadata.model_copy(
            update={
                "checksums": {
                    name: file_checksum(path / name) for name in (filename, "preprocessing.json")
                }
            }
        )
        (path / "bundle.json").write_bytes(canonical_json(metadata.model_dump(mode="json")))


@dataclass(frozen=True)
class NativeTreeAdapter:
    """Common implementation for histogram XGBoost and deterministic CPU LightGBM."""

    algorithm: Algorithm

    def __post_init__(self) -> None:
        """Reject unknown families even for runtime callers without static typing."""
        if self.algorithm not in ("xgboost", "lightgbm"):
            raise ValueError("Unsupported tree algorithm")

    def capabilities(self) -> Capabilities:
        """Return the same explicit CPU/horizon/serialization contract for both families."""
        return Capabilities()

    def fit(
        self, data: PreparedData, parameters: InternalParameters, *, seed: int, n_jobs: int
    ) -> TreeModel:
        """Fit only supplied training rows; never use a validation/final label for fitting."""
        if not 1 <= n_jobs <= 2:
            raise ValueError("CPU threads must be 1 or 2")
        columns = encoded_columns(data.preprocessing)
        if (
            data.matrix.ndim != 2
            or data.matrix.shape != (len(data.labels), len(columns))
            or len(data.labels) == 0
        ):
            raise ValueError("Training matrix shape disagrees with preprocessing or labels")
        if (
            not np.isfinite(data.matrix).all()
            or not np.isfinite(data.labels).all()
            or (data.labels < 0).any()
        ):
            raise ValueError("Training matrix/labels must be finite; targets must be nonnegative")
        if data.span.label_end > data.preprocessing.training_label_end:
            raise ValueError("Training span exceeds preprocessing fold end")
        params: dict[str, str | int | float]
        booster: xgb.Booster | lgb.Booster
        if self.algorithm == "xgboost":
            params = {
                "objective": "reg:squarederror",
                "tree_method": "hist",
                "device": "cpu",
                "max_depth": parameters.max_depth,
                "eta": parameters.learning_rate,
                "min_child_weight": parameters.min_leaf_rows,
                "max_bin": 63,
                "nthread": n_jobs,
                "seed": seed,
                "subsample": 1.0,
                "colsample_bytree": 1.0,
            }
            booster = xgb.train(
                params,
                xgb.DMatrix(data.matrix, label=data.labels, nthread=n_jobs),
                num_boost_round=parameters.trees,
            )
            model_class = "xgboost.core.Booster"
        else:
            params = {
                "objective": "regression",
                "learning_rate": parameters.learning_rate,
                "max_depth": parameters.max_depth,
                "num_leaves": min(31, 2**parameters.max_depth - 1),
                "min_data_in_leaf": parameters.min_leaf_rows,
                "max_bin": 63,
                "num_threads": n_jobs,
                "seed": seed,
                "deterministic": "true",
                "force_col_wise": "true",
                "verbosity": -1,
                "device_type": "cpu",
            }
            booster = lgb.train(
                params,
                lgb.Dataset(data.matrix, label=data.labels),
                num_boost_round=parameters.trees,
            )
            model_class = "lightgbm.basic.Booster"
        metadata = BundleMetadata(
            algorithm=self.algorithm,
            model_class=model_class,
            parameters=parameters,
            native_parameters=params,
            seed=seed,
            n_jobs=n_jobs,
            trained_until=data.preprocessing.training_label_end,
            training_span=data.span,
            context=data.preprocessing.training_context,
            encoded_columns=columns,
            library_versions=library_versions(),
            checksums={},
            capabilities=self.capabilities(),
        )
        return TreeModel(booster, data.preprocessing, metadata)

    def load(self, path: Path) -> TreeModel:
        """Validate checksums, encoding, coverage and pinned library versions before use."""
        metadata = BundleMetadata.model_validate_json((path / "bundle.json").read_bytes())
        if metadata.algorithm != self.algorithm or metadata.library_versions != library_versions():
            raise ValueError("Model algorithm or native library versions are incompatible")
        filename = "model.json" if self.algorithm == "xgboost" else "model.txt"
        if set(metadata.checksums) != {filename, "preprocessing.json"}:
            raise ValueError("Incomplete or unsafe model bundle file manifest")
        for name, expected in metadata.checksums.items():
            if file_checksum(path / name) != expected:
                raise ValueError(f"Model bundle checksum mismatch: {name}")
        preprocessing = FittedPreprocessor.load(path / "preprocessing.json")
        if (
            metadata.encoded_columns != encoded_columns(preprocessing)
            or metadata.trained_until != preprocessing.training_label_end
        ):
            raise ValueError("Saved model feature ordering/cutoff differs from preprocessing")
        if metadata.context != preprocessing.training_context:
            raise ValueError("Saved model and preprocessing dataset contexts differ")
        booster: xgb.Booster | lgb.Booster
        if self.algorithm == "xgboost":
            booster = xgb.Booster(params={"nthread": metadata.n_jobs})
            booster.load_model(path / filename)
        else:
            booster = lgb.Booster(model_file=str(path / filename))
        return TreeModel(booster, preprocessing, metadata)


def library_versions() -> dict[str, str]:
    """Pin native model compatibility and numeric encoding to the installed lock."""
    return {"xgboost": xgb.__version__, "lightgbm": lgb.__version__, "numpy": np.__version__}
