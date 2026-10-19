# Dataset files and reproducible processing

## In plain English
DVC remembers exact dataset files, while PostgreSQL remembers business records and import transactions. The pipeline checks raw files, writes typed Parquet tables and publishes a readable manifest. A synthetic example works without Kaggle or a database. Git stores code and file pointers rather than competition data. All artifact storage stays on this laptop.

## Four tools, four responsibilities
| Tool | Tracks/stores | Does not do here |
|---|---|---|
| Git | Code, configs/data.yaml, synthetic JSON fixture, dvc.yaml, dvc.lock, .dvc/config and raw .dvc pointers | Raw CSVs, Parquet, credentials, private paths or caches |
| DVC | Dataset files/content hashes, stage dependencies, run cache, local artifact remote | Version PostgreSQL rows, migrate schemas or approve models |
| PostgreSQL | Transactional import snapshots, actuals/unlabeled inputs, jobs, business metadata | Replace original file artifacts or contain serialized models |
| MLflow (planned) | Experiment/run parameters and metrics, registered model references | Replace Git/DVC/SQL; no MLflow service is running |

DVC cache hashes (currently including MD5 directory identifiers), the application's SHA-256 processed fingerprint, an ingestion bundle checksum and a PostgreSQL dataset UUID have different meanings. Do not compare them as if they were the same version ID.

## Local setup
Run from the repository root. The file pipeline needs Python/uv/Git, not Node, Docker, GPU, a cloud account or PostgreSQL.

```text
uv sync --locked --python 3.11
uv run python scripts/configure_dvc.py
```

The helper initializes DVC when needed. Its default laptop remote is a repository-specific subfolder in a sibling .dvc-remotes directory, outside Git. The resolved location/default remote is stored only in ignored .dvc/config.local. Pass --remote with another local directory to configure an existing storage location; inside-repository locations are rejected.

Shared DVC config contains no absolute private path or cloud remote. It selects copy-based cache links, disables analytics and automatic Git staging. DVC has transitive task libraries, but this project starts no Celery, Redis or orchestration service. Stages run as ordinary synchronous host commands.

## Synthetic example without Kaggle
tests/fixtures/rossmann_synthetic.json is explicitly synthetic_only and hand-authored. IDs 9001/9002 are outside the real Rossmann store range. It is not a sample copied from Kaggle. The generator writes deterministic LF CSV files locally; no CSV is committed.

```text
uv run dvc repro manifest@synthetic
uv run python -m retailforecast.data.file_pipeline verify --profile synthetic
uv run dvc status manifest@synthetic
```

The example produces two stores, four labeled store-days, two unlabeled inputs and two template placeholders. Its manifest explicitly says dataset_kind=synthetic. These are test/example records, not observed model performance.

The explicit target needs no real dataset. On a fresh checkout, project-wide dvc status may report missing real Rossmann files; the synthetic target still works. A bare dvc repro targets both profiles and requires real source artifacts too.

## Real Rossmann files
Obtain/unzip the four competition files locally under Kaggle access terms if absent. Existing originals in ignored data/ are supported; nothing is fabricated or downloaded automatically.

```text
uv run python -m retailforecast.data.file_pipeline prepare --profile rossmann --source-dir data
uv run dvc add data/raw/rossmann
uv run dvc repro manifest@rossmann
uv run python -m retailforecast.data.file_pipeline verify --profile rossmann
uv run dvc status
```

prepare validates then checksum-verifies copies into data/raw/rossmann. It never changes original downloads or Phase 4 content-addressed copies. dvc add creates data/raw/rossmann.dvc containing metadata, not rows. On unchanged inputs, dvc repro skips work. To force execution rather than use cached runs:

```text
uv run dvc repro --force --no-run-cache manifest@synthetic manifest@rossmann
```

configs/data.yaml is the single preprocessing config: profile paths/kinds, fixed validation date bounds, availability assumptions, batch size and compression. The configured maximum date is a validation bound, not a training cutoff. Extend it deliberately when legitimate new source data arrives.

## Stages and output contract
1. Generate only the synthetic source from its JSON fixture; real source is supplied separately.
2. Validate using the existing source contracts, fixed configured dates and full quality reports.
3. Normalize into stores, daily_sales, forecast_inputs and submission_template Parquet tables.
4. Publish a manifest after completed normalization is tied to the validated context.

Each profile writes under data/processed/<profile>/:

| Output | Meaning |
|---|---|
| validation.json | Typed report envelope bound to config/code/lock/writer context |
| tables/*.parquet | Explicit normalized source schemas and preserved row order |
| tables/normalization.json | Receipt linking validated context and exact table hashes |
| manifest.json | Portable typed metadata for future UI/API inspection |

No imputation, lag/rolling features, optimization, models or predictions are created. Actual Sales/Customers stay historical. Future inputs physically have no Sales/Customers columns. Template Sales become placeholder_sales in a separate table. Unknown test Open is NULL; zeros and closed-store quirks are preserved.

## Inspect a manifest
```text
uv run python -m json.tool data/processed/rossmann/manifest.json
```

Fields include dataset_kind, dataset_fingerprint, ingestion_dataset_checksum, max_historical_actual_date, effective_config_sha256, input_checksums, processing_code_sha256, dependency_lock_sha256, pyarrow_version, report/receipt hashes, and table paths/SHA-256/counts/column types. Paths are repository-relative. Wall-clock times, hostnames, usernames and Git branch state are absent.

The fingerprint hashes canonical payload JSON excluding its own fingerprint field. Code/lock text hashes normalize checkout newlines; source hashes identify exact raw bytes. Unchanged input/config/code/locked writer reproduced identical artifacts on this machine. Reordering raw rows or changing raw line endings creates a new byte identity. Cross-platform binary equality is not claimed without measurement.

verify checks current inputs, config, code, lock, writer, receipts and table bytes. New config cannot be attached to old equal-row-count Parquet. A future API should consume this verified contract, rather than blindly display stale JSON. No dataset endpoint is implemented now.

## Local remote and file restoration
```text
uv run dvc push
uv run dvc status --cloud
```

push copies artifact objects only to the configured laptop filesystem directory; it does not upload raw files to GitHub. Git receives code/config/pointer/lock metadata only. DVC cache, config.local, CSVs, Parquet and processed reports stay ignored. A sibling directory on the same laptop is not an off-machine disaster backup.

Use dvc checkout for offline workspace restoration when cache objects exist. Use dvc pull when objects must first be recovered from the configured local remote; pull fetches and restores. Preserve manual artifact edits before replacement. Neither command changes PostgreSQL rows.

## Compare and restore versions
After intentionally committing pointer/lock/code changes, compare DVC-enabled Git revisions. Replace OLD_REV and NEW_REV with actual commit IDs:

```text
uv run dvc diff OLD_REV NEW_REV
uv run dvc params diff OLD_REV NEW_REV
git diff OLD_REV NEW_REV -- configs/data.yaml dvc.yaml dvc.lock data/raw/rossmann.dvc
```

To restore a matching historical snapshot, first preserve uncommitted work and stop jobs using the checkout, or use a separate worktree. With a clean working tree:

```text
git switch --detach OLD_REV
uv sync --locked
uv run python scripts/configure_dvc.py
uv run dvc pull
uv run python -m retailforecast.data.file_pipeline verify --profile rossmann
```

Select a revision that contains this pipeline. Its code/config/lock must match the manifest; incompatible current code correctly rejects old provenance. Return with git switch main, sync the environment and pull that revision's artifacts. Git reset or database-volume deletion is not a file-restore method. This phase does not automatically commit/push new DVC metadata.

## Re-ingest restored raw files into PostgreSQL
```text
uv run python -m retailforecast.data.import_rossmann --source-dir data/raw/rossmann --dry-run
uv run python -m retailforecast.data.import_rossmann --source-dir data/raw/rossmann
```

This is a separate explicit operation with Phase 4 Docker/migration/configuration requirements. Identical raw bytes and availability policy reuse the existing ingestion checksum/SQL snapshot. New processing settings can change a file-artifact fingerprint without changing any raw CSV or SQL row. DVC restore never performs SQL rollback or removes earlier database versions.

## Import timestamps and training windows
Importing in 2026 does not turn 2013–2015 observations into new sales. ingested_at is a UTC audit event, not a label date or forecast cutoff. Real historical actuals end on 2015-07-31; unlabeled test dates through 2015-09-17 do not extend that endpoint.

Future training must select eligible label dates/information availability at each cutoff and record the dataset fingerprint. It must not read intermediate future actual Sales/Customers. The recorded known-at-cutoff assumptions are historical simulation assumptions, not proof of real-world availability.

## Memory and checks
Validation streams rows but retains uniqueness keys; memory scales with key count instead of a full dataframe. Conversion holds at most batch_rows (default 10,000; maximum 50,000). Explicit int8/int16/int32, boolean, date32, decimal128 and string fields avoid mixed-type inference. Batches become bounded row groups; dictionaries and Zstandard reduce file size. No global sort/pandas dataframe is needed. Checksums stream files and table inspection uses footer metadata.

These are limits for an 8 GB laptop, not a measured benchmark of a future full ML stack. Tests verify byte-identical reruns, changed-input/config fingerprints, portable manifests, stale context, tampering, label separation and row-group bounds:

```text
uv run pytest tests/test_file_pipeline.py -q
uv run python -m mypy
uv run python -m ruff check .
```

Full pytest also includes existing real PostgreSQL tests and requires that database. CI reproduces only synthetic artifacts without Kaggle access or the laptop's private remote. No unnecessary orchestration service was added.

References: [DVC local config](https://doc.dvc.org/command-reference/config), [pipeline format](https://doc.dvc.org/user-guide/project-structure/dvcyaml-files), [PyArrow writer](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetWriter.html).
