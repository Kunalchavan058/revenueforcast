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
- [ ] CPU models and bounded advanced-model training.
- [ ] Training lifecycle, active-model reuse, API, and persistence.
- [ ] Forecast UI, explanations, exports, and run/version history.
- [ ] Explicit new-label ingestion and optional local retraining schedules.
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
- [x] PostgreSQL infrastructure and migrations delivered in Phase 4; DVC delivered in Phase 5; MLflow remains future integration.
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
