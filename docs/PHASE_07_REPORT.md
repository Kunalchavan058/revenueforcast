# Phase 7 — Honest baselines and rolling-origin evaluation

## Completion status

Complete. Offline baseline forecasts and actual-versus-predicted errors were generated from real historical labels, with repeatable artifacts. The real final holdout is reserved and remains unscored. No advanced model training, forecast-serving API/UI, database migration, worker, scheduler, MLflow service was added. Subsequent commits are recorded in Git history.

## Changed files

New implementation:

- `src/retailforecast/evaluation/contracts.py`: typed bounded configuration, folds, actual outcomes, history and algorithm protocols.
- `src/retailforecast/evaluation/splits.py`: chronological expanding-origin development/final calendar reservation.
- `src/retailforecast/evaluation/runner.py`: independent fit/predict orchestration, common output policy and post-prediction truth join.
- `src/retailforecast/evaluation/metrics.py`: MAE/RMSE/RMSPE, coverage/totals, reporting segments and development-only selection.
- `src/retailforecast/evaluation/snapshot.py`: scoring-only projected Parquet outcomes, never Kaggle test/template truth.
- `src/retailforecast/evaluation/artifacts.py`: deterministic result manifests/Parquet, frozen selection and final-release receipts.
- `src/retailforecast/evaluation/backtest.py`: bounded development/final CLI with preview and verified cache reuse.
- `src/retailforecast/forecasting/baselines.py`: last-known, last-observed weekday and historical weekday-average adapters.
- `configs/backtest.yaml`: explicit folds/horizons/stores/seasonality/seed/closure/availability settings.
- `tests/test_backtesting.py`, `tests/test_backtest_artifacts.py`, `tests/test_backtest_cli.py`: 33 new cases including parametrizations.

Updated `src/retailforecast/features/builder.py` with the public available-history iterator, plus evaluation/forecasting package descriptions. Existing feature values/registry and DVC data fingerprints are unchanged.

Documentation: new MODEL_STRATEGY, decision 0008 and this report; updated README, configs README, CODING_STANDARDS, ARCHITECTURE, DATA_FLOW, DATA_DICTIONARY, FEATURES, ROADMAP and IMPLEMENTATION_LOG. No new dependency or lock change. Existing CI runs these tests through its full pytest check; remote CI was not run for these local changes.

## Verified real development study

Three stores (1,2,3), three development origins (2015-01-20 / 2015-03-09 / 2015-04-26), all horizons 1..48 and three fixed baseline rules produced **1,296 forecast rows**, 432 requested/labeled/scored rows per method. The non-overlapping target windows end on 2015-06-13. The final cutoff is 2015-06-13, reserving June 14 through July 31 without evaluating those targets.

Each method's 432 labeled points include **77 zero actuals**. These remain in MAE/RMSE and totals; RMSPE uses the 355 positive actuals. No future target plans are asserted known in the default config, so closure overrides do not use realized Open. Retrospective open/closed segments remain available after scoring.

| Method | Pooled MAE | Pooled RMSE | Pooled RMSPE | Mean development-fold RMSPE |
|---|---:|---:|---:|---:|
| last_known | 2759.44 | 3711.71 | 0.612001 | 0.515586 |
| last_weekday | 1301.25 | 1895.25 | 0.296207 | 0.295106 |
| weekday_average | 1106.77 | 1671.97 | 0.265734 | 0.257224 |

These values were read from the saved real result manifest, not invented. `weekday_average` won the predeclared mean-fold RMSPE/MAE/name selection on this specific development subset. This does not establish all-store performance or superiority over advanced models. Pooled RMSPE and mean fold RMSPE are distinct computations; selection uses the latter.

Both real runs produced byte-identical `predictions.parquet`, `segments.parquet`, `results.json` and `selection.json`. Outputs live in ignored `artifacts/evaluation/development` and `development-repeat`. Aggregate, fold, store, horizon, observed-open context, ISO week and month summaries are inspectable. No holdout release receipt exists for this real study.

Protocol fingerprint: `15cdb365dcac6073d776b7f160d990e5eb112a8932e766630e389e58022e4810`.

Prediction Parquet SHA-256: `e7b4aa5ae6e5aeefbd8f9188406aff87e46bc312b1ed06c060621dfeca2005e4`.

Git revision is recorded with working_tree_dirty=true and actual source hashes; committing or archiving this uncommitted source is necessary for restoration from version control. Seed 42 is recorded, although no randomness is used by these baselines.

## Commands and outcomes

| Command/check | Result |
|---|---|
| `uv run --locked pytest tests/test_backtesting.py tests/test_backtest_artifacts.py tests/test_backtest_cli.py -q` | 33 passed |
| `uv run --locked pytest -q` | **99 passed**, no skips; 66 existing plus 33 new, including PostgreSQL integration |
| `uv run --locked ruff check .` | Passed |
| `uv run --locked ruff format --check .` | Passed; public Python and documented Python snippets formatted |
| `uv run --locked mypy` | Success, no issues in 49 source files |
| Registry `--check` | Generated feature reference remains current |
| `uv lock --check` | 127 resolved packages consistent; no dependency changes |
| Backtest config Prettier check | Initial style issue corrected; effective typed config equality verified |
| Development CLI, default bounded real config | 1,296 genuine predictions/errors, three folds, selected weekday_average |
| Same development CLI with output `artifacts/evaluation/development-repeat` | Same scores; all four result files byte-identical |
| Verify results/checksum and cutoff assertions | Passed; every scored target ends before reserved final window |
| Synthetic end-to-end final CLI tests | Frozen selection, rejected config change, one release, verified cache return without prediction or outcome loading |
| `uv run --locked dvc status` | Data/pipelines up to date |

Full frontend build/browser checks were not rerun because no frontend/API code changed. No actual final-holdout scoring was run. Tests with synthetic provenance do not replace the real CLI: the real development run exercised actual Git/source hashes, verified Rossmann Parquet and output publication.

## Correctness, readability and trade-offs

Fit adapters receive only immutable observations satisfying date and available_as_of <= origin. Tests verify a spy sees no delayed/future labels, changing/erasing all post-origin actuals cannot affect any of 48 baseline forecasts, and generic future-trained/nonfinite algorithms fail. The runner uses shared FeatureRow inputs, emits all requested keys, applies a common nonnegative policy and never sees actual labels inside prediction calls. Error fields remain null without eligible labels/support. Closed-store positive actuals are preserved and scored; only a known plan can force a zero estimate.

Hand-calculated tests cover latest/weekday/seasonal values at h=1/h=48, sparse fallback, store isolation, MAE/RMSE/RMSPE arithmetic, zero denominators, missing/delayed truth, common-mask exclusions, date splits, horizon buckets, final-selection rejection, output corruption and once-only release. All-zero folds leave RMSPE undefined and cannot win selection; missing coverage is disclosed rather than bypassed.

Reviewed explicit types, public docstrings, targeted temporal comments, meaningful names, separate modules, named settings and shared fit/predict/scoring boundaries. No DataFrame shuffle, duplicate Python root or duplicated feature calculations were introduced. Protocol/source/registry/lock identity, fold dates and seed accompany results. Local receipts are audit guards, not security against manual filesystem edits. Incomplete final release stays visible rather than silently becoming another tuned trial.

Resource caps: 32 stores, 2..6 development folds, horizon <=48, 100,000 result rows, projected 10,000-row batches, sequential origin fitting. History/result/segment lists still consume bounded RAM; total 8 GB whole-stack peak and all-store throughput remain unmeasured. The real final period is reserved for later frozen comparison; once eventually inspected, it cannot be called untouched in subsequent development.

## Acceptance review

- [x] Algorithm-independent deterministic baseline evaluation with chronological refit policy and no future model inputs.
- [x] Training/selection/final dates separated; real final kept locked, with tested release/cache workflow.
- [x] Three transparent h=48-capable baselines and documented sparse/closure/zero policies.
- [x] Genuine aggregate and required segment scores, coverage and reproducibility metadata.
- [x] Bounded CLI saves inspectable JSON/Parquet; identical inputs reproduce exact local bytes.
- [x] Hand-computed tests, future mutation/fit-view checks, standards/strategy/log/roadmap updated.
- [x] Stop after Phase 7; advanced algorithms and forecast-serving features remain future work.
