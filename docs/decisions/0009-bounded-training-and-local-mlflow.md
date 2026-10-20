# 0009 — Bounded CPU training and local MLflow metadata

## In plain English

Models must learn from genuine cutoff-safe examples, not from held-out answers. A laptop needs small internal searches, one training job and a way to stop native fitting when resources are exhausted. Saving a fitted model does not activate it for the application.

Date: 2026-10-20. Status: implemented Phase 8.

## Decision

Use one pooled direct regressor with horizon and the existing shared features. Fit preprocessing per chronological fold; one-hot categorical IDs using saved training vocabularies for both native XGBoost/LightGBM adapters. Bound origin/row selection before looking at label values. Search a small deterministic internal grid, compare identical development folds and baselines, select eligible tree candidates by mean fold RMSPE/MAE/name, then refit only through the reserved final origin. Keep the actual final holdout unscored.

A supervised subprocess and cross-platform file lock enforce one job, CPU threads, sampled process-tree RSS and wall-clock limits. Stage a candidate and verify reload before coordinator publication. Failed trials/runs remain audited; no fallback to an unrequested model family/baseline or active-model replacement is allowed. Exact per-horizon metrics supplement existing reporting buckets.

## MLflow backend refinement

Decision 0003 planned PostgreSQL for a future concurrent MLflow service. This single-writer CLI uses the lightweight MLflow client and ignored local SQLite metadata/artifact directories, without an additional service/database in Docker. That is sufficient for experiment/run/parameter/artifact logging now and leaves business PostgreSQL unchanged. SQLite is not a future multi-user service guarantee. Model files remain outside database rows. MLflow registry aliases, transactional serving pointers and application lifecycle execution stay deferred.

## Trade-offs and compatibility

Fixed small searches favor auditability/resource control over exhaustive tuning. Full mode means full historical coverage within the explicitly configured cohort, not all 1,115 stores. Weekly/fortnightly origin grids are deterministic samples, recorded with any row cap. Baselines may outperform fitted models; show that honestly. Timings are logged but not used for hardware-sensitive ties.

The local 4.7.0 LightGBM Windows native build failed a minimal fit; the tested 4.6.0 pin is used. Native JSON/text formats avoid pickle but require pinned library compatibility. Sampled RSS can miss spikes and is not an OS memory sandbox. SQLAlchemy emits a known upstream MLflow deprecation warning; tracking/reload tests pass without suppressing it. Later whole-stack memory checks, advanced search, model approval/API use and final evaluation remain separate phases.
