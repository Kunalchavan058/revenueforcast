# Cutoff-safe direct multi-horizon features

## In plain English

A forecast issued on July 31 cannot learn from August 1 sales, even when predicting August 7. Each store, cutoff and horizon gets a separate row. Calendar facts are computable; opening and promotion plans need explicit evidence that they were known at cutoff. Unknown plans remain missing. A missing value in a model matrix may be imputed, but it never becomes a claimed business fact.

[FEATURE_REGISTRY.md](FEATURE_REGISTRY.md) is generated from `src/retailforecast/features/registry.py`, the single source of feature descriptions, order, types, lineage, missing policies and availability categories. Do not hand-edit that reference. [Decision 0007](decisions/0007-asof-direct-features.md) records the trade-offs.

## Implemented contracts

- `ForecastKey(store_id, cutoff_date, horizon_days)` accepts horizons 1..48; target is always cutoff plus horizon.
- `SalesObservation` has business date and `available_as_of`. Both must be at/before cutoff for history. Availability cannot precede its business date. Duplicate store/date actuals fail; corrections require selecting a new dataset version.
- `StoreSnapshot` and `PlanSnapshot` are full replacements. Select the latest snapshot known at/before cutoff, never the nearest snapshot after it. A newer eligible plan with a missing field clears that field; it does not inherit an older claim. Equal-time revisions fail as ambiguous. Plan joins include store AND target date.
- `FeatureBuilder.build` is the only predictor calculation. `iter_features` serves inference and backtesting inputs; `iter_labeled` calls that same builder and attaches y separately. `forecast_keys` lazily expands default horizons 1 through 48. Phase 7 supplies offline baseline scoring and Phase 8 adds CPU model training; no forecast endpoint exists yet.
- `iter_labeled(..., training_label_end=...)` includes only actual target labels with target date AND availability at/before fold end. Missing/unavailable targets are omitted, not filled with zero. A cutoff before fold end alone does not make a 48-day target eligible.
- `SnapshotContext` carries the verified DVC dataset fingerprint and declared assumptions with each adapted row. Preprocessing retains the training context and rejects mixed contexts. Hand-authored test inputs may omit context; a future production model bundle must require it and also record code revision, registry hash and estimator configuration.

All dates are daily business dates, not UTC import timestamps. Raw sales remain exact decimals in Parquet; model-side numeric predictors are finite floats. Counts disclose coverage. Negative/nonfinite labels fail at the typed boundary.

## Rossmann availability policy

| Field | V1 policy |
|---|---|
| Customers | Excluded entirely from predictors, including historical aggregates. Source/SQL retain it for auditing. The adapter projects it out. |
| Sales | y only at target date; history allowed only at/before cutoff and already available. Never target-relative lags that read intermediate future actuals. |
| Open | Target-day planned daily flag only if known at cutoff. Missing means unknown; Sunday alone does not imply closure. Never claim opening hours. |
| Promo | Target plan known at cutoff only; otherwise unknown. No causal interpretation or promotion optimization. |
| Promo2 / since week-year / interval | Expand only a metadata snapshot explicitly asserted to represent a known plan. Membership false yields 0; missing schedule yields unknown. ISO-week Monday start and listed target month determine active flag, not realized sales. |
| StateHoliday / SchoolHoliday | Target calendar inputs only when supplied as known at cutoff. No automatic national/state/school calendar is invented. Source category 0 is a known no-holiday value, distinct from missing. |
| StoreType / Assortment | Latest metadata snapshot known at cutoff; unknown metadata stays missing. They are static attributes within a supplied snapshot, not proof of historical constancy. |
| CompetitionDistance / opening month-year | Known metadata only. Distance units are not inferred. Opening age uses calendar-month difference at cutoff, not target date; incomplete/future start stays unknown. Month precision cannot establish an exact opening day. |
| Date / DayOfWeek | Compute target weekday, month, year and day-of-year from target date; preserve leap days. Source weekday was already validated during ingestion. |
| Id / sample submission Sales | Never predictors or labels. Store identity is a categorical predictor with an explicit unknown-store code. |

Rossmann archives do not contain actual publication timestamps. `HistoricalAssumptions` therefore requires a written explanation, an asserted metadata knowledge date, optional plan knowledge date, and a nonnegative sales-reporting delay. The loader never infers them from download/import time. Leaving `calendar_known_as_of=None` loads no future plans. Supplied late plans/metadata are ignored at earlier cutoffs. For real prospective use, supply independently recorded plan revisions instead of asserting all archived future flags were known.

A single archive-wide assumption is deliberately simple; it cannot represent real plan publication histories. Use explicit dated snapshots for richer availability, or leave plans unknown. Historical simulation results must disclose this assumption.

## Trace one real row

Inspected locally from the verified Rossmann files: Store 1, cutoff **2015-07-31**, horizon **7**, target **2015-08-07**. This trace assumes metadata known on 2013-01-01 and target plans known on 2015-07-31; those are simulation assumptions, not proven publication dates.

| Output | Dates/source actually read | Value / reason |
|---|---|---|
| horizon_days | request target minus cutoff | 7 |
| target_day_of_week | August 7 calendar | 5 (Friday) |
| sales_at_cutoff | July 31, available by cutoff | 5,263 |
| sales_lag_1_from_cutoff | July 30 exactly | 5,020 |
| sales_lag_7_from_cutoff | July 24 exactly | 3,706 |
| sales_lag_28_from_cutoff | July 3 exactly | 4,665 |
| sales_mean_7_through_cutoff | July 25..31 inclusive | 4,363.142857142857; 7 observed dates |
| sales_mean_28_through_cutoff | July 4..31 inclusive | 3,779.285714285714; 28 observed dates |
| target_open / target_promo | August 7 plan asserted known July 31 | 1 / 1 |
| target_sales | August 7 actual | Unavailable in competition test; never read as an input |

No August 1..6 actual is read. The same history statistics serve every horizon at this cutoff. Known target plans and target calendar facts may differ by horizon.

A hand-checkable synthetic test uses July 25..31 sales `[10, 0, 30, 40, 50, 60, 70]`. Lag 1 is 60 and the seven-day mean is 260/7. Removing July 30 makes lag 1 missing and mean 200/6, with coverage 6. The Sunday zero is an observed label, not an imputation. This small illustration is separate from the generated two-store fixture and from real Rossmann values.

## Run without Kaggle â€” PowerShell or bash

Run these identical commands from the repository root after `uv sync --locked`:

```text
uv run --locked python scripts/configure_dvc.py
uv run --locked dvc repro manifest@synthetic
uv run --locked python -m retailforecast.features.inspect --profile synthetic --store-id 9001 --cutoff 2015-07-31 --horizon 48 --metadata-known-as-of 2015-07-01 --assumption "Synthetic example only; metadata asserted known on the declared date."
uv run --locked pytest tests/test_temporal_leakage.py tests/test_feature_snapshot.py
uv run --locked python -m retailforecast.features.registry --check
```

The inspect command prints real computed features and provenance, never predictions. Without `--plans-known-as-of`, target Open/Promo/holiday inputs are null. To exercise the fixture's explicitly assumed plans, add `--plans-known-as-of 2015-07-31`. Input validation errors exit with an actionable message. No PostgreSQL, GPU or notebook is required for these feature-only commands.

For already prepared real files, change profile to `rossmann` and store ID to `1`; obtain/validate the competition files using DATA_VERSIONING first. The verified snapshot must be current; tampered or stale manifests fail before feature access.

## Shared training / backtesting / inference use

```python
from datetime import date
from pathlib import Path
from retailforecast.data.pipeline_config import DEFAULT_CONFIG
from retailforecast.features.builder import forecast_keys
from retailforecast.features.contracts import ForecastKey, HistoricalAssumptions
from retailforecast.features.preprocessing import FittedPreprocessor
from retailforecast.features.snapshot import load_feature_builder

assumptions = HistoricalAssumptions(
    explanation="Historical simulation; source archives do not prove publication dates.",
    metadata_known_as_of=date(2013, 1, 1),
    # Omit target plans unless their availability is explicitly asserted.
)
builder = load_feature_builder(DEFAULT_CONFIG, "rossmann", store_ids=[1], assumptions=assumptions)
fold_end = date(2015, 7, 31)
keys = forecast_keys([1], [date(2015, 7, 15), date(2015, 7, 20)], [1, 7, 48])
training = list(builder.iter_labeled(keys, training_label_end=fold_end))
preprocessing = FittedPreprocessor.fit(training, training_label_end=fold_end)
training_matrix = [preprocessing.transform_training(row) for row in training]
y = [row.target_sales for row in training]  # Separate from the model inputs.
preprocessing.save(Path("artifacts/example/preprocessing.json"))

request = ForecastKey(store_id=1, cutoff_date=fold_end, horizon_days=48)
serving_matrix_row = preprocessing.transform(builder.build(request))
# A future estimator consumes this row; no estimator is trained in this phase.
```

For backtests, create a fresh preprocessor per training fold; fit only fold-training examples. Use the unchanged fitted object on that fold's holdout inputs. Never fit or select vocabularies on validation/test data. `transform` rejects requests whose cutoff precedes the saved training label end; `transform_training` is explicitly limited to examples whose target and availability are within that fitted fold. It shares the same value transformation and does not fit again. Later model compatibility must also check the estimator's trained-through date and dataset lineage.

## Saved preprocessing and missingness

Fit computes medians from observed numeric training inputs. An entirely missing numeric column uses the named fallback 0 with its missing indicator set to 1. Each numeric predictor yields value plus `__missing`; categorical predictors use sorted training-only vocabularies, missing code -2 and unseen code -1. Stable output order is generated from the registry. The current 24 predictors yield 44 numeric matrix columns. Empty training data, invalid state, registry/order mismatch and post-fold labels fail visibly.

JSON persists feature order, medians, vocabularies, registry hash, fold label end and training dataset/assumption context. `load` validates compatibility. This object must be bundled with a future fitted estimator; a forecast request must never refit it. Category codes are identifiers with no measured numeric distance. Phase 8 LightGBM/XGBoost adapters add a deterministic one-hot layer derived from this saved categorical vocabulary and persist expanded ordering; category IDs are not passed as ordered numeric quantities.

Cold-start stores are allowed as feature rows: missing history/metadata remain null with zero coverage, store ID encodes as unseen, and fitted fallback is deterministic. This does not establish accurate forecasts or guarantee that a future approved model supports that store. The later model coverage policy may reject such requests. No automatic sales-zero clamp or closure prediction is implemented here.

## Resource bounds and verification

The adapter verifies DVC manifests, scans only selected columns in 10,000-row batches, and limits each loaded store partition to 32 stores. It never scans Customers into the feature objects. History indexes retain rows for the selected stores; there is no full cross-product materialization. Callers should process partitions sequentially. Each emitted row checks only fixed calendar windows plus latest-history lookup. Exact median fitting retains numeric training inputs and therefore rejects more than 50,000 fit rows rather than silently sampling; larger training design belongs to the next phase. These are bounds, not measured whole-stack RAM guarantees for 8 GB.

Tests mutate/erase every post-cutoff sale with known plans fixed and verify identical features, persisted-preprocessor matrices and fixed arithmetic prediction probes. The probes exist only in tests and are not trained or presented as application forecasts. Other cases cover h=1/h=48, target alignment, Sunday closures, missing rows, delayed labels, cross-store isolation, unseen stores, plan revisions, metadata timing, Promo2 weeks/months, leap days, schema mismatch and Customer exclusion across changed file snapshots. Tests run without fabricated accuracy metrics.

## Baseline backtesting integration

Phase 7 reuses build() for known target/calendar features and the new history_at_cutoff() view for fitting. The latter yields only sorted observations whose business and availability dates meet the origin boundary; algorithms never receive the full future label index. Baseline rules need no fitted median/category objects. Future learned models must still fit the preprocessing above within each chronological fold. MODEL_STRATEGY.md defines the implemented offline runner and truth-only scoring context.

## Phase 8 model use

Native tree adapters reuse the supervised builder and training-fold preprocessing above. with_history() supplies a physically available label view without duplicating calendar/lag/rolling calculations. A deterministic one-hot layer persists category ordering in each native model bundle. Model prediction rejects unsupported stores and preprocessing trained beyond the requested cutoff; checksum/version/context checks run on reload. Full serving lineage/promotion policy remains future work. TRAINING.md describes the bounded fit/evaluate/refit path and final-holdout exclusion.
