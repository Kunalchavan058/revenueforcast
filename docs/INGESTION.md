# Local PostgreSQL and historical ingestion

## In plain English
Start the database, apply migrations, and validate the real files before importing. A dry run checks files without needing a database. Successful imports publish a complete immutable snapshot, while duplicate imports reuse it. Reports explain missing values and rejected rows. API/web and all Python work stay on the host.

## Setup — PowerShell and bash
From the repository root, use Node 22.13+ for existing web/check commands. Python commands are identical on PowerShell and bash.

```text
uv sync --locked --python 3.11
uv run python scripts/configure_database.py
docker compose --env-file .env -f infra/compose.yaml up -d --wait
uv run alembic upgrade head
uv run alembic check
uv run python -m retailforecast.data.import_rossmann --source-dir data --dry-run
uv run python -m retailforecast.data.import_rossmann --source-dir data
```

configure_database.py fills missing/placeholder settings in ignored root .env with a random local password and matching psycopg DATABASE_URL; it never prints credentials or replaces non-placeholder existing settings. If you already have database credentials, maintain POSTGRES_PASSWORD, POSTGRES_PORT and DATABASE_URL consistently. The image initializes credentials only for a new volume; changing .env does not change an existing database password.

Docker Desktop/Engine and Compose v2 must be running. Compose runs PostgreSQL only, binds to 127.0.0.1:5432 by default, sets a 512 MiB container cap, and persists a named volume. The image is digest-pinned. No MLflow backend is created yet because no MLflow service is used in this phase. API health remains liveness without a database dependency.

Place train.csv, test.csv, store.csv and sample_submission.csv together in the source directory. Existing downloaded files in data/ are supported directly; validated copies go to data/raw/<checksum>/. If absent, obtain the Rossmann competition download from Kaggle under your own account/terms and unzip locally. No data is fabricated, downloaded automatically, or committed.

## CLI contracts
python -m retailforecast.data.import_rossmann supports --source-dir, --dry-run (alias --validate-only), --min-date, --max-date and --report. uv run selects the project environment; equivalently activate .venv and run python -m directly. The CLI uses typed ImportRequest/ImportResponse and source-row/report schemas in retailforecast.data.contracts.

Dry run writes a local report but does not connect to PostgreSQL or copy raw sources. Actual import always revalidates; there is no bypass flag. By default a JSON outcome/report is written to ignored data/processed/validation-<checksum>.json. Use --report data/processed/my-report.json for a fixed location. Exit codes: 0 validated/succeeded/duplicate; 2 rejected source data; 1 operational/configuration error. Diagnostics never print database credentials/SQL parameters.

Imports are synchronous host-side CLI operations in Phase 4; no HTTP upload endpoints, job worker, scheduler, feature pipeline, model service, or new frontend page is introduced. Planned HTTP ingestion remains future work. Business schema names are documented in DATA_DICTIONARY.md.

## Reproducibility and transactions
The same source bytes and availability contract produce the same dataset identity; reruns create a separate import audit with duplicate state, not duplicate business rows. Each full snapshot is independent; corrections do not overwrite previous observations. Per-file hashes and stored reports tie data to raw local bytes.

Validation is streamed, with uniqueness keys held in memory rather than complete data rows. Inserts use batches of 5,000 rows within one transaction. The import audit is created separately so rejected/failed attempts survive rollback. Copy mismatch, FK error, or batch failure publishes no partial dataset. Process termination lets PostgreSQL roll back the business transaction, but may leave a validating/running audit requiring inspection; retry is safe and audited. Preserved files are never automatically deleted.

UTC event timestamps and daily business dates are distinct. Test inputs and submission placeholders never become actual labels. No new Kaggle sales arrive automatically. Promotion inputs are non-causal and future ML must honor the recorded historical-availability assumption.

## Verification
```text
uv run python -m pytest
uv run python -m mypy
uv run python -m ruff check .
uv run alembic current
uv run alembic check
```

PostgreSQL integration tests are included in normal pytest runs and fail visibly if the database is unavailable; they are not silently skipped or replaced by SQLite. Each test uses a generated rf_test_<uuid> schema and real Alembic revisions. Tests drop only their own generated schema, leaving public/imported data intact. Downgrade/upgrade is verified only in those disposable schemas. Do not run alembic downgrade base on your actual imported database.

For source-only validation tests without infrastructure, explicitly run pytest tests/test_validation.py; this is a selected subset, not a claim that integration tests passed. Starter CI initializes Compose and migrations before running all checks. GitHub CI results are separate from local verification.

## Operations
Keep the API/web development command separate from infrastructure. docker compose --env-file .env -f infra/compose.yaml stop pauses PostgreSQL without deleting data; up -d --wait starts it again. Do not remove the named volume unless intentionally discarding your local database. Original CSVs and validated raw copies stay ignored. Back up the database plus raw bytes/reports; Docker volumes are not off-machine backups.
