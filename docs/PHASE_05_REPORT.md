# Phase 5 — DVC and reproducible dataset processing

## Delivered

DVC tracks local dataset files and content hashes; Git tracks code/configuration and DVC pointers. PostgreSQL remains the transactional business store. MLflow is reserved for experiment/run metadata and model references; no MLflow service was added.

One `configs/data.yaml` drives raw validation, four normalized Parquet tables and a typed dataset manifest. The synthetic JSON fixture contains invented records only and generates ignored CSVs. The real Rossmann files were validated and copied without changing the originals. The local DVC remote is outside the repository; its absolute path exists only in ignored `.dvc/config.local`. No cloud remote or orchestration service was added.

## Files and design decisions

- Pipeline: `pipeline_config.py`, `parquet_tables.py`, `synthetic_data.py`, `file_pipeline.py` under the existing `src/retailforecast/data/` package; no duplicate package root.
- Versioning: `dvc.yaml`, `dvc.lock`, `.dvc/config`, `.dvc/.gitignore`, `.dvcignore`, `data/raw/rossmann.dvc`, `configs/data.yaml` and `scripts/configure_dvc.py`.
- Verification: `tests/test_file_pipeline.py`, synthetic JSON fixture and CI synthetic reproduction steps.
- Dependencies: exact DVC, PyArrow, YAML and YAML typing pins in `pyproject.toml` and resolved `uv.lock`.
- Documentation: DATA_VERSIONING, decision 0006, data dictionary, architecture, data flow, coding standards, README, configuration README, roadmap and implementation log. Ignore rules exclude private settings and data bytes.

Public functions and boundaries have types/docstrings. Validation reuses source contracts; source ordering, nullable Open values and closed-store quirks are preserved. Forecast inputs contain no historical labels; submission placeholders have their own table and cannot masquerade as actual Sales. No engineered features exist.

Manifests exclude timestamps and host paths. They include raw/config/code/lock/writer hashes, table schemas/counts/hashes and the last historical actual date. Validation context and normalization receipts reject stale intermediate outputs. Named batch size is 10,000 rows, with explicit Arrow types and bounded writes. Validation uniqueness sets still grow with source keys; total peak memory on an 8 GB machine was not measured. Native Arrow lacks typing stubs, so its narrowly scoped mypy exception is paired with runtime schema tests.

## Commands and results

Commands were run from the repository root using the locked environment.

| Command/check | Result |
|---|---|
| `uv run --locked python scripts/configure_dvc.py` | Initialized portable settings and private laptop remote |
| `uv run --locked dvc repro manifest@synthetic` | Synthetic-only pipeline succeeded |
| Prepare real source files, then `uv run --locked dvc add data/raw/rossmann` | Validated copies and Git-safe raw pointer |
| `uv run --locked dvc repro manifest@rossmann` | Full real pipeline succeeded |
| `uv run --locked dvc repro --force --no-run-cache manifest@synthetic manifest@rossmann` | Both profiles rebuilt; identical fingerprints |
| `uv run --locked dvc repro` | Unchanged stages skipped |
| CLI manifest verification for both profiles | Source/config/code/environment/table integrity passed |
| `uv run --locked dvc checkout --force manifest@synthetic` | Exact manifest bytes preserved |
| `uv run --locked dvc push` | Local remote synchronized |
| `uv run --locked dvc status` | Data and pipelines up to date |
| `uv run --locked dvc status --cloud` | Cache and laptop remote in sync |
| Ruff check and format check | Passed; 55 files formatted |
| Strict mypy | Passed; 30 source files |
| Full pytest suite | 36 passed, including PostgreSQL integration and 11 new pipeline cases; no skips |
| `uv lock --check` | Passed |
| Publishable file inspection | No CSV/Parquet, private remote config or local absolute user paths |
| Read-only SQL counts | Dataset versions 1, actual rows 1,017,209, import jobs 2; unchanged |

Tests cover identical reruns, changed-label identity, portable root paths, stale normalization, nullable/source-label separation, batch bounds, tampering, invalid labels and unsafe configuration paths. Frontend code did not change; previous browser/build results were not rerun or counted as Phase 5 checks. Remote GitHub CI has not been executed for these local changes.

## Inspectable results

Real tables: stores 1,115; daily sales 1,017,209; unlabeled inputs 41,088; submission placeholders 41,088. Maximum historical actual date is **2015-07-31**. Import/preprocessing time does not extend training windows into 2026 or turn Kaggle test rows into actuals.

| Profile | Dataset fingerprint |
|---|---|
| Synthetic | `cfd0c178f4801b59d275733f591a62269047e8d9da2ed03b3ce6e5106ebfc90f` |
| Rossmann | `9ecf0848f6752b7beb4d26cbc80bfccf205d0cc31825af7ff64de06352e76788` |

Manifests are local at `data/processed/<profile>/manifest.json`, ready for a later API/UI consumer; no endpoint is implemented in this phase. See DATA_VERSIONING for reproduction, version comparison, restoration and separate PostgreSQL re-ingestion commands.

## Limits and completion review

A same-laptop remote protects local workflow, not laptop loss. Bit-identical Parquet was verified in this locked environment; cross-platform binary identity is not promised. Files publish individually with the manifest last; receipt/hash verification prevents consuming incomplete or mixed output. Historical availability remains an explicit simulation assumption. DVC dependencies include transitive worker libraries, but no worker, Redis or Celery service runs.

Requirements and readability were reviewed: one package root, meaningful names, explicit contracts, concise public docstrings, targeted provenance comments, named settings, no duplicated business validation, no feature/training implementation. Database contents and existing application services were preserved. Changes are local; this phase does not commit or publish them. Stop after Phase 5.
