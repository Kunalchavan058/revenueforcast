# Implementation log

## 2026-10-19 — Phase 1: product and engineering documentation
Created engineering rules, coding standards, product specification, roadmap, scope decision, and starter README. Established historical 1–48-day forecasts, saved-model reuse, temporal leakage prevention, CPU-first operation, and optional retraining only after explicit new-label ingestion.

Decision: keep this phase documentation-only. Architecture, dependency selection/pinning, code scaffolding, models, and tests remain future authorized work. No application runtime commands or training were run. Checked required documents, acceptance statements, and Git status. Code readability review: not applicable to executable changes; illustrative examples reviewed for clarity.

Existing environment notebook, local .venv, ignored dataset, and .gitignore predate this phase and were preserved. Application implementation has not begun. Open risks include local 8 GB resource use, bounded Auto search, feature availability, scheduler downtime, dataset licensing/access, and model compatibility/promotion policies.

## 2026-10-19 — Phase 2: architecture
Created ARCHITECTURE.md, DATA_FLOW.md, MODEL_LIFECYCLE.md, DIAGRAM_STYLE_GUIDE.md and decisions 0002/0003. Added D1–D5 with explanations, planned API/entities, direct horizon-aware forecasting, separate worker, immutable artifacts, transactional serving pointers, MLflow/DVC roles, recovery, and local scheduling. Updated AGENTS, README, coding standards, and roadmap.

Trade-offs: PostgreSQL queue avoids extra distributed infrastructure; split serving/registry authority requires reconciliation. CPU budgets need measurement on 8 GB hardware. Historical availability assumptions are explicit, promotion inputs remain non-causal, and future actual Sales/Customers cannot enter predictors. No application code, scaffolding, services, installations, or training. An initial oversized shell write failed before execution; smaller documentation writes succeeded.

Review: engineering/product/scope documents read; static coverage, links, diagrams and temporal/storage contracts checked. Documentation readability reviewed; runtime types/docstrings/comments review is not applicable to this documentation-only phase. CLI/rendering availability and final static results follow below. Remaining risks: memory, renderer compatibility, historical availability, recovery across stores, and dependency pins. Stop at this phase.

Final verification: Python static document checks passed (exit 0): six new design documents start with In plain English; exactly five Mermaid blocks have balanced fences and required story/steps/inputs/outputs/errors; all local Markdown links resolve. Mermaid CLI was not installed (PATH and local node_modules checks), so rendering/visual layout remain unverified and no rendered images were generated. No application tests were run because no application code changed. Phase 2 documentation is complete; rendering review remains an explicit validation gap.


## 2026-10-19 — Phase 3: runnable monorepo skeleton
Implemented the Next.js/React/TypeScript/Tailwind/shadcn UI foundation, typed health client and real API status states; FastAPI GET /api/v1/health; one installable src/retailforecast package with empty domain boundaries; uv/npm exact dependencies/locks; quality tooling, CI, and cross-platform command supervisor. Added safe configuration/ignore rules and raw/processed/artifact directory markers while preserving local data.

Verification complete: npm run check passed (Ruff, ESLint, formatting, strict mypy/TypeScript, 2 pytest tests and 5 component tests); production build passed; 2 Edge browser integration tests passed against temporary real local API/web servers, including loading/offline/retry. Health schema and rendered screenshot inspected. Full and production dependency audits report zero vulnerabilities. Lock consistency and Git ignore exceptions checked. No skips used.

Design/readability review: one domain package root; top-level service adapter; same-origin API proxy; two logical dev services; documented typed boundaries and public functions. Current lint/test requirements required portable Node 22.23.3, checksum verified, leaving system Node unchanged. Replaced vulnerable lint preset dependencies and aligned Vite types; no bypasses. Initial broad Ruff formatting touched the legacy experiment notebook, now excluded; no new notebook logic or ML implemented.

See PHASE_03_REPORT.md for exact files, commands/results, corrections and limitations. Updated roadmap, README, architecture and standards. Linux/Chromium CI and full 8 GB stack usage remain unverified. No imports, models, worker, database, forecasts, commit, or push. Stop after Phase 3.


## 2026-10-19 — Phase 4: PostgreSQL and historical ingestion
Implemented digest-pinned PostgreSQL 17.11 in Compose; host-side SQLAlchemy models, Alembic revision 52b92c66f920, Pydantic source/request/report contracts, private local database configuration, streaming validation and atomic CLI ingestion. Added separate unlabeled forecast_inputs, normalized forecast provenance, partial active-model scope uniqueness, provenance reports and local raw-file preservation. No MLflow backend was created because no current consumer warrants it; decision 0005 documents this refinement.

Real source validation and full import succeeded: 1,017,209 daily_sales, 41,088 unlabeled inputs and 1,115 stores. Reimport returned duplicate and reused the sole dataset version. available_through is 2015-07-31, with no later actuals, no models, no training jobs and no forecasts. Source quirks are preserved: 54 open zero-Sales rows and 11 test Open NULL values. Original source files were not modified.

Verification: Alembic head/current and schema check passed; migration downgrade/upgrade ran only in disposable test schemas. Six real PostgreSQL integration cases include failure rollback/audit, sequential/concurrent duplicates, rejection, uniqueness and migration round-trip. All 25 Python tests and 5 frontend tests passed without skips; Ruff, ESLint, formatting, strict mypy (24 source/migration files), TypeScript and lock consistency passed. The final shared decimal type-name clarification was rechecked with Ruff/mypy/all Python tests. No frontend/API application code changed; no additional production build/browser repeat was needed.

Readability review covered explicit typed contracts, public docstrings, transaction ownership, meaningful names, bounded batches/reports, historical date semantics and label separation. Data dictionary, ingestion guide, architecture/data-flow refinements, coding standards, README, CI and roadmap updated. PHASE_04_REPORT.md records exact files, commands/results and completion checklist. Remaining limits: historical availability assumptions, memory proportional to uniqueness keys, stale audit after process death, local backup requirements, unrun remote Linux CI and deferred MLflow/DVC/features. PostgreSQL remains running; existing host services preserved. No commit or push. Stop after Phase 4.
