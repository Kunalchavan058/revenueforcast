# RetailForecast AI

A local-first retail forecasting application in development. **Phase 4 implements PostgreSQL, migrations, source validation and historical Rossmann CLI ingestion.** The web app still shows API connection health only. Feature preparation, model training, forecasts, charts, scheduling, MLflow and DVC integration are not implemented. Historical 2015 records are not live data.

## Required tools

- Python 3.11–3.13; 3.11 is the locally tested baseline.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for the environment and lock.
- Node.js 22.13+ with npm 10+; .node-version records the tested release.
- Docker Desktop/Engine with Compose v2 for PostgreSQL and integration tests.
- Git. No GPU, Colab, notebook kernel, Kubernetes, Redis, Celery, authentication or remote cloud account is required.

API/web and ingestion stay on the host. Only PostgreSQL runs in Compose. The health-only UI can run without Docker; complete Python checks now require PostgreSQL.

## Install — Windows PowerShell

From the repository root:

```powershell
uv sync --locked --python 3.11
npm.cmd ci
uv run python scripts/configure_database.py
docker compose --env-file .env -f infra/compose.yaml up -d --wait
uv run alembic upgrade head
uv run alembic check
npm.cmd run dev
```

## Install — bash

```bash
uv sync --locked --python 3.11
npm ci
uv run python scripts/configure_database.py
docker compose --env-file .env -f infra/compose.yaml up -d --wait
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

Normal pytest includes real PostgreSQL integration tests and fails if the database is unavailable; it never silently skips or substitutes SQLite. Test schemas are generated and isolated from imported data; migration downgrade/upgrade is tested only there. Source-only tests can explicitly be selected with uv run pytest tests/test_validation.py.

Browser tests require free ports 3000/8000 and a browser. Install Chromium using npm exec --workspace apps/web -- playwright install chromium. Or use installed Edge: set $env:PLAYWRIGHT_CHANNEL='msedge' in PowerShell, or prefix the bash command with PLAYWRIGHT_CHANNEL=msedge. They start/stop their own test servers. The existing dev servers must be stopped before running browser integration tests.

## Configuration and boundaries

API health returns {status: ok, service: retailforecast-api, api_version: v1}; it is liveness only, not database/model readiness. Browser requests use same-origin /api/v1 and a Next.js rewrite to API_BASE_URL, default http://127.0.0.1:8000. Root dev/web/build commands load optional .env; restart/rebuild after proxy changes. The typed client shows actual loading/connected/offline states and validates response JSON.

- apps/web/: Next.js App Router, React/strict TypeScript, Tailwind and a local shadcn/ui primitive.
- services/api/: thin health-only service entry point, not a second Python package root.
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

Read [AGENTS.md](AGENTS.md), [product spec](docs/PRODUCT_SPEC.md), [architecture](docs/ARCHITECTURE.md), [coding standards](docs/CODING_STANDARDS.md), [roadmap](docs/ROADMAP.md), and [journal](docs/IMPLEMENTATION_LOG.md). Design documents include future behavior beyond this phase. No ML evaluation or accuracy claims exist.

The public repository is [Kunalchavan058/revenueforcast](https://github.com/Kunalchavan058/revenueforcast). Next.js regenerates next-env.d.ts during dev/build/typegen; it stays local and ignored while remaining included in tsconfig.json.
