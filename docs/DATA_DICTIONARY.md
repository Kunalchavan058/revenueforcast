# Rossmann data dictionary

## In plain English
Train data records observed sales; test data records unlabeled future inputs from the historical competition. The submission file shows an export format, not actual revenue or model output. Missing values and unusual closed-store records are retained explicitly. Every published record belongs to an immutable, checksum-identified snapshot. No engineered ML features exist in Phase 4.

## Inspected source files
The validator inspected the actual locally downloaded headers and all records, rather than assuming a schema.

| File | Observed records | Meaning and treatment |
|---|---:|---|
| train.csv | 1,017,209 | Labeled store-days, 2013-01-01 through 2015-07-31, 1,115 stores |
| test.csv | 41,088 | Unlabeled inputs, 2015-08-01 through 2015-09-17, 856 stores |
| store.csv | 1,115 | Store metadata with optional missing attributes |
| sample_submission.csv | 41,088 | Id/Sales placeholders; preserved as raw source and validated, not inserted as actuals or forecasts |

These are verified source-file counts, not claims of live data or model accuracy. Dataset rows means labeled train rows; complete per-file counts live in validation_report.

## Source columns and typed mappings
| Source field | Files | Type / destination | Rules |
|---|---|---|---|
| Store | train/test/store | positive integer / store_id | Store must exist in this snapshot's store.csv; metadata key unique per snapshot |
| Date | train/test | business date / date | configured date bounds; matches DayOfWeek; unique (Store, Date) within each file |
| DayOfWeek | train/test | integer 1–7 / day_of_week | Monday=1; must agree with Date |
| Sales | train only | nonnegative finite Decimal(18,4) / daily_sales.sales | label, never future predictor; missing/negative/nonfinite values rejected |
| Customers | train only | nonnegative integer / daily_sales.customers | historical audit only; forbidden as a V1 predictor |
| Open | train/test | 0/1 / is_open | required for actuals; blank/missing in test retained as NULL |
| Promo | train/test | 0/1 / promotion | source promotion flag; any later predictor is non-causal and needs known-at-cutoff provenance |
| StateHoliday | train/test | 0/a/b/c / state_holiday | required source category; missing columns/blank values are rejected |
| SchoolHoliday | train/test | 0/1 / school_holiday | required source flag; missing columns/blank values are rejected |
| Id | test/submission | positive integer / submission_id | unique per file; identical coverage in test and sample submission |
| Sales | sample submission | nonnegative finite decimal | placeholder only; never copied to daily_sales or forecast_points |
| StoreType | store | a/b/c/d or NULL / store_type | optional |
| Assortment | store | a/b/c or NULL / assortment | optional |
| CompetitionDistance | store | nonnegative finite Decimal(18,4) or NULL | source distance; units/causal effects not inferred |
| CompetitionOpenSinceMonth | store | integer 1–12 or NULL | optional |
| CompetitionOpenSinceYear | store | integer 1900–2100 or NULL | optional |
| Promo2 | store | 0/1 or NULL | optional |
| Promo2SinceWeek | store | integer 1–53 or NULL | optional |
| Promo2SinceYear | store | integer 1900–2100 or NULL | optional |
| PromoInterval | store | comma-separated known month abbreviations or NULL | Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sept, Oct, Nov, Dec |

CSV whitespace is trimmed. Blank optional metadata is NULL, not zero. Exact integral strings such as 1.0 can become integer 1; fractional Customers/IDs, garbage numerics, infinities, negative labels, unknown columns, duplicate headers, and extra cells fail validation. Missing required columns are reported by name. No arbitrary rows are dropped to make an import pass.

## Source quirks and validation reports
The observed data has 172,817 closed train rows, 54 open train rows with zero Sales, and 11 test rows with unknown Open. There are 3 missing CompetitionDistance values and 354 missing competition opening month/year values. Validation reports retain complete per-column missingness counts. Closed rows with positive Sales are warnings, not automatic zeroing; actual source labels remain untouched. Missing dates are not filled and no synthetic zero records are generated.

Report contract: file checksum, total/valid/invalid rows, date span, unique stores, missingness, duplicate count, closed_stores (closed store-day row count, not unique store count), closed_with_sales, missing_open, zero_sales_when_open, missing optional columns, warnings, total issue count and up to 50 actionable issue examples with filename/line. File-level parsing errors may stop scanning a malformed file; counts then describe records examined, not a fabricated complete count. Import is rejected whenever any issue is present.

## Business schema and relations
All opaque IDs are UUID strings. UTC timestamps record ingestion/job events; source business dates stay SQL DATE. No model bytes are stored in PostgreSQL.

| Entity | Primary/unique keys and relations | Contents |
|---|---|---|
| dataset_versions | PK id; unique checksum and version | source, compound checksum, immutable version, ingested_at, labeled rows, available_through, raw_uri, validation report, availability_policy |
| stores | PK (source_version, store_id); FK source_version to dataset_versions | versioned Rossmann metadata |
| daily_sales | PK (source_version, store_id, date); composite FK to stores | labeled actuals only; nonnegative Sales/Customers and weekday constraint |
| forecast_inputs | PK (source_version, store_id, date); unique (source_version, submission_id); composite FK to stores | unlabeled test inputs; physically no Sales/Customers columns |
| import_jobs | PK id; optional FK dataset_version_id | every publication attempt, checksum, state, report, UTC start/end, sanitized error_code |
| training_jobs | PK id; FK dataset_version_id | requested algorithm, constrained state, start/end, logs_uri/exit_code; execution not implemented |
| model_versions | PK id; FKs dataset_version_id/training_job_id | algorithm, scope, trained_until, external artifact URI, feature fingerprint, MLflow run ID, trained_at, evaluation reference, approval status |
| forecast_runs | PK id; FK source_version/model_version_id; unique (id, source_version) | request cutoff and created_at shared by all points; execution not implemented |
| forecast_points | PK (run_id, store_id, target_date); unique (run_id, store_id, horizon); composite FKs to run and stores | horizon 1–48, nonnegative predicted_sales; no prediction code implemented |
| retraining_schedules | PK id; unique scope | manual/weekly/monthly/quarterly, timezone, next_run, enabled; scheduler not implemented |

For normalization, forecast_points inherits model_version_id, cutoff_date and created_at through forecast_runs rather than copying them onto every point. Later response/export schemas join those values. Scope identifies dataset lineage (currently an independent full snapshot), feature schema, requested algorithm policy and training-cutoff policy; a PostgreSQL partial unique index allows at most one status=active model per scope. It is a constraint, not an implemented approval/rollback service. Dedicated serving-slot generation/audit and richer training lifecycle tables remain future work.

## Provenance and availability
Individual source checksums are SHA-256 of exact bytes. Compound snapshot identity hashes a sorted filename/checksum manifest, source contract version and explicit availability policy. Validation date bounds do not change identity because they do not transform data. Identical valid sources/policy reuse the same dataset even on a later day; different bytes/policy create an independent full snapshot. No silent merge, correction overwrite, or incremental lineage inference occurs.

Raw copies are preserved under ignored data/raw/<compound-checksum>/. Import verifies copy checksums before publication. A snapshot transaction inserts version, stores, actuals, unlabeled inputs and success/duplicate audit together; batches do not commit independently. A separate audit transaction records failed publication after rollback. Equal concurrent snapshots are serialized with a PostgreSQL advisory transaction lock plus a unique checksum constraint. Raw files can remain after failed publication for review; no incomplete dataset is visible.

The default date policy is 2000-01-01 through the current UTC date, configurable by --min-date/--max-date. Historical simulation assumes train labels are available on their business date and supplied store metadata/test plans are known at forecast cutoff. This assumption is persisted and disclosed; archived CSVs cannot prove real historical availability. available_through is the latest observed train label date, never the last test date.

## Engineered fields — not implemented
No lags, rolling windows, encodings, target transformations, model outputs, or predictions are created during ingestion. Future feature contracts must use cutoff_date, target_date, horizon_days, and available_as_of; only Sales observed at/before cutoff may supply lags/windows. Future actual Sales and all Customers predictors remain forbidden. No promotion optimization or causal effect inference is supported.
