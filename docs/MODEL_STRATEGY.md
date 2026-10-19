# Model strategy and honest historical evaluation

## In plain English

A backtest asks what could have been forecast at a past date, freezes that knowledge, and compares estimates with subsequently observed sales. A baseline is a transparent historical rule, not an advanced learned model. The first results describe three selected Rossmann stores in 2015, not present-day performance or a guarantee for every store.

Phase 7 implements deterministic baselines, rolling-origin evaluation and private result artifacts. It does not implement LightGBM, XGBoost, Auto training, serving, UI charts, model approval or scheduling. The final real-data holdout is reserved and left unscored in this phase. Synthetic tests exercise its complete release path.

## Formal target and available information

For store s, business-date cutoff t and horizon h in 1..48, predict daily Sales y(s,t+h) using only information available by t. Historical actuals must satisfy both date <= t and available_as_of <= t. Future promotions/opening/holiday covariates require a dated plan known by t. Customers are excluded entirely. [FEATURES.md](FEATURES.md) and the generated [FEATURE_REGISTRY.md](FEATURE_REGISTRY.md) remain the input contracts.

A download/import timestamp is not a historical training date. Rossmann archive files lack publication timestamps, so `configs/backtest.yaml` records explicit assumptions. The default assumes same-day label availability and metadata known from 2013-01-01, with **no asserted future target plans**. Target flags therefore remain unknown. Planned future covariates are optional and never extracted from realized Sales/Open after prediction. No Kaggle test row or submission placeholder is a ground-truth label.

## Chronological protocol

`make_plan` reserves the last H historical dates for a final holdout, then N disjoint H-day development windows immediately before it. Defaults are H=48 and N=3. Dates derive only from validated train coverage; algorithm errors do not choose favorable windows. Every fold fits from expanding available history through its origin. Each of its 48 forecasts then uses this same frozen fitted history. Later development folds may use earlier development actuals once available, which simulates retraining over time. No random shuffle or random train/test split occurs.

For the current source ending 2015-07-31:

| Role | Forecast cutoff / training label boundary | Subsequently observed targets |
|---|---|---|
| Development 1 | 2015-01-20 | 2015-01-21..2015-03-09 |
| Development 2 | 2015-03-09 | 2015-03-10..2015-04-26 |
| Development 3 | 2015-04-26 | 2015-04-27..2015-06-13 |
| Reserved final | 2015-06-13 | 2015-06-14..2015-07-31 |

For any future learned direct model, a training example is eligible only when its target date and label availability are <= the origin; selecting rows solely by their earlier feature cutoff is insufficient. Fit encoders/imputers inside each fold and persist them with that fold's estimator. The current deterministic baselines require neither an encoder nor an imputer. This phase chooses **refit once per origin**, with reuse only across that origin's target horizons. A future alternative reuse policy must record its trained-through date and pass the same runner guard.

## Three reproducible baselines

| Method | Forecast rule | Sparse-history policy |
|---|---|---|
| `last_known` | Repeat the latest available same-store actual at/before cutoff for every horizon. | No store history => unsupported, not zero. |
| `last_weekday` | Repeat the most recent available same-store observation matching the target weekday. | No matching weekday => last-known same-store actual. |
| `weekday_average` | Mean matching-weekday actuals in the inclusive last `seasonal_weeks * 7` calendar days through cutoff; default 8 weeks. | No matching observation inside window => last-known same-store actual. |

Missing dates are not converted to zeros and do not shift calendar weekdays. Observed zero sales, including historical closed days, remain in historical averages. There is no cross-store fallback.

At horizon 48, the target weekday is already a calendar fact. `last_weekday`/`weekday_average` look back from the **origin**, not from the target: if target-minus-seven falls after the origin it cannot be read. `last_known` simply repeats its origin value. None requires true intermediate future sales, recursion, or reading the holdout before prediction.

Hand-calculated test: January 1..14 have sales equal to day-of-month times ten, cutoff January 14. For January 15 (Thursday), forecasts are last_known=140, last_weekday=80 (January 8), and two-week weekday_average=45 (January 1/8 values 10/80). Horizon 48 targets Tuesday March 3: values are 140, 130 (January 13), and 95 (January 6/13 values 60/130). These are explicit synthetic test values, not measured Rossmann results.

## Output and closure policies

All algorithm adapters receive a physically filtered immutable `TrainingHistory`, never the complete builder or scoring outcomes. `predict` receives only a FeatureRow. A model declaring trained_until after origin fails. Every method emits every requested key, including unsupported rows. The runner validates finite predictions and applies the common nonnegative clamp, retaining the raw estimate and adjustment flags.

Under `closure_policy: known_plan_zero`, a supported forecast is set to zero **only** when its target Open plan was explicitly known as closed by cutoff. `unadjusted` disables that override. Sunday by itself does not establish closure. Without plans, a baseline can still estimate zero from observed historical patterns; that estimate does not assert a known future closure. Retrospective Open enters only scoring segments. Closed-store positive actual sales remain genuine labels and can produce nonzero errors; they are never overwritten to flatter results.

Predictions are generated before the outcome loader is invoked. Only `daily_sales` supplies outcomes; the loader projects Sales/observed Open and never Customers. Delayed outcomes unavailable by scoring_as_of remain unlabeled. Error columns are null when the actual or prediction is unavailable, or when a row is excluded from common support.

## Metrics, selection and fairness

Business summaries report **MAE and RMSE** in source Sales units; no currency unit is invented. Both include zero actuals. Also report Rossmann **RMSPE** as a ratio, excluding exactly zero actuals from its denominator and explicitly counting exclusions. An all-zero segment has null RMSPE, not a fabricated perfect score. Do not add epsilon denominators or remove zero-sales cases from revenue summaries.

For actuals [0,10,20] and predictions [2,8,24], MAE=8/3, RMSE=sqrt(8), RMSPE=0.2 over the two positive actuals; one zero is excluded only from RMSPE. Adding a fourth forecast with no actual creates no additional error observation and reduces coverage to 3/4.

Following the existing Rossmann selection policy, choose the lowest **mean development-fold RMSPE**, then mean fold MAE, then stable method name. Selection uses no final result. Baseline runtimes are not tie-breakers, avoiding hardware-dependent selection for these deterministic rules. Future Auto policy remains separate. A method must score every requested development key and have defined RMSPE in every fold to be eligible. Missing labels, unsupported history or an all-zero fold can leave no eligible winner; the report still records coverage and null/partial metrics, and final release is refused.

Methods are scored on identical store/cutoff/target keys with a common prediction-support mask. A missing prediction for one method excludes that key from every method's scored comparison, with reason counts visible in the point table. Individual requested/labeled/scored counts disclose the exclusions. Selection rejects inconsistent fold summaries. No method can omit difficult requested keys to improve its score.

Reports include pooled aggregate, per-fold, per-store, horizon buckets **1–7 / 8–14 / 15–28 / 29–48**, observed-open/closed/unknown context, ISO target week (including ISO year), and target month. These are separate reporting axes, not every possible cross-product. Fold metrics preserve chronological results; pooled metrics are calculated from points, not incorrectly averaging already averaged errors. `labeled_actual_sales_sum` includes all available labels, including zeros and unsupported predictions; `scored_actual_sales_sum` and `scored_predicted_sales_sum` refer only to the common scored mask. Always compare coverage alongside errors.

## CLI — PowerShell and bash

Use identical commands from the repository root after preparing the real snapshot as described in [DATA_VERSIONING.md](DATA_VERSIONING.md):

```text
uv run --locked python -m retailforecast.evaluation.backtest --plan-only
uv run --locked python -m retailforecast.evaluation.backtest --stage development --output artifacts/evaluation/development
```

The default config evaluates stores 1,2,3, three origins and all 48 horizons: 1,296 method/store/origin/horizon points. To choose a different explicit store partition, use `--stores 1 2 3` or edit the config **before** its study/selection. `--config` selects a typed YAML backtest config; `--data-config` selects the existing preprocessing config. The seed is recorded (42 by default); these baselines use no random sampling. No silent store sampling or hidden trial search occurs.

For an independent reproducibility check before final release:

```text
uv run --locked python -m retailforecast.evaluation.backtest --stage development --output artifacts/evaluation/development-repeat
```

Identical data/config/source/environment produce identical JSON and Parquet bytes. Output locations and wall-clock timestamps are absent from result identity. Output must be a new relative subdirectory of ignored `artifacts/evaluation`; existing runs are not overwritten. No PostgreSQL, GPU, worker or cloud service is required by this CLI.

For tests without Kaggle:

```text
uv run --locked pytest tests/test_backtesting.py tests/test_backtest_artifacts.py tests/test_backtest_cli.py
```

These tests generate explicitly synthetic fixtures sufficient for several origins. The earlier two-day DVC synthetic fixture is deliberately too short for the default 192-day study and fails with an actionable insufficient-history message; it is not padded with invented actuals.

## Locked final holdout

Development is the default and emits `selection.json` only from development scores. The final calendar is reserved before scoring under ignored `artifacts/evaluation/holdout_locks`, keyed by dataset/store scope. Moving that final window within the same study is rejected. Final scoring requires the exact development selection, same data/config/code/registry/environment and verified development report/Parquet hashes. There is no final-stage method override.

Only after all intended candidate decisions are frozen, release the selected method once:

```text
uv run --locked python -m retailforecast.evaluation.backtest --stage final --selection artifacts/evaluation/development/selection.json --output artifacts/evaluation/final
```

The final method is refitted through the reserved final cutoff, never the end of its target window. A release receipt is claimed before final scoring. Successful identical reruns verify cached files and return without predicting or loading scoring outcomes again. Changed decisions/output locations are rejected. An interrupted pending release stays visible; inspect and restore consistent artifacts/receipts instead of deleting the ledger to retune. Keep this local ledger with result backups.

This is an auditable laptop workflow, not an adversarial security boundary: a person with filesystem access can alter files or create a new dataset/store study. Once final results have been seen, that period is no longer an untouched test set for subsequent model development. Never claim an already inspected holdout is fresh for new algorithms. **Phase 7 leaves the real reserved holdout unscored**; only synthetic tests exercise final release, preserving the real period for a later fully frozen model comparison.

## Saved results and provenance

Each run writes:

- `predictions.parquet`: method, fold, store, cutoff/target/horizon, trained_until, raw/adjusted prediction, known and retrospective opening context, status, optional actual and signed/absolute/squared/percentage errors.
- `segments.parquet`: metrics and coverage for every reporting axis.
- `results.json`: typed publication manifest, complete segment summaries and Parquet checksums.
- `selection.json`: development-only frozen method choice, protocol and report checksum.

The protocol embeds each fold's dates, effective config/seed, DVC dataset identity, explicit knowledge assumptions, Git revision, dirty-tree notice, actual data/features/evaluation/forecasting source hashes, lock hash, feature registry hash and Python/PyArrow versions. Uncommitted source hashes are recorded honestly: Git revision alone cannot restore uncommitted code, so commit or archive source before claiming full restoration from Git. Code/config changes invalidate an earlier frozen selection. Results publish their JSON manifest last; incomplete runs are not accepted as cached success. Same-platform byte reproducibility is tested; cross-platform Parquet binary identity is not promised.

## Failure modes and resource bounds

Unknown/missing store history yields unsupported predictions, not fake zero revenue. Gaps and late labels reduce coverage; insufficient calendar history fails plan creation. Nonfinite predictions, ambiguous duplicate truth keys, future-trained models, malformed configs and inconsistent comparison masks fail visibly. All-zero slices have meaningful MAE/RMSE and undefined RMSPE. Incomplete final releases require inspection, not automatic retuning or a falsely successful result.

Resources are bounded by at most 32 selected stores, 2..6 development folds, horizons <=48, at most 100,000 result rows, 10,000-row projected input/output batches and sequential fitting. No complete million-row-by-48 Cartesian expansion is created. History/point/segment lists still occupy RAM proportional to the chosen bounds; total peak memory on an 8 GB machine has not been measured. Do not infer all-store or future advanced-model accuracy from the three-store starter study. Promotion effects remain predictive associations, not causal uplift.
