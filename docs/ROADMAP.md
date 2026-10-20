# Phased roadmap

Only the current user-authorized phase may be implemented. Later phases below are proposed, not authorization.

## Phase 1 â€” Engineering rules and product definition
- [x] Root AGENTS.md with permanent rules and completion review.
- [x] Living coding standards with concrete examples and temporal provenance rules.
- [x] Product specification and Given/When/Then acceptance criteria.
- [x] Scope decision, development journal, roadmap, and honest README.
- [x] Documentation consistency and file existence review.
- [x] Stop without architecture, scaffolding, package installation, or model training.

## Proposed later phases
- [x] Architecture, diagrams, resource budgets, and detailed design decisions (Phase 2).
- [x] Phase 3 repository/tooling and runnable API/web skeleton; infrastructure integration remains deferred.
- [x] Historical data contracts, validation and transactional ingestion (Phase 4).
- [x] Dataset file versioning and reproducible preprocessing (Phase 5).
- [x] Forecast feature availability and information-cutoff tests (Phase 6).
- [x] Rolling-origin evaluation, deterministic baselines and reproducible score artifacts (Phase 7).
- [x] CPU XGBoost/LightGBM/Auto training, bounded tuning and local MLflow (Phase 8).
- [x] Model registry/active-model reuse and forecast API/persistence (Phases 9-10).
- [ ] Forecast UI, explanations, exports, and run/version history.
- [x] Durable training jobs, explicit new-label ingestion, minimal training onboarding and optional local schedules (Phase 11).
- [ ] End-to-end acceptance, resource checks, demo, and portfolio documentation.

## Phase 2 â€” Architecture and visual explanations
- [x] Architecture, data flow, lifecycle, and diagram style guide.
- [x] D1â€“D5 editable Mermaid with story, steps, inputs, outputs, and errors.
- [x] Stack/process and storage/registry decision records.
- [x] Planned API/entity contracts and persistence/recreation table.
- [x] Direct cutoff-safe forecasting, CPU limits, optional schedules, rollback.
- [x] Static documentation/readability review; rendering gap recorded in journal.
- [x] Stop without application code, scaffolding, packages, or training.

## Phase 3 â€” Runnable monorepo skeleton
- [x] Requested directories and single installable Python domain root.
- [x] FastAPI /api/v1/health, typed frontend connection states and retry.
- [x] Next.js App Router, React, strict TypeScript, Tailwind, shadcn/ui primitive.
- [x] Locked dependencies, safe env template, dataset/model/cache ignore rules.
- [x] Cross-platform commands, starter CI, exact onboarding and phase report.
- [x] Lint, formatting, strict types, 2 API tests and 5 component tests passed.
- [x] Production build and 2 real Edge browser integration tests passed.
- [x] Readability/docs review; no ML implementation, commits or push.
- [x] PostgreSQL infrastructure and migrations delivered in Phase 4; DVC delivered in Phase 5; MLflow delivered in Phases 8-9.
- [x] Stop at the runnable scaffold.

## Phase 4 â€” PostgreSQL, data contracts and ingestion
- [x] Actual Rossmann columns/records inspected and source contracts defined.
- [x] Digest-pinned Docker Compose PostgreSQL, host-side app processes.
- [x] Minimal normalized SQLAlchemy entities and explicit Alembic migration.
- [x] Separate unlabeled inputs, metadata-only model references and one-active scope constraint.
- [x] Validate-first/dry-run CLI, bounded diagnostic reports and local raw provenance.
- [x] Full atomic real import and idempotent reimport; verified persisted counts.
- [x] Real PostgreSQL tests for rollback, duplicate/concurrent publication and migration round-trip.
- [x] All quality gates passed: 25 Python tests plus 5 frontend component tests.
- [x] Data dictionary, onboarding, design decisions, standards and journal updated.
- [x] Readability/types/docstrings/comments and source-label boundaries reviewed.
- [x] Stop before feature generation, model training, prediction or scheduling.

## Phase 5 â€” Dataset file versioning and reproducible processing
- [x] DVC initialized with portable shared settings and a private local remote outside Git.
- [x] One data configuration, synthetic-only fixture and validate/normalize/manifest stages.
- [x] Real source pointers, typed bounded-batch Parquet and inspectable provenance manifests.
- [x] Forced rebuild produces identical fingerprints; changed-input and stale-artifact tests pass.
- [x] Local remote synchronized; checkout and manifest verification succeed; DVC status clean.
- [x] 36 Python tests, Ruff, formatting, strict mypy and lock checks pass.
- [x] Beginner/engineer guide, storage boundaries, standards and phase report updated.
- [x] Raw CSV, Parquet, credentials, cache and absolute local remote paths remain ignored.
- [x] Stop before features, training, new API/UI endpoints or scheduling.

## Phase 6 — Feature registry and direct multi-horizon datasets
- [x] Actual CSV columns re-inspected and current engineering/data policies reviewed.
- [x] Single generated registry with source, type, derivation, missingness, availability, lineage, risk and serving contracts.
- [x] Shared per-store builder, exact cutoff lags, inclusive windows and aligned separate labels for horizons 1..48.
- [x] Explicit as-of metadata/plans, no Customers predictors and unknown future flags preserved.
- [x] Bounded verified Parquet adapter and inspect CLI with availability provenance.
- [x] Training-only fitted preprocessing saved/reloaded with stable ordering and unknown-category handling.
- [x] Future mutation/erasure, h=1/48, missing rows, Sunday, store isolation, cold-start and label-alignment tests pass.
- [x] Worked real row, generated reference, coding standards and phase report documented.
- [x] Stop before estimator training, scoring runner, model lifecycle or forecast API/UI.

## Phase 7 — Honest baselines and rolling-origin evaluation
- [x] Algorithm-independent fit/predict contracts with physically available history and shared feature inputs.
- [x] Last-known, last-observed weekday and historical weekday-average baselines, including h=48.
- [x] Disjoint expanding-origin development folds and a reserved final holdout.
- [x] MAE/RMSE/RMSPE with zero exclusions, real business totals and common-support coverage.
- [x] Per-fold/store/horizon/open-context/week/month metrics and JSON/Parquet provenance.
- [x] Bounded CLI, frozen selection and once-only final release with verified cached repeats.
- [x] Hand-calculated, future mutation, synthetic CLI and byte-reproducibility tests pass.
- [x] Real three-store development study rerun byte-identically; real final holdout left unscored.
- [x] Model strategy, design decision, standards, guide/status and implementation report updated.
- [x] Stop before advanced-model training, forecast serving, UI/API or lifecycle services.

## Phase 8 — Bounded CPU model training
- [x] Shared native XGBoost/LightGBM fit/predict/save/load/capability interfaces.
- [x] Shared cutoff-safe supervised examples with horizon, fold-fitted preprocessing and persisted one-hot ordering.
- [x] Same chronological development folds and baselines; eligibility-based Auto without final/hidden-test tuning.
- [x] Backend-only bounded search settings, explicit dev/full cohort/history scope and deterministic sampling metadata.
- [x] One training lock, two CPU threads, warning/hard memory thresholds and externally enforced elapsed limits.
- [x] Local SQLite MLflow parent/trial logging with actual parameters, metrics and artifacts.
- [x] Native serialization, version/checksum/cutoff/coverage guards and safe failed-job publication behavior.
- [x] Real Auto/XGBoost/LightGBM dev and LightGBM full commands produce fitted models with measured scores.
- [x] Real final holdout remains excluded from both training labels and evaluation.
- [x] All 111 tests pass; typing, lint/format, registry and lock checks pass; data provenance rebuilt for new lock.
- [x] Guides, design decision, phase report, architecture/data/status and journal updated.
- [x] Stop before API/UI model use, durable queue, model activation, scheduling or final-holdout release.


## Phase 9 - PostgreSQL MLflow and checked model lifecycle

- [x] Separate local MLflow PostgreSQL database/login, private provisioning and CI onboarding.
- [x] Native artifacts remain files; sealed app versions reference MLflow runs and registered versions.
- [x] Candidate/active/rejected/archived roles, global generation-checked pointer and transactional audit.
- [x] Shared-window comparison with original cutoff-fitted validation models, preserved final holdout and explicit missing-evidence approval.
- [x] Checked rollback, retained artifacts and immutable request pinning.
- [x] Typed CLI/API list/inspect/activate/rollback contracts and schema/cutoff/load protection.
- [x] Real PostgreSQL concurrency, migration, failure, artifact, rollback and tracking tests.
- [x] Latest full suite: 130 passed, 1 visible upstream warning; strict typing, lint, registry, lock and DVC checks pass.
- [x] Corrected selection: fresh same-budget Auto comparison selected LightGBM, now active; no pending approval; final holdout unscored (see validation fix report).
- [x] Lifecycle guide, architecture/contracts, decision, report and journal updated.
- [x] Stop before forecast execution/UI, durable queue, scheduler or final release; no commit/push.


## Correction - Preserve validation evidence across final refits

- [x] Retain/seal original cutoff-fitted models and link them to the final recipe/refit.
- [x] Re-score matched historical predictions; never evaluate final weights backward.
- [x] Recover existing registrations idempotently and record exact comparison basis/policies.
- [x] Fresh full-mode Auto study: six genuine trials, shared budget/windows and baselines; LightGBM selected and refitted.
- [x] Measured winning LightGBM activated automatically; old XGBoost archived and prior duplicate candidate resolved.
- [x] 130 tests pass, including promotion, final-weight misuse, cutoff, corruption and recovery regressions.
- [x] Current guide/design/report corrected; locked final holdout remains unscored; no commit/push.

## Phase 10 - Saved-model prediction API

- [x] Typed/OpenAPI health, dataset status, paged/searchable stores, active/version list, forecast create/replay/CSV and feature-registry routes.
- [x] Verified native model/preprocessing pinned per request; no training, fitting or automatic registration.
- [x] SQL source/model lineage and physical observation/availability cutoff projection; Customers excluded.
- [x] Explicit known-future scenarios, unknown defaults, trained-through and source-date guards.
- [x] Atomic run context/daily point persistence, exact decimal totals and metadata-rich CSV; stable retrieval after switches.
- [x] 1/7/48-day output, determinism, future mutation/erasure, unknown categories, missing history, rollback, corruption and active-switch tests.
- [x] All 164 Python cases verified across full/targeted corrected runs; five web component tests, lint/format/types, schema, lock, registry and DVC checks pass.
- [x] Actual active LightGBM HTTP smoke passed; 167 points saved without training/source/model state changes.
- [x] API guide, generated schemas, actual response, decision, standards, architecture/data contracts, report and journal updated.
- [x] Final holdout remains unscored; no raw CSV/model/secret publication and no commit/push.
- [x] Stop before forecast UI, durable training jobs, scheduling, cross-lineage adoption or final release.

## Phase 11 - Durable training jobs and optional local retraining

- [x] Typed nonblocking enqueue/status/queued-cancel APIs and six-state durable queue.
- [x] One standalone scheduler/worker, one-running constraint, fenced owned children, heartbeat, restart recovery and bounded attempts.
- [x] Idempotent manual/weekly/monthly/quarterly schedules with timezone/calendar anchors and audited downtime coalescing.
- [x] Unchanged-source watermark guard records a skip without fitting or creating a model version.
- [x] Validated append-only observed-actuals CLI with provenance, transactional child publication, idempotency and rollback.
- [x] Fresh forecasts follow only certified descendants while retaining active weights and cutoff-safe saved feature context.
- [x] Later fits exclude the complete protected final interval from fitting history and reuse controlled development windows.
- [x] Checked candidate publication/promotion remains independent of job success; incumbent forecasts survive failed training.
- [x] Honest no-model/queued/active/offline onboarding; browser polling reads status only.
- [x] Real PostgreSQL/native tests, complete 186-case Python suite, frontend/component/browser/build and static quality checks.
- [x] Migration head/schema verified; original real source, model pointer and final-holdout reservation preserved.
- [x] Operator guide, current contracts/diagrams, decision 0013 and Phase 11 report/log updated.
- [x] Stop before full forecast/settings UI, schedule-performance replay, unrelated-lineage migration or final release; no commit/push.
