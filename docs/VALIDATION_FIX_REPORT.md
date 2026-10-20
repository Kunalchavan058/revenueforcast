# Corrected chronological validation and model promotion

Date: 2026-10-20. Status: fixed, executed on the real local dataset and verified.

## Problem and correction

There was sufficient labeled historical data. The lifecycle check incorrectly tried to evaluate final refitted weights on the earlier development windows, while registration omitted the original fold models that supplied valid chronological validation. That was an implementation error, not a missing-data problem.

Registration now preserves and seals the selected trial's original per-cutoff native models/preprocessing, tied to its exact final refit, parameters, seed, dataset/feature protocol and sampling policy. Promotion regenerates both recipes' predictions using the correct model fitted at each validation cutoff, joins truth afterward, compares identical target keys and metrics, and activates the corresponding final refit only if it wins. It never sends earlier validation features to later final weights or consumes final-holdout outcomes. Legacy evidence recovery is idempotent/audited; new registrations retain evidence automatically.

## Actual controlled training and selection

Executed:

```text
uv run --locked python -m retailforecast.training.train --algorithm auto --mode full --output artifacts/training/phase09-corrected-auto-full
```

Both families received the same full-mode dataset/history/row policy, feature matrices, cutoffs, 1..48 horizons, seed and CPU/resource budget. All six configured trials completed, alongside three baselines. The selected recipe was **lightgbm_trial_3**. The workflow compared validation results before refitting the winner through **2015-06-13**. The final June 14..July 31 dates remain unscored.

| Trial | Mean development-fold RMSPE |
|---|---:|
| xgboost_trial_1 | 0.21030145137331746 |
| xgboost_trial_2 | 0.2036958954327295 |
| xgboost_trial_3 | 0.19902321274183202 |
| lightgbm_trial_1 | 0.20994829894762254 |
| lightgbm_trial_2 | 0.20231365243175528 |
| **lightgbm_trial_3** | **0.1978861738893034** |

These are actual computed model-selection validation metrics; lower is better. They are neither Kaggle hidden-test scores nor unbiased final-holdout performance. Each trial uses 432 validation predictions: 3 stores x 3 chronological origins x 48 horizons. Selected fold models were fitted at 2015-01-20, 2015-03-09 and 2015-04-26, before their respective targets. Configured training scope remains stores 1,2,3, not all 1,115 stores.

The supervised job recorded 95.125 seconds and peak process-tree RSS 344.703125 MiB, with no memory warning. This is measured training-process usage, not total laptop memory. Artifacts and PostgreSQL-backed MLflow logs are under the ignored local artifact tree; source CSVs were not changed or published.

## Actual promotion and live state

Recovered the original fold evidence for the previous XGBoost and pending LightGBM registrations. Registered the new controlled Auto winner as application model **c0e51310-98a8-4c34-afd9-ca658fbcd468**. The corrected promotion path re-scored matched historical models and produced these mean-fold RMSPE values:

- New full-mode LightGBM recipe: **0.1978861738893034**.
- Previous dev-mode XGBoost recipe: **0.2168122628207466**.

That operational comparison discloses both recipes' different sampling/history policies. The separate fresh Auto study above is the controlled same-budget algorithm comparison. Neither comparison uses final refitted weights to predict backward.

The new **LightGBM version is active at generation 2**, without an approval override. XGBoost is archived and retained for rollback. The older pending LightGBM version was re-scored against the new champion and rejected as a tie/duplicate recipe, so no pending approval remains. This does not label the LightGBM algorithm worse; a newer version of that algorithm is the active winner.

Actual paired predictions/segments are saved as JSON/Parquet under the new model's comparisons directory and linked in application evidence, including recipe fingerprints, policies, validation basis and report hash. The promotion report is also logged to its MLflow run. A previously pinned XGBoost prediction stayed unchanged across the switch. Active LightGBM loads and predicts at horizons 1 and 48, and API inspection reports the new pointer.

No final-release claim was created. Business source data remain 1 dataset version, 1,115 stores and 1,017,209 actual rows. There are now 3 model versions; exactly 1 is active. Private verification details are in artifacts/phase09-verification/corrected-validation.json.

## Validation

- Full `python -m pytest -q`: **130 passed**, 1 existing unsuppressed MLflow/SQLAlchemy warning, 119.64 seconds.
- Focused lifecycle suite before final integrity additions: 16 passed; the complete suite includes those and additional corrupt-fold tests.
- Strict mypy: **70 source files**, no issues.
- Ruff lint: all checks passed; Ruff format: 109 files already formatted.
- Alembic check: no new upgrade operations; no new database migration was needed for JSON evidence fields.
- Dependency lock: 148 resolved packages, unchanged; DVC data/pipeline status current.

Regression checks prove: later final weights never make historical validation predictions; every retained model's fit cutoff equals its evaluation origin; no scored target enters the reserved final period; actual measured winners promote without overrides; ties reject without pending approval; missing legacy evidence can be recovered idempotently; swapped future-fitted/corrupted fold models cannot activate; pinned predictions and rollback/concurrency guarantees remain intact.

## Changed files and review

Code: src/retailforecast/lifecycle/validation.py (new); comparison.py, registry.py and manage.py; src/retailforecast/evaluation/artifacts.py (include lifecycle source hashes in comparison provenance); tests/test_model_lifecycle.py.

Documentation: README.md, docs/CODING_STANDARDS.md, MODEL_LIFECYCLE.md, ARCHITECTURE.md, TRAINING.md, PHASE_09_REPORT.md (historical-status notice), ROADMAP.md, IMPLEMENTATION_LOG.md, this report and decisions 0010/0011.

Reviewed explicit typed contracts, focused artifact/comparison modules, named minimum-fold policy, actionable failures and comments explaining why validation fits differ from final refits. Shared feature/scoring code remains authoritative; no duplicate business metrics or Customers predictors were added. Old files, SQL audit and model bytes remain intact. No commit/push, new service, frontend workflow, scheduler or final evaluation was introduced. The existing conservative same-data-context/schema/cohort compatibility policy remains; complete forecast UI/API work is still outside this correction.
