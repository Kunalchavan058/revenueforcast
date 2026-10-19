# Phased roadmap

Only the current user-authorized phase may be implemented. Later phases below are proposed, not authorization.

## Phase 1 — Engineering rules and product definition
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
- [ ] Forecast feature availability and information-cutoff tests.
- [ ] Temporal evaluation, baseline, CPU models, and reproducible artifacts.
- [ ] Training lifecycle, active-model reuse, API, and persistence.
- [ ] Forecast UI, explanations, exports, and run/version history.
- [ ] Explicit new-label ingestion and optional local retraining schedules.
- [ ] End-to-end acceptance, resource checks, demo, and portfolio documentation.

## Phase 2 — Architecture and visual explanations
- [x] Architecture, data flow, lifecycle, and diagram style guide.
- [x] D1–D5 editable Mermaid with story, steps, inputs, outputs, and errors.
- [x] Stack/process and storage/registry decision records.
- [x] Planned API/entity contracts and persistence/recreation table.
- [x] Direct cutoff-safe forecasting, CPU limits, optional schedules, rollback.
- [x] Static documentation/readability review; rendering gap recorded in journal.
- [x] Stop without application code, scaffolding, packages, or training.

## Phase 3 — Runnable monorepo skeleton
- [x] Requested directories and single installable Python domain root.
- [x] FastAPI /api/v1/health, typed frontend connection states and retry.
- [x] Next.js App Router, React, strict TypeScript, Tailwind, shadcn/ui primitive.
- [x] Locked dependencies, safe env template, dataset/model/cache ignore rules.
- [x] Cross-platform commands, starter CI, exact onboarding and phase report.
- [x] Lint, formatting, strict types, 2 API tests and 5 component tests passed.
- [x] Production build and 2 real Edge browser integration tests passed.
- [x] Readability/docs review; no ML implementation, commits or push.
- [x] PostgreSQL infrastructure and migrations delivered in Phase 4; MLflow/DVC remain future integration.
- [x] Stop at the runnable scaffold.

## Phase 4 — PostgreSQL, data contracts and ingestion
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
