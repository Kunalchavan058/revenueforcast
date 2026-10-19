# Phase 6 — Feature registry and leakage-safe datasets

## Completion status

Complete. One shared as-of builder supplies training, backtesting and inference feature rows, with aligned labels attached separately. No estimator was trained; no forecast API/UI, scoring runner, model lifecycle or scheduling implementation was added. Implementation was completed locally; subsequent commits are recorded in Git history.

## Exact Phase 6 files

New implementation files under the existing package root:

- `src/retailforecast/features/contracts.py`: immutable request, actual, metadata, plan, assumption and snapshot-context contracts.
- `src/retailforecast/features/registry.py`: structured single source for all feature descriptions/order and generated reference CLI.
- `src/retailforecast/features/builder.py`: per-store as-of indexes, exact calendar lags, inclusive windows, independent horizons and supervised label iterator.
- `src/retailforecast/features/preprocessing.py`: training-fold medians, missing indicators, categorical mappings, persisted order/context and compatibility guards.
- `src/retailforecast/features/snapshot.py`: verified bounded projected Parquet adapter with explicit knowledge-time assumptions.
- `src/retailforecast/features/inspect.py`: genuine one-row inspection CLI, without predictions.
- `tests/test_temporal_leakage.py` and `tests/test_feature_snapshot.py`: 30 new feature cases, including parametrizations.

New documents: `docs/FEATURE_REGISTRY.md` (generated), `docs/FEATURES.md`, `docs/decisions/0007-asof-direct-features.md`, this report.

Updated: `src/retailforecast/features/__init__.py`, `.github/workflows/checks.yml` (registry freshness), `README.md`, `docs/CODING_STANDARDS.md`, `docs/ARCHITECTURE.md`, `docs/DATA_FLOW.md`, `docs/DATA_DICTIONARY.md`, `docs/ROADMAP.md`, `docs/IMPLEMENTATION_LOG.md`.

Ignored local verification artifacts: `artifacts/features/phase06-preprocessing.json` and `artifacts/example/preprocessing.json`. These contain fitted preprocessing only, not an estimator. Existing uncommitted Phase 5 changes were preserved. No dependencies, lockfiles, raw data, migrations or database records changed in Phase 6.

## Behavior and decisions

Each row is keyed by store, cutoff and horizon 1..48; target is cutoff plus horizon. Predictor history requires both business date and availability date at/before cutoff. Lag 1 reads t-1, never target-1. Seven-/28-day rolling windows include cutoff and use only observed available dates; counts expose missing coverage. Duplicate actual keys and equal-time metadata/plan revisions fail. Full eligible plan revisions can explicitly clear old values to unknown.

Customers are excluded entirely, including historical aggregates; the adapter never loads the column. Targets are outside FeatureRow. Kaggle test rows and submission placeholders cannot supply y. Supervised iteration checks target business date and availability against training_label_end, preventing origins with later targets from leaking across fold boundaries.

Future Open/Promo/holiday flags need explicit known-time plans. Sunday does not imply closure. Promo2 requires an asserted known schedule; missing components stay unknown. Static store metadata is also gated by knowledge date. Archived files cannot prove real publication dates, so the adapter requires written assumptions and leaves target plans unknown by default. Explicit per-row revisions can be supplied directly for richer real-world knowledge histories.

The registry defines 24 predictors and generated descriptions. Training-only preprocessing produces 44 columns, preserves separate missing/unseen categorical codes, numeric missing indicators, registry fingerprint, fold label end and dataset/assumption context. Fit rejects post-fold labels and mixed contexts. Serving rejects preprocessing fitted after the requested cutoff; training has a separate bounded transform sharing identical value conversion. Save/load uses typed validated JSON, not pickle. A future estimator must persist this object in its model bundle and explicitly support the selected categorical encoding.

Registry fingerprint at completion: `ed7be458c334f08e33feabc53c068df13a9315e013327ffc41cdc0ee9380eeec`.

## Commands and verified outcomes

| Command/check | Result |
|---|---|
| Inspect first CSV header with Python csv reader | Actual train/test/store/submission columns match source contracts; test has no Sales |
| `uv run --locked pytest tests/test_temporal_leakage.py tests/test_feature_snapshot.py -q` during development | Feature-only tests passed; final cases included in the full suite below |
| `uv run --locked pytest -q` | **66 passed in 5.60 seconds**, no skips: 36 existing plus 30 feature cases |
| `uv run --locked ruff check . --fix --output-format concise` | All checks passed; imports corrected, no suppression added |
| `uv run --locked ruff format --check .` | Final check passed; 68 files already formatted, including documented Python example |
| `uv run --locked mypy` | Success, no issues in 38 source files |
| `uv run --locked python -m retailforecast.features.registry` then `--check` | Reference regenerated and freshness check passed; covered by pytest and CI |
| `uv lock --check` | 127 locked packages resolved consistently; no dependency changes |
| `uv run --locked dvc status` | Data and pipelines are up to date; Phase 5 dataset identities unchanged |
| `git diff --check` | Passed; only Git line-ending normalization notices |
| Real `features.inspect` for Store 1 / July 31 / h=7 with explicit assumptions | Values and provenance printed; worked trace matches FEATURES.md |
| Bounded real Store 1 feature iteration | Exactly 48 independent horizons through September 17 |
| Real preprocessing fit/save/reload | Eligible historical labels only; identical reloaded matrix values, 44 columns |
| Execute documented Python example | Passed; both ignored preprocessing artifacts refreshed to final registry/context schema |
| Read-only SQL count query | Dataset versions 1; daily_sales 1,017,209; import_jobs 2; models 0; forecast runs 0 |
| `git check-ignore artifacts/features/phase06-preprocessing.json` | Generated artifact excluded from Git |
| Feature guide relative-link check | All local links resolve |

An initial formatting check flagged the guide's embedded Python line wrapping; the code block was formatted and the final whole-project check passed. No tests were replaced by skips. No frontend code changed, so production web build/browser tests were not rerun. Remote GitHub CI has not run for these local changes.

## Leakage and readability review

Future mutation tests replace or erase all actuals after cutoff while fixing known plans. Predictors, persisted-preprocessor matrices and fixed arithmetic prediction probes remain identical for horizons 1, 7 and 48. These probes exist only in tests, without estimator training or published forecasts. Tests also prove July 30 lag alignment for a July 31 cutoff, inclusive-window arithmetic, missing dates, delayed observations/targets, cross-store isolation, Sunday plans, unknown stores, plan replacement/timing, metadata timing, Promo2 ISO-week/month boundaries, leap day, invalid horizons, schema drift, invalid labels and Customer exclusion across changed snapshot files.

Reviewed public docstrings/types, small module responsibilities, named caps, meaningful names, input/output errors, explicit target separation and targeted date comments. Shared calculation prevents drift across training/backtests/inference. No duplicate Python root, DataFrame shift or duplicated source business validation was introduced. Generated descriptions have an automated freshness test.

## Acceptance and limits

- [x] Registry includes explanation, source, model-input type, derivation, missing policy, availability class, lineage, leakage risk and serving requirement.
- [x] Shared direct multi-horizon rows and correct label alignment, as-of joins and missing-history policy.
- [x] Customers entirely excluded and future unknown plans never inferred as facts.
- [x] Training-only preprocessing persisted/reloaded, with fixed order and unknown handling.
- [x] Required leakage/boundary cases pass; real/synthetic worked explanations and runnable commands provided.
- [x] Roadmap, log, standards and architecture/data status updated; stopped before model implementation.

RAM is bounded by projected 10,000-row scans, at most 32 stores per adapter call, lazy example iteration and a visible 50,000-row exact-median fit cap. Index memory still scales with selected history, and whole-stack 8 GB peak memory/large training throughput has not been measured. Larger training needs a deliberate bounded fold/encoder strategy, not silent subsampling. Unknown-store fallback is deterministic, not a promise of accurate or approved coverage. Categorical codes need explicit estimator integration. Genuine historical availability cannot be proven from the archive; the written simulation policy remains a limitation. Estimator trained-through/lineage checks, scored backtests and model quality remain future work.
