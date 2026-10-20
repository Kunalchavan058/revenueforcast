# RetailForecast AI

A local-first retail forecasting application in development. **Phase 13 makes Overview and Forecasts functional:** explore imported historical actuals, then generate and export saved-model predictions for selected stores. Model Studio retains background training; other feature workflows remain explicitly planned. Historical 2015 records are not live data; no currency or operational results are invented.

## Required tools

- Python 3.11â€“3.13; 3.11 is the locally tested baseline.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for the environment and lock.
- Node.js 22.13+ with npm 10+; .node-version records the tested release.
- Docker Desktop/Engine with Compose v2 for PostgreSQL and integration tests.
- Git. No GPU, Colab, notebook kernel, Kubernetes, Redis, Celery, authentication or remote cloud account is required.

API/web and ingestion stay on the host. Only PostgreSQL runs in Compose. The shell and API-health indicator can run without Docker; database/model metadata then show unavailable states. Complete Python checks require PostgreSQL.

## Install â€” Windows PowerShell

From the repository root:

```powershell
uv sync --locked --python 3.11
npm.cmd ci
uv run python scripts/configure_database.py
docker compose --env-file .env -f infra/compose.yaml up -d --wait
uv run python scripts/configure_mlflow.py
uv run alembic upgrade head
uv run alembic check
npm.cmd run dev
```

## Install â€” bash

```bash
uv sync --locked --python 3.11
npm ci
uv run python scripts/configure_database.py
docker compose --env-file .env -f infra/compose.yaml up -d --wait
uv run python scripts/configure_mlflow.py
uv run alembic upgrade head
uv run alembic check
npm run dev
```

configure_database.py creates missing local credentials in ignored .env without printing them or replacing real settings. .env.example contains placeholders only. Changing an existing PostgreSQL password in .env does not update the password already initialized in a persistent volume. See [ingestion setup](docs/INGESTION.md).

Open http://127.0.0.1:3000 for the web app, http://127.0.0.1:8000/api/v1/health for liveness JSON and http://127.0.0.1:8000/docs for OpenAPI. PostgreSQL defaults to loopback port 5432. Ctrl+C stops the two managed dev services; infrastructure is separately managed and retains its named volume.

## Validate and import real files

Put train.csv, test.csv, store.csv and sample_submission.csv together under data/ (the existing local download is already there). No data is downloaded or fabricated automatically.

```text
uv run python -m retailforecast.data.import_rossmann --source-dir data --dry-run
uv run python -m retailforecast.data.import_rossmann --source-dir data
```

Dry run needs no database. Actual imports always validate first, preserve checksum-verified raw bytes under ignored data/raw/, and publish one immutable snapshot transaction. Repeat imports return duplicate without duplicating business records. JSON reports live in ignored data/processed/. --report chooses an output path; --min-date/--max-date control sensible date bounds. Failures return nonzero with actionable report issues; no partial dataset is published.

test.csv is unlabeled and stored separately from daily_sales. sample_submission.csv contains export placeholders, not actuals or predictions. Source Customers remain historical audit data only. Read [data dictionary](docs/DATA_DICTIONARY.md) and [transaction/setup guide](docs/INGESTION.md).

## Commands

Use npm.cmd in PowerShell if execution policy blocks npm.ps1. No virtualenv activation is required.

| Purpose                       | Root command                                                      |
| ----------------------------- | ----------------------------------------------------------------- |
| Reinstall locked dependencies | npm run setup                                                     |
| API only / web only           | npm run api / npm run web                                         |
| Both host dev services        | npm run dev                                                       |
| Start PostgreSQL              | docker compose --env-file .env -f infra/compose.yaml up -d --wait |
| Stop PostgreSQL, retain data  | docker compose --env-file .env -f infra/compose.yaml stop         |
| Apply/verify migrations       | uv run alembic upgrade head / uv run alembic check                |
| Python + frontend lint        | npm run lint                                                      |
| Apply/check formatting        | npm run format / npm run format:check                             |
| Strict mypy and TypeScript    | npm run typecheck                                                 |
| Python + component tests      | npm test                                                          |
| All quality checks            | npm run check                                                     |
| Production frontend build     | npm run build                                                     |
| Browser tests after build     | npm run test:e2e                                                  |

Normal pytest includes real business/MLflow PostgreSQL integration tests and fails if the database is unavailable; it never silently skips or substitutes SQLite. Test schemas are generated and isolated from imported data; migration downgrade/upgrade is tested only there. Source-only tests can explicitly be selected with uv run pytest tests/test_validation.py.

Browser tests require free ports 3000/8000 and a browser. Install Chromium using npm exec --workspace apps/web -- playwright install chromium. Or use installed Edge: set $env:PLAYWRIGHT_CHANNEL='msedge' in PowerShell, or prefix the bash command with PLAYWRIGHT_CHANNEL=msedge. They start/stop their own test servers. The existing dev servers must be stopped before running browser integration tests.

## Configuration and boundaries

API health returns {status: ok, service: retailforecast-api, api_version: v1}; it is liveness only, not database/model readiness. Browser requests use same-origin /api/v1 and a Next.js rewrite to API_BASE_URL, default http://127.0.0.1:8000. Root dev/web/build commands load optional .env; restart/rebuild after proxy changes. The typed client shows actual loading/connected/offline states and validates response JSON.

- apps/web/: Next.js App Router, React/strict TypeScript, Tailwind and a local shadcn/ui primitive.
- services/api/: thin health, model-lifecycle and forecast endpoints, not a second Python package root.
- src/retailforecast/: the sole installable Python package; implemented data/storage modules and reserved features/training/evaluation/forecasting/lifecycle boundaries.
- infra/compose.yaml and infra/migrations/: PostgreSQL and frozen Alembic revisions. No model bytes in business tables.
- tests/: synthetic source fixtures, API/validation tests and real PostgreSQL ingestion/migration tests. Web tests live under apps/web/.
- configs/, scripts/, .github/workflows/: configuration, host commands, setup and CI.
- data/raw/, data/processed/, artifacts/: ignored contents with eligible empty markers.

uv.lock/package-lock.json and exact direct versions pin dependencies; the PostgreSQL image is digest-pinned. Never commit .env, raw CSVs, model binaries, caches or generated reports. Existing local CSVs and the legacy colab_test.ipynb remain local/preserved; future product work uses Python modules.

## Existing Windows Node installation

The system Node 20.9 is too old for current tooling. A checksum-verified portable Node 22.23.3 is available in ignored .tools/ without changing the system installation. In this checkout, prepend it before npm commands:

```powershell
$env:Path = "$PWD\.tools\node-v22.23.3-win-x64;$env:Path"
node --version
```

Other checkouts should install Node 22.13+ themselves; .tools/ is not committed.

## Design and status

Read [AGENTS.md](AGENTS.md), [product spec](docs/PRODUCT_SPEC.md), [architecture](docs/ARCHITECTURE.md), [coding standards](docs/CODING_STANDARDS.md), [roadmap](docs/ROADMAP.md), and [journal](docs/IMPLEMENTATION_LOG.md). Design documents include future behavior beyond this phase; measured development results are documented separately from the unscored final holdout.

The public repository is [Kunalchavan058/revenueforcast](https://github.com/Kunalchavan058/revenueforcast). Next.js regenerates next-env.d.ts during dev/build/typegen; it stays local and ignored while remaining included in tsconfig.json.

## Reproducible datasets with DVC

DVC tracks artifact files/content hashes; PostgreSQL keeps transactional business records; Git tracks code/pointers; MLflow tracks experiments and model references in its own local PostgreSQL database. The local DVC remote is outside this repository and its location stays in ignored config.local.

```text
uv sync --locked
uv run python scripts/configure_dvc.py
uv run dvc repro manifest@synthetic
uv run python -m retailforecast.data.file_pipeline verify --profile synthetic
```

This synthetic-only example needs no Kaggle, database or cloud. For real data, prepare copies from data/, run dvc add data/raw/rossmann, then dvc repro manifest@rossmann. See [DATA_VERSIONING.md](docs/DATA_VERSIONING.md) for commands, manifests, comparison/restore, re-ingestion and historical-cutoff rules. CSV and Parquet must stay out of Git.

## Phase 6 — Inspect cutoff-safe features

See [FEATURES.md](docs/FEATURES.md) for synthetic-only commands, shared training/backtest/inference use, the real July 31 → August 7 trace and availability assumptions. [FEATURE_REGISTRY.md](docs/FEATURE_REGISTRY.md) is generated from the executable registry.

```text
uv run --locked pytest tests/test_temporal_leakage.py tests/test_feature_snapshot.py
uv run --locked python -m retailforecast.features.registry --check
```

Target plans are unknown unless explicitly supplied as known at cutoff. Customers never enter V1 predictors. This phase does not train an estimator or add forecast pages/endpoints.

## Phase 7 — Honest baseline backtests

[MODEL_STRATEGY.md](docs/MODEL_STRATEGY.md) explains the three baselines, rolling-origin windows, zero-sales scoring, common coverage and locked final holdout.

```text
uv run --locked python -m retailforecast.evaluation.backtest --plan-only
uv run --locked python -m retailforecast.evaluation.backtest --stage development --output artifacts/evaluation/development
```

The default is a bounded three-store, three-origin, 48-horizon study. Results are private JSON/Parquet under `artifacts/evaluation`; choose a new output directory if a run already exists. The real final holdout remains reserved and unscored. Feature/evaluation-only synthetic tests require neither Kaggle nor PostgreSQL; the full existing suite includes PostgreSQL integration tests.

## Phase 8 — Fit CPU models

See [TRAINING.md](docs/TRAINING.md) for budgets, full-mode scope, native model/preprocessing bundles, MLflow inspection and failure policies.

```text
uv run --locked dvc repro manifest@synthetic manifest@rossmann
uv run --locked python -m retailforecast.training.train --algorithm lightgbm --mode dev
uv run --locked python -m retailforecast.training.train --algorithm xgboost --mode dev
uv run --locked python -m retailforecast.training.train --algorithm auto --mode dev
uv run --locked python -m retailforecast.training.train --algorithm lightgbm --mode full
```

Users select algorithm and dev/full mode; internal tuning parameters live in `configs/training.yaml`. The current cohort is stores 1,2,3, not all Rossmann stores. The final real holdout remains unscored. Saved candidates and experiment files stay ignored under `artifacts/`; training alone does not activate them; Phase 9 supplies explicit checked lifecycle commands. Phase 10 now serves saved active models through the forecast API.

## Phase 9 - Track and approve model versions

After starting PostgreSQL, provision MLflow's separate database/login before running training:

```text
uv run --locked python scripts/configure_mlflow.py
uv run --locked alembic upgrade head
uv run --locked python -m retailforecast.lifecycle.manage list
uv run --locked python -m retailforecast.lifecycle.manage slot
```

[MODEL_LIFECYCLE.md](docs/MODEL_LIFECYCLE.md) gives exact register/inspect/activate/rollback commands and API contracts. Model binaries/preprocessing remain in ignored local files, never PostgreSQL. Existing SQLite experiments are retained; new tracking defaults to PostgreSQL. A generation token prevents concurrent overwrites. Later candidates are compared using sealed original chronological validation models, then the winning final refit can activate automatically. Manual approval is reserved for genuinely missing evidence; the real final holdout stays locked. Current models cover stores 1,2,3 only. [PHASE_09_REPORT.md](docs/PHASE_09_REPORT.md) records actual verification and remaining limits.

The corrected workflow is verified in [VALIDATION_FIX_REPORT.md](docs/VALIDATION_FIX_REPORT.md): historical fold models supply validation evidence even after the serving model is refitted. To run a fresh controlled comparison and refit, use `uv run --locked python -m retailforecast.training.train --algorithm auto --mode full`.

## Phase 10 - Predict without retraining

[API_CONTRACT.md](docs/API_CONTRACT.md) documents every endpoint, request/result/failure example, historical cutoffs, scenario availability, decimal precision, CSV and limits. Start `npm run api`, then open http://127.0.0.1:8000/docs. Apply `uv run --locked alembic upgrade head` first. Inspect `/api/v1/datasets/status`, `/api/v1/stores` and `/api/v1/models/active`, then POST `/api/v1/forecasts`:

```json
{ "store_ids": [1, 2, 3], "cutoff_date": "2015-07-31", "horizon_days": 48 }
```

The existing active model covers stores 1,2,3. Every request reuses verified weights/preprocessing and only history available by its cutoff; it never trains. GET `/api/v1/forecasts/{forecast_id}` and its `/download.csv` return saved values. Daily/week/month totals sum rounded store-day values. Future plans are unknown unless explicitly supported and supplied. The browser still has no forecasting page. See [PHASE_10_REPORT.md](docs/PHASE_10_REPORT.md) for actual checks and scope.

## Phase 11 - Background training and optional recurrence

Start the optional worker in another terminal after PostgreSQL, migrations and API/web:

```text
uv run --locked python -m retailforecast.lifecycle.job_worker
```

POST `/api/v1/training-jobs` with `{"algorithm":"auto"}` enqueues without blocking on fitting. GET `/api/v1/training-jobs/{id}` inspects actual stages/attempts. GET/PUT `/api/v1/retraining-schedule` defaults to manual/disabled; an enabled schedule still needs this worker and an awake laptop. No new labeled data means a recorded skip, not a new model. Existing forecasts keep using the incumbent while a candidate trains.

[TRAINING_JOBS.md](docs/TRAINING_JOBS.md) provides PowerShell/bash examples, the operator `import_actuals` CSV contract, restart/idempotency and timezone rules. Validated new actuals can refresh forecast history without retraining; fixed-window candidate evaluation and model activation are separate. See [PHASE_11_REPORT.md](docs/PHASE_11_REPORT.md) for verification and limits.

## Phase 12 - Interface foundation

The browser now has Overview, Forecasts, Model Studio, Experiments, Feature Explorer and Data & Settings destinations. Status context stays visible on each page. Dataset as-of is the latest observed business date, never the import timestamp or today's date. Counts/model identity come from the real API. Unimplemented workflows display explicit empty states rather than sample operational results.

[UI_DESIGN.md](docs/UI_DESIGN.md) documents hierarchy, desktop/mobile wireframes, design tokens, API plumbing, accessibility and chart contracts. The foundation includes native store/date controls, state components, static skeletons, consistent date/Sales-unit formatting and a lazy ECharts SVG renderer with separate actual/predicted series plus an accessible table. Rossmann currency is unspecified, so no currency symbol is invented. ECharts and browser accessibility checks are exactly locked in package-lock.json.

Use the existing install/run commands above. Model Studio retains the separately started worker from Phase 11; visiting a page does not launch training or generate forecasts. See [PHASE_12_REPORT.md](docs/PHASE_12_REPORT.md) for real screenshots, validation and deferred scope. This phase does not publish a hosted demo.

## Phase 13 - Business Overview and Forecasts

Overview now recomputes selected-period Sales, coverage, store/weekday comparisons and open/closed history from imported SQL actuals. Choose stores and observed dates, apply filters and download matching daily/weekly/monthly totals. Forecasts supports bounded multi-store selection, observed as-of limits, 1–48 days, real saved-model results, separate actual/predicted chart series, per-store/weekly views and the existing CSV export. It never starts training; absent models link to Model Studio.

[DASHBOARDS.md](docs/DASHBOARDS.md) documents exact filters, units, missingness, cutoff and export behavior. [PHASE_13_REPORT.md](docs/PHASE_13_REPORT.md) records real dev-server/browser evidence, checks and scope. Restart API/web to load the added reporting endpoints. A training worker is optional for inference; a compatible active model and imported observations are required.
