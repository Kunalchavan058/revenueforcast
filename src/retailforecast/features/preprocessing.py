"""Training-only fitted imputation/category mapping, saved as portable typed JSON."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from statistics import median

from pydantic import BaseModel, ConfigDict

from retailforecast.data.pipeline_config import canonical_json
from retailforecast.features.builder import FeatureRow, LabeledExample
from retailforecast.features.contracts import SnapshotContext
from retailforecast.features.registry import PREDICTORS, registry_fingerprint

EMPTY_NUMERIC_DEFAULT = 0.0
MISSING_CATEGORY_CODE = -2.0
UNKNOWN_CATEGORY_CODE = -1.0
MAX_FIT_ROWS = 50_000


class FittedPreprocessor(BaseModel):
    """Frozen training-fold state to persist alongside a future estimator.

    Ordinal category codes have no quantitative meaning. Future estimators must
    explicitly support this encoding or provide a separately versioned adapter.
    No statistic or vocabulary is learned by transform().
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: int = 1
    registry_sha256: str
    training_label_end: date
    training_context: SnapshotContext | None = None
    numeric_fill: dict[str, float]
    categories: dict[str, tuple[str, ...]]
    output_columns: tuple[str, ...]

    @classmethod
    def fit(
        cls, examples: Iterable[LabeledExample], *, training_label_end: date
    ) -> FittedPreprocessor:
        """Fit only caller-selected training examples, rejecting post-fold labels."""
        numeric: dict[str, list[float]] = {
            item.name: [] for item in PREDICTORS if item.data_type == "numeric"
        }
        categorical: dict[str, set[str]] = {
            item.name: set() for item in PREDICTORS if item.data_type == "categorical"
        }
        count = 0
        context: SnapshotContext | None = None
        for example in examples:
            if (
                example.features.key.target_date > training_label_end
                or example.label_available_as_of > training_label_end
            ):
                raise ValueError("Preprocessing fit cannot use labels beyond training_label_end")
            validate_row(example.features)
            if count == 0:
                context = example.features.context
            elif context != example.features.context:
                raise ValueError("Fit examples must share one dataset and availability context")
            count += 1
            if count > MAX_FIT_ROWS:
                raise ValueError(
                    "Preprocessing fit exceeds MAX_FIT_ROWS; select a bounded training fold"
                )
            for name, numbers in numeric.items():
                value = example.features.values[name]
                if value is not None:
                    if not isinstance(value, float):
                        raise ValueError(f"Numeric feature {name} must be float or None")
                    numbers.append(value)
            for name, vocabulary in categorical.items():
                value = example.features.values[name]
                if value is not None:
                    if not isinstance(value, str):
                        raise ValueError(f"Categorical feature {name} must be string or None")
                    vocabulary.add(value)
        if count == 0:
            raise ValueError("Cannot fit preprocessing without eligible labeled training rows")
        return cls(
            registry_sha256=registry_fingerprint(),
            training_context=context,
            training_label_end=training_label_end,
            numeric_fill={
                name: float(median(values)) if values else EMPTY_NUMERIC_DEFAULT
                for name, values in numeric.items()
            },
            categories={name: tuple(sorted(values)) for name, values in categorical.items()},
            output_columns=output_columns(),
        )

    def transform(self, row: FeatureRow) -> tuple[float, ...]:
        """Apply saved feature order and missing policy; never fit on serving/holdout rows."""
        self.validate_state()
        validate_row(row)
        if row.key.cutoff_date < self.training_label_end:
            raise ValueError("Preprocessor was fitted on labels beyond forecast cutoff")
        return self._transform_values(row)

    def _transform_values(self, row: FeatureRow) -> tuple[float, ...]:
        result: list[float] = []
        for item in PREDICTORS:
            value = row.values[item.name]
            if item.data_type == "numeric":
                if value is not None and not isinstance(value, float):
                    raise ValueError(f"Invalid numeric feature {item.name}")
                result.extend(
                    (self.numeric_fill[item.name] if value is None else value, float(value is None))
                )
            else:
                if value is not None and not isinstance(value, str):
                    raise ValueError(f"Invalid categorical feature {item.name}")
                vocabulary = self.categories[item.name]
                code = MISSING_CATEGORY_CODE if value is None else UNKNOWN_CATEGORY_CODE
                if value is not None and value in vocabulary:
                    code = float(vocabulary.index(value))
                result.append(code)
        return tuple(result)

    def transform_training(self, example: LabeledExample) -> tuple[float, ...]:
        """Transform training rows while retaining the frozen fold fit boundary.

        Training inputs naturally predate the fold end; inference's fitted-through
        guard does not apply within that same fold. No fitting happens here.
        """
        if (
            example.features.key.target_date > self.training_label_end
            or example.label_available_as_of > self.training_label_end
        ):
            raise ValueError("Training example exceeds fitted fold boundary")
        self.validate_state()
        validate_row(example.features)
        return self._transform_values(example.features)

    def validate_state(self) -> None:
        """Reject incompatible versions, changed registry/order and malformed saved state."""
        if (
            self.schema_version != 1
            or self.registry_sha256 != registry_fingerprint()
            or self.output_columns != output_columns()
        ):
            raise ValueError("Preprocessing schema/registry/order is incompatible")
        numeric = {item.name for item in PREDICTORS if item.data_type == "numeric"}
        categorical = {item.name for item in PREDICTORS if item.data_type == "categorical"}
        if set(self.numeric_fill) != numeric or set(self.categories) != categorical:
            raise ValueError("Incomplete preprocessing state")
        if any(not math.isfinite(value) for value in self.numeric_fill.values()):
            raise ValueError("Non-finite imputation state")
        if any(tuple(sorted(set(values))) != values for values in self.categories.values()):
            raise ValueError("Category vocabulary must be unique and sorted")

    def save(self, path: Path) -> None:
        """Persist JSON within a caller-owned local artifact directory, never pickle."""
        self.validate_state()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical_json(self.model_dump(mode="json")))

    @classmethod
    def load(cls, path: Path) -> FittedPreprocessor:
        """Load and validate compatibility before using persisted preprocessing."""
        state = cls.model_validate_json(path.read_bytes())
        state.validate_state()
        return state


def output_columns() -> tuple[str, ...]:
    """Derive output order solely from registry; numeric missing flags follow values."""
    columns: list[str] = []
    for item in PREDICTORS:
        columns.append(item.name)
        if item.data_type == "numeric":
            columns.append(f"{item.name}__missing")
    return tuple(columns)


def validate_row(row: FeatureRow) -> None:
    """Reject extra/omitted fields and non-finite numbers at preprocessing boundary."""
    if tuple(row.values) != tuple(item.name for item in PREDICTORS):
        raise ValueError("Feature ordering/schema differs from registry")
    if any(isinstance(value, float) and not math.isfinite(value) for value in row.values.values()):
        raise ValueError("Feature values must be finite")
