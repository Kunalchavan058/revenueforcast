# CPU model training and bounded Auto selection

## In plain English

Choose XGBoost, LightGBM or Auto. The application prepares historical examples, fits preprocessing inside each training fold, tests small internal parameter candidates on chronological development windows, and saves a real fitted model with its preprocessing. Auto selects between eligible tree candidates; it never substitutes a baseline or uses hidden Kaggle answers. Baselines remain visible comparisons, even when they perform better than a tree model.

There is no training UI in this phase. The existing web page still reports API health. No notebook, GPU, remote account, model approval service or database worker is required. These are local CLI training runs, not active production model promotion.

## Install and run — PowerShell or bash

From the repository root:

```text
uv sync --locked --python 3.11
uv run --locked dvc repro manifest@synthetic manifest@rossmann
uv run --locked python -m retailforecast.training.train --algorithm lightgbm --mode dev
uv run --locked python -m retailforecast.training.train --algorithm xgboost --mode dev
uv run --locked python -m retailforecast.training.train --algorithm auto --mode dev
```

The real snapshot must already exist; follow DATA_VERSIONING.md to obtain/prepare it. Changed dependency locks require DVC reproduction because environment identity is deliberately part of the dataset manifest. This does not change original source CSVs or PostgreSQL records. Raw labels remain historical; no Kaggle test Sales are available.

For the bounded full-history mode:

```text
uv run --locked python -m retailforecast.training.train --algorithm lightgbm --mode full
uv run --locked python -m retailforecast.training.train --algorithm xgboost --mode full
uv run --locked python -m retailforecast.training.train --algorithm auto --mode full
```

Every command creates a new ignored `artifacts/training/<algorithm>-<mode>-<id>/` directory. An optional `--output artifacts/training/my-run` names a new run; existing output is refused. `--config`, `--backtest-config` and `--data-config` are engineering setup overrides, not normal product tuning controls. Normal selection is algorithm plus dev/full mode; no learning-rate/depth/tree-count flags or UI knobs are exposed.

## What dev and full mean

Both modes use the explicit store cohort in configs/backtest.yaml (currently stores 1,2,3), identical three development windows and all 48 forecast horizons. Full does **not** silently mean all 1,115 Rossmann stores. The adapter currently supports partitions up to 32 stores. Choose the cohort deliberately before studying scores; results describe that cohort only.

| Setting | dev | full |
|---|---:|---:|
| Historical origin lookback | Last 180 calendar days | Entire available history before fitting cutoff |
| Initial origin cadence | Every 14 days | Every 7 days |
| Maximum supervised rows per fold/refit | 8,000 | 40,000 |
| Maximum trials per requested algorithm | 2 | 3 |
| Supervised elapsed limit | 600 seconds | 1,800 seconds |

If the origin grid would exceed the row budget, select evenly spaced origins across the requested window before looking at label values. Retain every configured store and all 48 horizons at each retained origin; do not truncate the first stores or shortest horizons. Record the cap, requested cadence, actual origin count and training date span. Missing/unavailable targets are omitted rather than made into zero labels.

The fitted model is a single pooled direct regressor with store identity, target calendar, horizon and cutoff-safe history features. It does not read true intermediate future sales. Warmup is 28 days. Each target and label availability must end at/before the fitting boundary. The shared builder and Customers exclusion remain authoritative.

## Chronological search and fixed holdout

The existing baseline plan reserves final targets June 14..July 31, 2015, with cutoff June 13. Search uses only the three earlier development windows. Each trial refits preprocessing and model at each development origin, with no shuffling or globally fitted vocabularies. Changing or erasing all later actuals cannot change a fitting matrix.

The internal deterministic search grid has at most three modest tree/depth/rate candidates; it is not RandomizedSearchCV with accidental random folds. All algorithms share the same selected training origins, labels and evaluation targets. Fold preparation is cached only within this one request/cutoff, across parameter candidates with identical input policy.

Selection uses mean development-fold RMSPE, then mean MAE, then stable method name. RMSPE requires positive denominators and complete requested coverage in every fold. MAE/RMSE preserve zero actuals; common masks, known-closure policy and baseline rules are unchanged. Timing is recorded but is not a hardware-dependent tie-breaker. Per-store, fold, weekday/month context, four horizon buckets and **individual horizons 1..48** are saved; no numeric score is hardcoded.

A specific algorithm request selects only among its own trials. Auto compares eligible XGBoost and LightGBM trials. Failed/incomplete trials cannot win. If all requested candidates fail eligibility, training fails visibly instead of silently switching to a baseline. Baseline errors are always retained for honest comparison; a valid saved tree is not proof that it beats the baselines.

After selection, refit the chosen parameters through the **reserved final origin**, June 13—not through July 31. Save that candidate, verify native reload predictions at h=1 and h=48, and publish only after the supervised worker succeeds. The real final holdout is neither scored nor used as a fitting label in this phase. The Phase 7 final CLI supports baseline selections; this training command does not expose a final-holdout release flag. A later learned-model final evaluation must validate this frozen training protocol/bundle rather than pass trial IDs to the baseline-only runner.

## Preprocessing and adapter contract

NativeTreeAdapter provides fit/load/capabilities; its fitted TreeModel provides predict/save. Both families use the same PreparedData and fitted preprocessing contracts. Models advertise CPU-only execution, horizons 1..48, native serialization and explicit trained-store coverage. A model rejects earlier forecast cutoffs and stores outside its fitted cohort. This is separate from the raw feature builder's ability to represent cold-start stores.

FittedPreprocessor learns numeric medians/missing indicators and categorical vocabularies from training rows only. A deterministic one-hot layer derived from those saved vocabularies prevents either tree library from interpreting arbitrary category IDs as ordered quantities. Missing/unseen categories get distinct columns. Save the exact expanded column order and reconstruct it on load; inference never fits encoders or imputers.

XGBoost uses CPU histogram training and native JSON. LightGBM uses deterministic CPU column-wise fitting and its native text model. No pickle is loaded. Bundle checksums, algorithm, exact native library versions, preprocessing identity/order, training dates and dataset context are checked on reload. Raw estimates flow through the same nonnegative/known-closure policy in the evaluation runner; direct adapter predict returns a finite raw estimate, not a serving API response.

Native APIs and format references: [XGBoost model IO](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html), [LightGBM Python API](https://lightgbm.readthedocs.io/en/v4.6.0/Python-API.html).

## CPU, memory, time and failure controls

configs/training.yaml owns internal settings: one job at a time, at most two native CPU threads, an RSS warning at 1,536 MiB, hard sampled aggregate RSS cap 2,048 MiB, system available-memory floor 256 MiB, and mode-specific elapsed limits. OMP/BLAS thread environment settings accompany native library settings. The CLI acquires a cross-platform file lock, then launches one hidden Windows-compatible subprocess. A separate coordinator samples RSS/elapsed time every 0.25 seconds and can terminate native fitting, not just stop between trials.

RSS sums coordinator, worker and descendants; shared pages can be counted twice. Short allocation spikes can escape sampling. This is a conservative application budget, not a Windows Job Object/cgroup or guarantee of total PostgreSQL/browser/OS RAM. Observed run peaks are recorded. Matrix/row caps and shallow CPU trees bound normal work, but whole-machine 8 GB peak remains a separate measurement obligation.

The worker stages `candidate/`; the coordinator verifies it and only then renames it to `model/`. A native error, timeout, memory excess or missing eligible winner preserves status/logs without replacing any previous run/model. Individual failed trials are logged explicitly and may be followed by another bounded trial; resource-budget termination aborts the job, rather than pretending an unfinished search is successful. One existing model or database serving pointer is never modified. Stale locks are released by the OS/filelock mechanism on process exit; failed directories remain for audit.

## Saved artifacts and provenance

Each run includes:

- request.json and status.json: frozen internal configuration, requested algorithm/mode, UTC events, status and measured resource use.
- worker.log and trials.json: actual errors, trial IDs, parameters, timings and outcomes.
- folds/: native fold models, fitted preprocessing and manifests for each evaluated trial/origin.
- comparison/: genuine actual-versus-predicted Parquet, segment metrics and evaluation JSON. No baseline selection.json is emitted for a tree study.
- training.json: resolved algorithm/trial, full effective config, code revision/dirty-source hashes, raw ingestion checksum and DVC fingerprint, seed, registry/environment hashes, date span, duration, comparison and final-candidate paths, MLflow IDs and explicit final_holdout_scored=false.
- model/: native model.json or model.txt, preprocessing.json and checksum-bearing bundle.json, including model class, actual native parameters, library versions, fitted stores and expanded feature order.

File data stay ignored locally; Git tracks code, configs and DVC pointers. PostgreSQL business counts stay unchanged. Bundle success is not approval or activation; lifecycle execution and API reuse come later.

## PostgreSQL-backed MLflow without another server

Before training, run `uv run --locked python scripts/configure_mlflow.py` against the healthy local PostgreSQL service. New parent/trial metadata use its distinct `retailforecast_mlflow` database/login; artifacts remain ignored local files. No tracking server/cloud account is needed. Phase 9 supersedes Phase 8's temporary SQLite backend; earlier SQLite metadata/files remain available for audit, and synthetic offline fixtures explicitly opt into disposable SQLite only.

Actual generic/native parameters, seeds, dataset/code identity, fold/horizon metrics, duration, resource observations and artifacts are still logged. Failed/interrupted runs are marked failed. Raw CSV/matrices are not uploaded. Registration, active-slot checks and rollback are separate explicit operations documented in [MODEL_LIFECYCLE.md](MODEL_LIFECYCLE.md); fitting never replaces a serving model automatically.

## Validation and compatibility

```text
uv run --locked pytest tests/test_training.py tests/test_training_resources.py tests/test_training_workflow.py
uv run --locked pytest
uv run --locked mypy
uv run --locked ruff check .
```

Tests genuinely fit both native libraries, compare seeded results within numerical tolerance, round-trip models/preprocessing, mutate future sales, verify h=1/h=48 and one-hot encoding, reject corrupted bundles/unseen stores/earlier cutoffs, enforce locks/time/memory, and run the full supervised synthetic Auto/MLflow flow. No tests are replaced by skips.

The pinned LightGBM 4.7.0 Windows build failed a standalone native label-setting fit in this environment; 4.6.0 passed that reproducer and the model tests, so the lock pins 4.6.0. This is a measured local compatibility decision, not a claim that every 4.7 platform is broken. MLflow currently emits an upstream SQLAlchemy deprecation warning; it does not prevent measured tracking or run reloads. Same locked CPU environment has tested numerical reproducibility; different architectures/library versions are not promised bit-identical results.

Daily target plans and store metadata have separate assumptions: calendar_known_as_of=None disables Open/Promo/holiday plan loading, while a Promo2 schedule may still derive from the asserted known metadata snapshot. Archived metadata does not independently establish that historical schedule publication date.


## Validation evidence after final refitting

The original `folds/TRIAL/CUTOFF/` directories contain the real pre-validation models and fitted preprocessing. Registration now preserves the selected trial's fold models, seals their linkage to the final refit and automatically uses them for shared-window promotion comparison. A final model trained through June 13 can therefore have valid earlier rolling-origin validation evidence without ever predicting backward with June-13 weights. Different recipes disclose their sampling policies; Auto compares algorithms with the same mode/budget. Original final weights and the locked final target dates remain separate. See MODEL_LIFECYCLE.md and decision 0011.
