# Phase 8 — Genuine bounded CPU model training

## Completion status

Complete. XGBoost, LightGBM and Auto commands genuinely fit native CPU regressors, evaluate chronological development forecasts against actual Sales, persist preprocessing/models and log experiments locally in MLflow. A full-history LightGBM command was also executed successfully. No final-holdout scoring, production model activation, API/UI training flow, scheduler, commit or push was added.

## Exact changed files

New implementation under the existing package root:

- training/contracts.py: typed internal config, budgets, modes/search candidates, model span/capability/bundle/request contracts.
- training/dataset.py: bounded chronological origins, shared supervised features, fold-only preprocessing and one-hot encoding.
- training/adapters.py: shared native CPU fit/load/capabilities and fitted predict/save contracts, version/checksum/cutoff/store guards.
- training/resources.py: one-job lock and process-tree RSS/elapsed watchdog with owned-child cleanup.
- training/tracking.py: SQLite-backed local MLflow parent/trial parameters, metrics, artifacts and interrupted-run audit.
- training/workflow.py: fixed development folds, internal bounded search, honest baselines, Auto eligibility and pre-holdout refit.
- training/train.py and training/worker.py: normal CLI coordinator and internal supervised subprocess entrypoint.

The paths above are under `src/retailforecast/`. Updated training/__init__.py, features/builder.py (filtered history replacement), features/registry.py (cached immutable registry fingerprint), evaluation/metrics.py (optional exact-horizon summaries) and evaluation/artifacts.py (training source hashes and optional suppression of baseline selection files).

Added configs/training.yaml and tests/test_training.py, tests/test_training_resources.py, tests/test_training_workflow.py. Updated pyproject.toml/uv.lock with exact native/client/resource dependencies. dvc.lock was rebuilt against the new environment; source CSVs/SQL records did not change.

New docs: TRAINING.md, decision 0009 and this report. Updated README, configs README, ARCHITECTURE, CODING_STANDARDS, DATA_FLOW, DATA_DICTIONARY, FEATURES, MODEL_STRATEGY, MODEL_LIFECYCLE, ROADMAP and IMPLEMENTATION_LOG.

## Verified real training results

All runs use stores 1,2,3, CPU threads=2, seed=42, the same three 48-day development windows and raw actual labels. They refit the chosen model through **2015-06-13**. Final targets June 14..July 31 are not training labels or scored outcomes. Full mode means full eligible history within this explicit cohort, with recorded origin sampling; it does not mean all 1,115 stores.

| Command algorithm / mode | Selected trial | Refit rows | Pooled MAE | Pooled RMSE | Pooled RMSPE | Mean fold RMSPE | Supervised seconds | Sampled peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| auto / dev | xgboost_trial_1 | 1,665 | 1067.36 | 1588.23 | 0.217658 | 0.216812 | 49.47 | 281.12 |
| xgboost / dev | xgboost_trial_1 | 1,665 | 1067.36 | 1588.23 | 0.217658 | 0.216812 | 36.78 | 276.76 |
| lightgbm / dev | lightgbm_trial_1 | 1,665 | 1073.72 | 1599.16 | 0.219204 | 0.218613 | 36.67 | 276.37 |
| lightgbm / full | lightgbm_trial_3 | 17,373 | 981.89 | 1530.35 | 0.198931 | 0.197886 | 52.72 | 331.75 |

Numbers above were generated from the saved real training/status manifests. Selection uses mean development-fold RMSPE, then MAE/name, not pooled RMSPE or final outcomes. This explains why a different trial can have marginally lower pooled RMSPE without winning the predeclared fold criterion. Full-mode results use a different training-data budget and are not part of the dev Auto choice. These are selected development results, not unbiased final-holdout accuracy or a general guarantee.

Auto evaluated four genuine tree trials (two per family), all with complete measured development coverage, plus three baselines. Its comparison contains 3,024 rows. Explicit dev family comparisons contain 2,160 rows each; full LightGBM contains 2,592. Every comparison includes aggregate/fold/store/open-context/week/month, four horizon buckets and individual horizons 1..48. Each method scores the same 432 development labels, including 77 zeros retained in MAE/RMSE and excluded only from RMSPE. Baseline metrics remain visible even when unfavorable to a requested model.

Verified output folders under ignored artifacts/training:

- phase08-auto-dev-verified
- phase08-xgboost-dev
- phase08-lightgbm-dev
- phase08-lightgbm-full

Each model/ contains native model.json or model.txt, preprocessing.json and checksum manifest. All four final bundles were reloaded with their pinned libraries, all 54 expanded columns validated, and the original source/config/protocol identities rechecked. MLflow parent and successful trial runs are FINISHED with recorded generic/native parameters and genuine scores. No real holdout release receipt exists.

## Commands and checks

| Command/check | Result |
|---|---|
| Native adapter tests on explicit synthetic history | Both libraries fit, reproduce seeded predictions within tolerance and reload native/JSON bundles |
| Resource/failure tests | One-job rejection/release, visible memory warning, memory/time child termination, failed worker audit and prior-model preservation passed |
| Supervised synthetic Auto integration | Real worker, both algorithms, MLflow params/exact-horizon metrics, model publication and final-label exclusion passed |
| All requested-candidate failure | Failed run/trial records; no silent baseline fallback or completed model |
| `uv run --locked pytest -q` | **111 passed**, no skips, one upstream MLflow/SQLAlchemy deprecation warning |
| `uv run --locked mypy` | Success, no issues in 60 source files |
| Ruff lint and format checks | Passed |
| Feature registry freshness | Passed; generated descriptions unchanged |
| `uv lock --check` | 148 resolved packages consistent |
| `uv run --locked dvc repro manifest@synthetic manifest@rossmann` | Rebuilt validated manifests/receipts for the new lock; source row counts unchanged |
| Auto dev CLI | Genuine saved XGBoost candidate with both families evaluated |
| Explicit XGBoost dev / LightGBM dev CLIs | Genuine saved requested-family candidates |
| LightGBM full CLI | Genuine saved candidate using 17,373 eligible supervised rows |
| Auto versus explicit family prediction comparison | All 432 trial-1 points per family reproduce within 1e-6 tolerance |
| Final artifact verification | Native/preprocessing hashes/versions/columns, MLflow status, current source/config identity and no scored final targets verified |

No frontend build/browser repeat was needed because no frontend/API behavior changed. GitHub CI was not run for these local changes. MLflow is a lightweight client with local SQLite metadata/files, not a new Docker/remote service. Decision 0009 documents this deliberate refinement of the earlier service-backend architecture.

## Compatibility correction and failure evidence

Initial integration exposed strict LightGBM boolean parameter formatting, corrected to native accepted values. The installed LightGBM 4.7.0 Windows build also failed a minimal standalone NumPy label-setting fit independently of application features. The pinned 4.6.0 release passed that reproducer, all native tests and real dev/full commands. This is a local measured compatibility choice, not a claim about every platform/version. Early experimental failures remain audited locally and are not counted as verified final runs.

The final suite reports one upstream MLflow SQLAlchemy noload deprecation warning; it was not suppressed or turned into a skip, and verified run/metric reloads succeed.

## Dataset and model provenance

Final Rossmann DVC fingerprint: `a3ed2b3e5d3002ece94d4f2a4faa49187489df59a5889d547e5c50a97833ab53`.

Synthetic fingerprint: `e08cff69cb8cd6f10d11303757c8f811c6c78e744b8f6cf039e0c1f78bf7990b`.

The environment lock changed, so these provenance fingerprints differ from Phase 7 despite unchanged raw competition bytes and SQL ingestion checksum. Models record the file identity, raw ingestion checksum, actual Git/source hashes, registry/lock/environment identity, class/native parameters, seed/threads, trained_at/date span, expanded ordering, durations, MLflow IDs and relative artifact locations. The current source was uncommitted during verification; hashes honestly record that state. Record or retain it before claiming Git-only restoration.

## Readability, leakage and resource review

The implementation keeps CLI supervision, algorithms, dataset construction, evaluation and tracking separate. Public contracts are typed/docstringed. Date comments explain per-origin eligibility and why pre-holdout refitting cannot use July labels. Calendar-origin sampling is deterministic and recorded before target values are inspected. All labels and their availability must end within each fitting fold. Customers are absent; one-hot vocabulary and medians come only from training. Earlier-cutoff, unsupported-store, corrupted-bundle and incompatible-version requests fail visibly. Native JSON/text avoids pickle.

Named settings cap one job, two CPU threads, 2,048 MiB sampled aggregate RSS with warning at 1,536, 256 MiB available-memory floor, 600/1,800 seconds dev/full, two/three trials per family and 8,000/40,000 rows. Native work runs in a killable owned child. Publication requires successful completion and checksum/reload validation; no prior model/serving pointer is overwritten. Full-stack 8 GB use is not claimed: sampled RSS can double-count shared pages and miss brief spikes, and other services/OS are outside the worker total. Current real supervised peaks are reported above.

## Acceptance

- [x] Genuine XGBoost, LightGBM and Auto fits using one shared adapter/data contract.
- [x] Small bounded backend-only search, same chronological folds, honest baseline comparisons and no final/hidden-test tuning.
- [x] Fold-fitted preprocessing and persisted one-hot order/native models with real metrics/provenance.
- [x] CPU/RAM/time bounds, one job, dev/full modes, warnings and failure-safe candidate publication.
- [x] Local MLflow params/metrics/artifacts and run audit without UI/server/cloud dependency.
- [x] Native tests, seeded reproducibility, h=1/h=48, save/load and failure cases pass; 111 tests total.
- [x] Guides/architecture/standards/log/roadmap updated; stop before activation/API/lifecycle/final release.

Remaining limits: explicit historical availability assumptions (including known metadata/Promo2 schedules), small configured cohort, deterministic sampled origins rather than every possible row, numerical rather than cross-platform bitwise reproducibility, upstream tracking deprecation, unmeasured whole-stack RAM, and deferred serving lineage/registry/approval/final-evaluation integration. A valid tree model is not a promised accuracy improvement.

## Final repository/data checks

Business database counts remain dataset_versions=1, daily_sales=1,017,209, import_jobs=2, training_jobs=0, model_versions=0 and forecast_runs=0. CLI model files/MLflow records do not claim application activation. All 34 changed source/documentation/config files passed dataset/model/SQLite/private-path/local-credential exclusion checks, and new local documentation links resolve. DVC reports data/pipelines up to date; eight updated provenance files were synchronized to the verified out-of-repository local filesystem remote, which is in sync. No GitHub data/model upload, Git commit or Git push occurred.
