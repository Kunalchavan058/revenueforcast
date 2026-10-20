"""Shared evaluated output adjustments, used by both backtests and forecast serving."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


@dataclass(frozen=True)
class AdjustedPrediction:
    """A prediction plus flags distinguishing clipping from an explicitly known closure."""

    predicted_sales: float | None
    nonnegative_clamped: bool
    closure_adjusted: bool


def apply_output_policy(
    raw_prediction: float | None,
    known_open: bool | None,
    closure_policy: Literal["known_plan_zero", "unadjusted"],
) -> AdjustedPrediction:
    """Apply the established evaluation policy; unknown opening never implies closure."""
    if raw_prediction is not None and not isfinite(raw_prediction):
        raise ValueError("Model produced a non-finite prediction")
    prediction = None if raw_prediction is None else max(0.0, raw_prediction)
    closed = prediction is not None and known_open is False and closure_policy == "known_plan_zero"
    return AdjustedPrediction(
        0.0 if closed else prediction,
        raw_prediction is not None and raw_prediction < 0,
        closed,
    )
