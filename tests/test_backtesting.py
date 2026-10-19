"""Hand-calculated baselines, chronological boundaries and truthful scoring coverage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import sqrt

import pytest
from pydantic import ValidationError

from retailforecast.evaluation.contracts import (
    BacktestConfig,
    Fold,
    Outcome,
    TrainingHistory,
    outcome_index,
)
from retailforecast.evaluation.metrics import calculate_metrics, choose_method, summarize
from retailforecast.evaluation.runner import (
    PredictionPoint,
    generate_predictions,
    horizon_bucket,
    score_predictions,
)
from retailforecast.evaluation.splits import make_plan
from retailforecast.features.builder import FeatureBuilder, FeatureRow
from retailforecast.features.contracts import (
    ForecastKey,
    HistoricalAssumptions,
    PlanSnapshot,
    SalesObservation,
)
from retailforecast.forecasting.baselines import BASELINE_NAMES, BaselineFactory, HistoricalBaseline

ORIGIN = date(2015, 1, 14)


def config(horizon: int = 48, stores: tuple[int, ...] = (1,)) -> BacktestConfig:
    """Return bounded synthetic test settings with no asserted future plans."""
    return BacktestConfig(
        horizon_days=horizon,
        development_folds=2,
        seasonal_weeks=2,
        store_ids=stores,
        assumptions=HistoricalAssumptions(
            explanation="Synthetic test only; known-time dates are explicitly controlled.",
            metadata_known_as_of=date(2015, 1, 1),
        ),
    )


def actual(day: date, sales: float, store: int = 1, delay: int = 0) -> SalesObservation:
    """Create a validated actual without ever accepting a Customers field."""
    return SalesObservation(
        store_id=store, date=day, sales=sales, available_as_of=day + timedelta(days=delay)
    )


def history() -> list[SalesObservation]:
    """January 1..14 sales are day-of-month times ten, enabling hand calculations."""
    return [actual(date(2015, 1, day), float(day * 10)) for day in range(1, 15)]


def fold(horizon: int = 48, name: str = "development_1") -> Fold:
    """Build a single synthetic origin for unit-level forecast/scoring checks."""
    return Fold(
        fold_id=name,
        role="development",
        cutoff_date=ORIGIN,
        target_end=ORIGIN + timedelta(days=horizon),
    )


def point(
    day: int, prediction: float | None, method: str = "probe", name: str = "development_1"
) -> PredictionPoint:
    """Create a pending point; tests must join outcomes to compute errors."""
    return PredictionPoint(
        fold_id=name,
        method=method,
        store_id=1,
        cutoff_date=ORIGIN,
        target_date=ORIGIN + timedelta(days=day),
        horizon_days=day,
        trained_until=ORIGIN,
        raw_prediction=prediction,
        predicted_sales=prediction,
        known_open=None,
    )


def truth(day: int, sales: float, *, delay: int = 0, is_open: bool | None = None) -> Outcome:
    """Make scoring-only observations distinct from model inputs."""
    target = ORIGIN + timedelta(days=day)
    return Outcome(
        store_id=1,
        target_date=target,
        actual_sales=sales,
        available_as_of=target + timedelta(days=delay),
        observed_open=is_open,
    )


@pytest.mark.parametrize("horizon,expected", [(1, (140.0, 80.0, 45.0)), (48, (140.0, 130.0, 95.0))])
def test_baselines_have_hand_calculated_direct_horizon_values(
    horizon: int, expected: tuple[float, ...]
) -> None:
    """h=48 uses Tuesday January 6/13, never intermediate future Tuesdays."""
    builder = FeatureBuilder(history())
    features = builder.build(ForecastKey(store_id=1, cutoff_date=ORIGIN, horizon_days=horizon))
    fitted_history = TrainingHistory(
        cutoff_date=ORIGIN, observations=tuple(builder.history_at_cutoff([1], ORIGIN))
    )
    assert (
        tuple(
            BaselineFactory(name, 2).fit(fitted_history).predict(features)
            for name in BASELINE_NAMES
        )
        == expected
    )


def test_sparse_weekday_fallback_and_cross_store_isolation() -> None:
    """Missing same-weekday history uses declared last-actual fallback within that store."""
    builder = FeatureBuilder([actual(ORIGIN, 140.0), actual(ORIGIN, 999999.0, store=2)])
    fitted_history = TrainingHistory(
        cutoff_date=ORIGIN, observations=tuple(builder.history_at_cutoff([1, 2], ORIGIN))
    )
    row = builder.build(ForecastKey(store_id=1, cutoff_date=ORIGIN, horizon_days=1))
    for name in BASELINE_NAMES:
        baseline = BaselineFactory(name, 2).fit(fitted_history)
        assert baseline.predict(row) == 140.0
        unseen = builder.build(ForecastKey(store_id=999, cutoff_date=ORIGIN, horizon_days=1))
        assert baseline.predict(unseen) is None


@pytest.mark.parametrize("erase", [False, True])
def test_future_mutation_cannot_change_any_baseline_prediction(erase: bool) -> None:
    """Changing/erasing every later sale leaves all 48 direct forecasts unchanged."""
    future = [actual(ORIGIN + timedelta(days=i), 1000.0 + i) for i in range(1, 49)]
    changed = [] if erase else [row.model_copy(update={"sales": 888888.0}) for row in future]
    factories = [BaselineFactory(name, 2) for name in BASELINE_NAMES]
    left = generate_predictions(FeatureBuilder(history() + future), [fold()], config(), factories)
    right = generate_predictions(FeatureBuilder(history() + changed), [fold()], config(), factories)
    assert left == right
    empty = score_predictions(left, {}, scoring_as_of=date(2015, 4, 1))
    assert all(
        row.actual_sales is None and row.signed_error is None and row.status == "missing_actual"
        for row in empty
    )


def test_delayed_actuals_are_not_in_fit_view() -> None:
    """A spy adapter only receives available rows; target outcomes are never passed."""

    @dataclass
    class SpyFactory:
        """Inspect the public future-algorithm interface at its fit boundary."""

        name: str = "spy"
        seen: TrainingHistory | None = None

        def fit(self, rows: TrainingHistory) -> HistoricalBaseline:
            """Capture the actual fitting view and return a valid deterministic baseline."""
            self.seen = rows
            return BaselineFactory("last_known").fit(rows)

    spy = SpyFactory()
    builder = FeatureBuilder(
        [
            actual(ORIGIN, 1000.0, delay=1),
            actual(ORIGIN - timedelta(days=1), 20.0),
            actual(ORIGIN + timedelta(days=1), 9999.0),
        ]
    )
    result = generate_predictions(builder, [fold(1)], config(1), [spy])
    assert spy.seen is not None
    assert [row.sales for row in spy.seen.observations] == [20.0]
    assert result[0].predicted_sales == 20.0
    with pytest.raises(ValidationError, match="unavailable future"):
        TrainingHistory(
            cutoff_date=ORIGIN, observations=(actual(ORIGIN + timedelta(days=1), 99.0),)
        )


def test_zero_sales_metrics_are_hand_calculated_and_missing_truth_has_no_error() -> None:
    """MAE=8/3, RMSE=sqrt(8), RMSPE=.2; missing fourth label reduces coverage only."""
    predictions = [point(1, 2.0), point(2, 8.0), point(3, 24.0), point(4, 5.0)]
    scored = score_predictions(
        predictions,
        outcome_index([truth(1, 0.0), truth(2, 10.0), truth(3, 20.0)]),
        scoring_as_of=date(2015, 2, 1),
    )
    metrics = calculate_metrics(scored)
    assert metrics.mae == pytest.approx(8 / 3)
    assert metrics.rmse == pytest.approx(sqrt(8))
    assert metrics.rmspe == pytest.approx(0.2)
    assert metrics.zero_actuals == metrics.rmspe_zero_excluded == 1
    assert metrics.labeled_actual_sales_sum == metrics.scored_actual_sales_sum == 30.0
    assert metrics.scored_predicted_sales_sum == 34.0
    assert metrics.coverage == 0.75
    assert scored[-1].absolute_error is None
    assert scored[0].squared_percentage_error is None


def test_all_zero_actuals_have_undefined_rmspe_not_perfect_selection_score() -> None:
    """Zero outcomes remain in business metrics but cannot win undefined RMSPE gates."""
    scored = score_predictions(
        [point(1, 2.0), point(2, 2.0)],
        outcome_index([truth(1, 0.0), truth(2, 0.0)]),
        scoring_as_of=date(2015, 2, 1),
    )
    metrics = calculate_metrics(scored)
    assert metrics.mae == metrics.rmse == 2.0
    assert metrics.rmspe is None
    assert metrics.zero_actuals == 2
    assert choose_method(summarize(scored)) is None


def test_common_support_and_delayed_truth_are_explicit() -> None:
    """One unsupported method excludes that key fairly; delayed y stays invisible."""
    points = [point(1, 10.0, "a"), point(2, 20.0, "a"), point(1, None, "b"), point(2, 20.0, "b")]
    scored = score_predictions(
        points, outcome_index([truth(1, 10.0), truth(2, 20.0)]), scoring_as_of=date(2015, 2, 1)
    )
    assert [row.status for row in scored] == [
        "common_mask_excluded",
        "scored",
        "unsupported",
        "scored",
    ]
    aggregate = [item for item in summarize(scored) if item.axis == "aggregate"]
    assert [item.metrics.scored for item in aggregate] == [1, 1]
    assert choose_method(summarize(scored)) is None
    delayed = score_predictions(
        [point(1, 10.0)],
        outcome_index([truth(1, 10.0, delay=2)]),
        scoring_as_of=ORIGIN + timedelta(days=1),
    )[0]
    assert (
        delayed.status == "unavailable_actual"
        and delayed.actual_sales is None
        and delayed.signed_error is None
    )
    with pytest.raises(ValueError, match="different requested"):
        score_predictions(points[:-1], {}, scoring_as_of=date(2015, 2, 1))


def test_observed_closure_never_leaks_into_prediction_or_replaces_actual() -> None:
    """Retrospective Open is a scoring segment; only a known plan enables zero override."""
    unknown = generate_predictions(
        FeatureBuilder(history()), [fold(1)], config(1), [BaselineFactory("last_known")]
    )
    scored = score_predictions(
        unknown, outcome_index([truth(1, 3.0, is_open=False)]), scoring_as_of=date(2015, 2, 1)
    )
    assert scored[0].predicted_sales == 140.0
    assert scored[0].actual_sales == 3.0  # Preserve anomalous closed-store positive Sales.
    plan = PlanSnapshot(
        store_id=1, target_date=ORIGIN + timedelta(days=1), available_as_of=ORIGIN, is_open=False
    )
    closed = generate_predictions(
        FeatureBuilder(history(), plans=[plan]),
        [fold(1)],
        config(1),
        [BaselineFactory("last_known")],
    )
    assert closed[0].predicted_sales == 0.0 and closed[0].raw_prediction == 140.0
    assert closed[0].closure_adjusted
    assert any(
        item.axis == "observed_open" and item.value == "closed" for item in summarize(scored)
    )


def test_plan_reserves_disjoint_development_and_final_windows() -> None:
    """Final 48 days end July 31; development labels stop before that window."""
    settings = config().model_copy(update={"development_folds": 3})
    plan = make_plan(date(2013, 1, 1), date(2015, 7, 31), settings)
    assert [item.cutoff_date for item in plan.folds] == [
        date(2015, 1, 20),
        date(2015, 3, 9),
        date(2015, 4, 26),
        date(2015, 6, 13),
    ]
    assert plan.folds[-1].role == "final"
    for left, right in zip(plan.folds[:-1], plan.folds[1:], strict=True):
        assert left.target_end == right.cutoff_date
    with pytest.raises(ValueError, match="Insufficient"):
        make_plan(date(2015, 7, 30), date(2015, 7, 31), settings)


@pytest.mark.parametrize(
    "horizon,bucket",
    [
        (1, "1-7"),
        (7, "1-7"),
        (8, "8-14"),
        (14, "8-14"),
        (15, "15-28"),
        (28, "15-28"),
        (29, "29-48"),
        (48, "29-48"),
    ],
)
def test_horizon_bucket_boundaries(horizon: int, bucket: str) -> None:
    """Keep every requested horizon in the specified inclusive reporting segment."""
    assert horizon_bucket(horizon) == bucket


def test_selection_rejects_final_results_and_metrics_report_all_segments() -> None:
    """Method selection cannot inspect holdout metrics through its public API."""
    scored = score_predictions(
        [point(1, 10.0, name="final")],
        outcome_index([truth(1, 10.0)]),
        scoring_as_of=date(2015, 2, 1),
    )
    summaries = summarize(scored)
    assert {item.axis for item in summaries} == {
        "aggregate",
        "fold",
        "store",
        "horizon",
        "observed_open",
        "week",
        "month",
    }
    with pytest.raises(ValueError, match="Final holdout"):
        choose_method(summaries)


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_invalid_algorithm_prediction_fails_instead_of_being_scored(value: float) -> None:
    """A generic adapter cannot publish nonfinite predictions as successful results."""

    @dataclass
    class FixedModel:
        """Minimal alternate algorithm demonstrating runner independence."""

        trained_until: date = ORIGIN

        def predict(self, features: FeatureRow) -> float:
            """Return the controlled invalid value for this boundary test."""
            return value

    @dataclass
    class FixedFactory:
        """Fit an alternate algorithm without any baseline implementation dependency."""

        name: str = "invalid_probe"

        def fit(self, rows: TrainingHistory) -> FixedModel:
            """Return controlled state without reading labels beyond its fit argument."""
            return FixedModel()

    with pytest.raises(ValueError, match="non-finite"):
        generate_predictions(FeatureBuilder(history()), [fold(1)], config(1), [FixedFactory()])


def test_runner_rejects_future_trained_model_and_clamps_negative_prediction() -> None:
    """Compatibility and nonnegative output policy apply to every algorithm adapter."""

    @dataclass
    class FixedModel:
        """Minimal finite fixed-output model."""

        trained_until: date

        def predict(self, features: FeatureRow) -> float:
            """Return a negative estimate so runner policy can be verified."""
            return -5.0

    @dataclass
    class FixedFactory:
        """Supply controlled fitting provenance to the generic runner."""

        trained_until: date
        name: str = "fixed_probe"

        def fit(self, rows: TrainingHistory) -> FixedModel:
            """Expose only a declared training date and fixed prediction behavior."""
            return FixedModel(self.trained_until)

    with pytest.raises(ValueError, match="trained_until"):
        generate_predictions(
            FeatureBuilder(history()),
            [fold(1)],
            config(1),
            [FixedFactory(ORIGIN + timedelta(days=1))],
        )
    row = generate_predictions(
        FeatureBuilder(history()), [fold(1)], config(1), [FixedFactory(ORIGIN)]
    )[0]
    assert row.raw_prediction == -5.0 and row.predicted_sales == 0.0 and row.nonnegative_clamped
