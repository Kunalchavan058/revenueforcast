# Phase 4 — PostgreSQL and ingestion verification

## Delivered
PostgreSQL 17.11 in digest-pinned Docker Compose; host-side typed SQLAlchemy business records, explicit Alembic revision, Pydantic source/request/report contracts, streaming validation, checksum-preserved local raw sources, atomic CLI ingestion and durable import audit. No features, model training, forecasting, HTTP ingestion or scheduler were implemented.

## Verified real data
| Record | Persisted count/result |
|---|---:|
| dataset_versions | 1 |
| stores | 1,115 |
| daily_sales | 1,017,209 |
| forecast_inputs | 41,088 |
| import_jobs | 2: succeeded then duplicate |
| training_jobs / model_versions / forecast_runs / forecast_points | 0 each |
| actual Sales after 2015-07-31 | 0 |
| dataset available_through | 2015-07-31 |
| test Open values retained NULL | 11 |

The second full import reused the same dataset ID rather than inserting another version. sample_submission's 41,088 placeholders were validated/preserved as source only, not inserted as actuals or predictions. Source diagnostics include 172,817 closed train rows and 54 open rows with zero Sales. Raw copies/reports and credentials remain ignored.

## Commands and outcomes
Commands run from the repository root with the existing portable Node 22 prepended for npm commands.

| Command | Outcome |
|---|---|
| uv run python scripts/configure_database.py | Private random local settings generated; no credentials printed |
| docker compose --env-file .env -f infra/compose.yaml up -d --wait | Healthy PostgreSQL container; host API/web unchanged |
| uv run alembic revision --autogenerate -m 'initial business and ingestion schema' | Explicit revision generated and reviewed/formatted |
| uv run alembic upgrade head | Applied 52b92c66f920 |
| uv run alembic current | 52b92c66f920 (head) |
| uv run alembic check | No new upgrade operations detected |
| uv run python -m retailforecast.data.import_rossmann --dry-run --report data/processed/initial-validation.json | All four actual files validated; no database publication |
| uv run python -m retailforecast.data.import_rossmann --report data/processed/import-result.json | succeeded; full real data committed |
| Same CLI with --report data/processed/reimport-result.json | duplicate; original dataset reused |
| SQLAlchemy count/boundary queries | Counts above match; test labels never entered actuals |
| uv run python -m pytest -q | 25 passed, no skips or warnings after fixes |
| uv run python -m mypy | Strict check passed for 24 source/migration files |
| Ruff lint/format | Passed after formatting generated migration and fixing callback/name issues |
| uv lock --check | Resolved lock consistent |
| npm run format / npm run check | Passed: Ruff, ESLint, formatting, strict mypy/TypeScript, 25 Python + 5 frontend tests |

Tests include six real PostgreSQL integration cases using disposable generated schemas: duplicate import, failed-publication rollback plus retained audit, broken-input rejection, active-model uniqueness, migration downgrade/upgrade round-trip, and concurrent duplicate imports. Seventeen source-validation cases cover missing columns/downloads, invalid dates/numerics, numeric coercion, closed-store quirks, duplicates, test label prohibition, template IDs, stable identity and bounded report examples; two API tests remain passing. No SQLite substitutes or silent skips.

## Files created
- alembic.ini
- infra/compose.yaml
- infra/migrations/env.py
- infra/migrations/script.py.mako
- infra/migrations/versions/52b92c66f920_initial_business_and_ingestion_schema.py
- scripts/configure_database.py
- src/retailforecast/storage/database.py
- src/retailforecast/storage/models.py
- src/retailforecast/data/contracts.py
- src/retailforecast/data/validation.py
- src/retailforecast/data/ingestion.py
- src/retailforecast/data/import_rossmann.py
- tests/conftest.py
- tests/rossmann_fixtures.py
- tests/test_validation.py
- tests/test_ingestion_postgres.py
- docs/DATA_DICTIONARY.md
- docs/INGESTION.md
- docs/decisions/0005-historical-ingestion-and-schema.md
- docs/PHASE_04_REPORT.md

Updated .env.example, .github/workflows/checks.yml, pyproject.toml, uv.lock, README.md, infra/README.md, docs/ARCHITECTURE.md, docs/DATA_FLOW.md, docs/CODING_STANDARDS.md, docs/ROADMAP.md and docs/IMPLEMENTATION_LOG.md. Generated local .env, raw copies, reports, caches and database volume are not source files. Existing downloaded CSVs were not modified. No frontend application code was changed.

## Decisions, review and limits
Business tables contain records/metadata and artifact references, never serialized models. The extra forecast_inputs table physically excludes labels. Forecast point provenance is normalized through forecast_runs. Active uniqueness is enforced per explicit scope, while serving-slot generations/audit and lifecycle execution remain future work. A separate MLflow database is deferred until its consumer exists, as documented in decision 0005.

Reviewed meaningful names, explicit types, module boundaries, public docstrings and explanatory transaction/cutoff comments. No engineered Features exist, so feature leakage tests remain future work; source label separation and availability assumptions are verified/documented now. Raw copy checks prevent changed source bytes from being published under the wrong hash. Snapshot identity is unchanged by a later validation maximum date. Every batch stays inside one business transaction, with failure audit recorded afterward.

Limitations: availability is a declared historical simulation assumption; no live data feed. Validation uniqueness keys use memory proportional to row count. Process death may leave a stale validating/running audit even though PostgreSQL rolls back data; safe retry is available. Docker volume/raw files need backups. Linux CI is defined but has not run remotely. No full ML-stack 8 GB memory or accuracy claims. The full real import was not downgraded; migration round-trip touched only disposable test schemas.

## References used for implementation
- [SQLAlchemy ORM bulk insert contracts](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html)
- [Alembic migration tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Official PostgreSQL container documentation](https://hub.docker.com/_/postgres)

## Completion checklist
- [x] Actual CSV headers/records inspected; no fabricated download or labels.
- [x] PostgreSQL healthy in Compose, while API/web/ingestion remain host-side.
- [x] SQLAlchemy models, explicit migration and schema parity verified.
- [x] Reproducible full real ingest plus duplicate reimport verified.
- [x] Validation reports, raw provenance and transaction rollback covered.
- [x] Concurrent idempotency, missing columns, dates, numerics, closures and migration round-trip tested.
- [x] Full combined quality check passed: 25 Python and 5 frontend tests; no skips.
- [x] Final decimal-alias readability refactor rechecked with Ruff, strict mypy and all 25 Python tests.
- [x] Data dictionary, setup, architecture refinements, standards, roadmap and journal updated.
- [x] No model training, feature implementation, forecasts, commit or push; stop after Phase 4.

PostgreSQL remains running with the imported snapshot. Existing API/web services were not stopped. Production web/browser tests were not repeated for this database-only phase because frontend/API application code did not change; their Phase 3 verification remains recorded separately.
