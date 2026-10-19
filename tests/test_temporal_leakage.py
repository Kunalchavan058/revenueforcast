"""Hand-checkable direct-horizon and as-of availability regression tests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from retailforecast.features.builder import FeatureBuilder, forecast_keys
from retailforecast.features.contracts import (
    ForecastKey,
    PlanSnapshot,
    SalesObservation,
    StoreSnapshot,
)
from retailforecast.features.preprocessing import FittedPreprocessor
from retailforecast.features.registry import FEATURE_NAMES, PREDICTORS, render_registry

CUTOFF = date(2015, 7, 31)


def key(horizon: int = 7, store: int = 1, cutoff: date = CUTOFF) -> ForecastKey:
    """Build one explicit request in the worked July/August example."""
    return ForecastKey(store_id=store, cutoff_date=cutoff, horizon_days=horizon)


def observed(day: date, value: float, store: int = 1, delay: int = 0) -> SalesObservation:
    """Create synthetic actuals with controllable availability delays."""
    return SalesObservation(
        store_id=store, date=day, sales=value, available_as_of=day + timedelta(days=delay)
    )


def history() -> list[SalesObservation]:
    """July 25..31 has values 10,0,30,40,50,60,70; Sunday zero is observed."""
    return [
        observed(date(2015, 7, 25) + timedelta(days=i), value)
        for i, value in enumerate((10.0, 0.0, 30.0, 40.0, 50.0, 60.0, 70.0))
    ]


def fitted_state() -> FittedPreprocessor:
    """Fit preprocessing only, on synthetic labels available by July 30."""
    builder = FeatureBuilder(history())
    examples = builder.iter_labeled(
        [key(1, cutoff=date(2015, 7, 29))], training_label_end=date(2015, 7, 30)
    )
    return FittedPreprocessor.fit(examples, training_label_end=date(2015, 7, 30))


@pytest.mark.parametrize("horizon", [1, 7, 48])
@pytest.mark.parametrize("erase_future", [False, True])
def test_future_sales_mutation_cannot_change_features_or_fixed_predictions(
    horizon: int, erase_future: bool
) -> None:
    """Modify/erase every later actual; shared features and a fixed probe remain identical."""
    future = [observed(CUTOFF + timedelta(days=i), float(i * 100)) for i in range(1, 49)]
    changed = [] if erase_future else [row.model_copy(update={"sales": 999999.0}) for row in future]
    plan = PlanSnapshot(
        store_id=1, target_date=key(horizon).target_date, available_as_of=CUTOFF, promotion=True
    )
    left = FeatureBuilder(history() + future, plans=[plan]).build(key(horizon))
    right = FeatureBuilder(history() + changed, plans=[plan]).build(key(horizon))
    assert left.values == right.values
    preprocessor = fitted_state()
    before, after = preprocessor.transform(left), preprocessor.transform(right)
    assert before == after
    # A fixed arithmetic prediction probe checks the serving matrix path without
    # training an estimator or presenting these values as application forecasts.
    weights = tuple((i + 1) / 100 for i in range(len(before)))
    assert sum(a * b for a, b in zip(before, weights, strict=True)) == sum(
        a * b for a, b in zip(after, weights, strict=True)
    )


def test_calendar_lags_and_inclusive_windows_are_hand_checkable() -> None:
    """July 30 is lag 1; July 25..31 mean includes the observed Sunday zero."""
    values = FeatureBuilder(history()).build(key()).values
    assert values["sales_at_cutoff"] == 70.0
    assert values["sales_lag_1_from_cutoff"] == 60.0
    assert values["sales_lag_7_from_cutoff"] is None
    assert values["sales_mean_7_through_cutoff"] == pytest.approx(260 / 7)
    assert values["sales_count_7_through_cutoff"] == 7.0
    assert values["days_since_last_sales"] == 0.0


def test_missing_date_does_not_shift_rows_or_fill_actual_zero() -> None:
    """Removing July 30 leaves lag 1 missing and reduces window coverage."""
    rows = [row for row in history() if row.date != date(2015, 7, 30)]
    values = FeatureBuilder(rows).build(key()).values
    assert values["sales_lag_1_from_cutoff"] is None
    assert values["sales_mean_7_through_cutoff"] == pytest.approx(200 / 6)
    assert values["sales_count_7_through_cutoff"] == 6.0


def test_cross_store_isolation_and_unsorted_input() -> None:
    """Another store's huge nearby observations cannot contaminate any statistic."""
    other = [observed(row.date, 900000.0, store=2) for row in history()]
    builder = FeatureBuilder(reversed(history() + other))
    assert builder.build(key()).values == FeatureBuilder(history()).build(key()).values
    assert builder.build(key(store=2)).values["sales_mean_7_through_cutoff"] == 900000.0


def test_delayed_labels_and_history_age() -> None:
    """A past business date is not sufficient when its actual is reported later."""
    builder = FeatureBuilder(
        [observed(CUTOFF, 70.0, delay=1), observed(CUTOFF - timedelta(days=2), 50.0)]
    )
    values = builder.build(key()).values
    assert values["sales_at_cutoff"] is None
    assert values["days_since_last_sales"] == 2.0
    assert values["sales_mean_7_through_cutoff"] == 50.0


def test_plan_asof_revision_and_explicit_unknown_replacement() -> None:
    """Ignore late revisions; an eligible None revision clears an older known plan."""
    old = PlanSnapshot(
        store_id=1,
        target_date=key().target_date,
        available_as_of=date(2015, 7, 1),
        promotion=True,
        is_open=True,
    )
    late = old.model_copy(update={"available_as_of": date(2015, 8, 1), "promotion": False})
    builder = FeatureBuilder(history(), plans=[old, late])
    assert builder.build(key()).values["target_promo"] == 1.0
    unknown = PlanSnapshot(store_id=1, target_date=key().target_date, available_as_of=CUTOFF)
    assert (
        FeatureBuilder(history(), plans=[old, unknown, late]).build(key()).values["target_promo"]
        is None
    )


def test_sunday_open_is_unknown_unless_plan_explicit() -> None:
    """Calendar Sunday alone does not establish closure; known flag stays distinct."""
    sunday = key(2)
    assert sunday.target_date == date(2015, 8, 2)
    assert FeatureBuilder(history()).build(sunday).values["target_open"] is None
    plan = PlanSnapshot(
        store_id=1, target_date=sunday.target_date, available_as_of=CUTOFF, is_open=False
    )
    values = FeatureBuilder(history(), plans=[plan]).build(sunday).values
    assert values["target_open"] == 0.0
    assert values["target_day_of_week"] == 7.0


def test_metadata_known_time_and_planned_promo2() -> None:
    """Metadata revisions are as-of; complete known Promo2 schedule expands by target."""
    store = StoreSnapshot(
        store_id=1,
        available_as_of=CUTOFF,
        store_type="a",
        competition_open_since_month=6,
        competition_open_since_year=2015,
        promo2=True,
        promo2_since_year=2015,
        promo2_since_week=20,
        promo_interval="Feb,May,Aug,Nov",
    )
    late = store.model_copy(update={"available_as_of": date(2015, 8, 1), "store_type": "d"})
    values = FeatureBuilder(history(), stores=[store, late]).build(key()).values
    assert values["store_type"] == "a"
    assert values["competition_months_at_cutoff"] == 1.0
    assert values["promo2_active_target"] == 1.0
    assert FeatureBuilder(history(), stores=[late]).build(key()).values["store_type"] is None
    missing = store.model_copy(update={"promo_interval": None})
    assert (
        FeatureBuilder(history(), stores=[missing]).build(key()).values["promo2_active_target"]
        is None
    )


@pytest.mark.parametrize("horizon", [1, 48])
def test_target_alignment_and_training_fold_end(horizon: int) -> None:
    """Labels are store-specific t+h and cannot exceed fold label end."""
    request = key(horizon)
    target = observed(request.target_date, 123.0)
    builder = FeatureBuilder(history() + [target, observed(request.target_date, 888.0, store=2)])
    assert (
        list(
            builder.iter_labeled(
                [request], training_label_end=request.target_date - timedelta(days=1)
            )
        )
        == []
    )
    example = list(builder.iter_labeled([request], training_label_end=request.target_date))[0]
    assert example.target_sales == 123.0
    assert example.features.key.target_date == CUTOFF + timedelta(days=horizon)
    assert example.features.values == builder.build(request).values
    assert "target_sales" not in example.features.values


def test_missing_or_delayed_target_is_not_zero_label() -> None:
    """Missing actuals and unavailable target reports are omitted, never fabricated."""
    request = key(1)
    assert (
        list(
            FeatureBuilder(history()).iter_labeled(
                [request], training_label_end=request.target_date
            )
        )
        == []
    )
    delayed = observed(request.target_date, 42.0, delay=1)
    builder = FeatureBuilder(history() + [delayed])
    assert list(builder.iter_labeled([request], training_label_end=request.target_date)) == []


def test_unseen_store_has_transparent_fitted_fallback(tmp_path: Path) -> None:
    """Persist/reload training medians/order/categories; cold-start store remains explicit."""
    state = fitted_state()
    row = FeatureBuilder([]).build(key(store=999))
    assert row.values["sales_mean_7_through_cutoff"] is None
    assert row.values["sales_count_7_through_cutoff"] == 0.0
    matrix = state.transform(row)
    assert matrix[state.output_columns.index("store_id")] == -1.0
    assert matrix[state.output_columns.index("sales_mean_7_through_cutoff__missing")] == 1.0
    assert matrix[state.output_columns.index("store_type")] == -2.0
    path = tmp_path / "preprocessing.json"
    state.save(path)
    assert FittedPreprocessor.load(path).transform(row) == matrix
    assert state.model_dump() == FittedPreprocessor.load(path).model_dump()


def test_fit_does_not_learn_validation_values_or_vocabulary() -> None:
    """A held-out category and sales do not change saved training state during transform."""
    state = fitted_state()
    before = state.model_dump_json()
    row = FeatureBuilder(
        [observed(CUTOFF, 99999.0)],
        stores=[StoreSnapshot(store_id=1, available_as_of=CUTOFF, store_type="new-category")],
    ).build(key())
    transformed = state.transform(row)
    assert transformed[state.output_columns.index("store_type")] == -1.0
    assert state.model_dump_json() == before
    training = list(
        FeatureBuilder(history()).iter_labeled(
            [key(1, cutoff=date(2015, 7, 29))], training_label_end=date(2015, 7, 30)
        )
    )
    assert len(state.transform_training(training[0])) == len(state.output_columns)
    with pytest.raises(ValueError, match="beyond forecast cutoff"):
        state.transform(training[0].features)
    with pytest.raises(ValueError, match="beyond training_label_end"):
        FittedPreprocessor.fit(training, training_label_end=date(2015, 7, 29))


def test_schema_drift_or_extra_customer_fields_fail() -> None:
    """Customer values cannot be smuggled into typed inputs or saved schemas."""
    with pytest.raises(ValidationError, match="Extra inputs"):
        SalesObservation.model_validate(
            {
                "store_id": 1,
                "date": CUTOFF,
                "sales": 1.0,
                "available_as_of": CUTOFF,
                "customers": 100,
            }
        )
    state = fitted_state().model_copy(update={"registry_sha256": "wrong"})
    with pytest.raises(ValueError, match="incompatible"):
        state.transform(FeatureBuilder(history()).build(key()))
    assert not any("customer" in item.name.lower() for item in PREDICTORS)
    assert tuple(FeatureBuilder(history()).build(key()).values) == FEATURE_NAMES


@pytest.mark.parametrize("horizon", [0, 49])
def test_invalid_horizon_rejected(horizon: int) -> None:
    """Reject requests outside the agreed direct-horizon contract."""
    with pytest.raises(ValidationError):
        key(horizon)


def test_duplicate_actuals_and_ambiguous_plans_rejected() -> None:
    """Input order cannot determine which conflicting row becomes a feature."""
    with pytest.raises(ValueError, match="Duplicate actual"):
        FeatureBuilder(history() + history())
    plan = PlanSnapshot(store_id=1, target_date=key().target_date, available_as_of=CUTOFF)
    with pytest.raises(ValueError, match="Duplicate plan"):
        FeatureBuilder([], plans=[plan, plan])


def test_default_horizon_expansion_and_leap_calendar() -> None:
    """One cutoff expands to exactly 48 independent rows; leap day stays a business date."""
    keys = list(forecast_keys([1], [CUTOFF]))
    assert len(keys) == 48
    assert keys[-1].target_date == date(2015, 9, 17)
    row = FeatureBuilder([]).build(key(1, cutoff=date(2016, 2, 28)))
    assert row.key.target_date == date(2016, 2, 29)
    assert row.values["target_day_of_year"] == 60.0


def test_generated_registry_reference_matches_code() -> None:
    """Prevent a manually edited explanation from drifting away from the registry."""
    path = Path(__file__).resolve().parents[1] / "docs/FEATURE_REGISTRY.md"
    assert path.read_text(encoding="utf-8") == render_registry()


def test_empty_history_uses_training_missing_policy_and_fit_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cold-start training has explicit zero imputation and indicators, not zero actuals."""
    from retailforecast.features import preprocessing
    from retailforecast.features.builder import LabeledExample

    example = LabeledExample(FeatureBuilder([]).build(key()), 12.0, key().target_date)
    state = FittedPreprocessor.fit([example], training_label_end=key().target_date)
    matrix = state.transform_training(example)
    assert matrix[state.output_columns.index("sales_at_cutoff")] == 0.0
    assert matrix[state.output_columns.index("sales_at_cutoff__missing")] == 1.0
    assert example.features.values["sales_at_cutoff"] is None
    monkeypatch.setattr(preprocessing, "MAX_FIT_ROWS", 1)
    with pytest.raises(ValueError, match="MAX_FIT_ROWS"):
        FittedPreprocessor.fit([example, example], training_label_end=key().target_date)


def test_competition_future_start_and_promo2_week_boundaries() -> None:
    """Month precision is explicit; ISO week start and inactive months remain distinct."""
    store = StoreSnapshot(
        store_id=1,
        available_as_of=CUTOFF,
        competition_open_since_year=2015,
        competition_open_since_month=8,
        promo2=True,
        promo2_since_year=2015,
        promo2_since_week=33,
        promo_interval="Aug",
    )
    builder = FeatureBuilder([], stores=[store])
    assert builder.build(key(7)).values["competition_months_at_cutoff"] is None
    assert builder.build(key(7)).values["promo2_active_target"] == 0.0
    assert builder.build(key(10)).values["promo2_active_target"] == 1.0
    assert builder.build(key(48)).values["promo2_active_target"] == 0.0


def test_label_availability_and_numeric_integrity_are_validated() -> None:
    """Standalone training examples cannot claim future labels known prematurely."""
    from retailforecast.features.builder import LabeledExample

    with pytest.raises(ValueError, match="before target date"):
        LabeledExample(FeatureBuilder([]).build(key()), 1.0, CUTOFF)
    with pytest.raises(ValueError, match="finite and nonnegative"):
        LabeledExample(FeatureBuilder([]).build(key()), float("nan"), key().target_date)


def test_fit_preserves_one_dataset_availability_context() -> None:
    """Training artifacts retain assumptions; mixed snapshot fits require an explicit redesign."""
    from retailforecast.features.builder import LabeledExample
    from retailforecast.features.contracts import HistoricalAssumptions, SnapshotContext

    context = SnapshotContext(
        dataset_fingerprint="synthetic-example",
        assumptions=HistoricalAssumptions(
            explanation="Synthetic test assumption; metadata asserted known for this test.",
            metadata_known_as_of=CUTOFF,
        ),
    )
    row = FeatureBuilder([], context=context).build(key())
    example = LabeledExample(row, 1.0, key().target_date)
    state = FittedPreprocessor.fit([example], training_label_end=key().target_date)
    assert state.training_context == context
    other = LabeledExample(FeatureBuilder([]).build(key()), 1.0, key().target_date)
    with pytest.raises(ValueError, match="share one dataset"):
        FittedPreprocessor.fit([example, other], training_label_end=key().target_date)
