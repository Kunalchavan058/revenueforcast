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
| DayOfWeek | train/test | integer 1â€“7 / day_of_week | Monday=1; must agree with Date |
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
| CompetitionOpenSinceMonth | store | integer 1â€“12 or NULL | optional |
| CompetitionOpenSinceYear | store | integer 1900â€“2100 or NULL | optional |
| Promo2 | store | 0/1 or NULL | optional |
| Promo2SinceWeek | store | integer 1â€“53 or NULL | optional |
| Promo2SinceYear | store | integer 1900â€“2100 or NULL | optional |
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
| forecast_points | PK (run_id, store_id, target_date); unique (run_id, store_id, horizon); composite FKs to run and stores | horizon 1â€“48, nonnegative predicted_sales; no prediction code implemented |
| retraining_schedules | PK id; unique scope | manual/weekly/monthly/quarterly, timezone, next_run, enabled; scheduler not implemented |

For normalization, forecast_points inherits model_version_id, cutoff_date and created_at through forecast_runs rather than copying them onto every point. Later response/export schemas join those values. Scope identifies dataset lineage (currently an independent full snapshot), feature schema, requested algorithm policy and training-cutoff policy; a PostgreSQL partial unique index allows at most one status=active model per scope. Phase 9 adds the implemented global-v1 serving pointer and audited approval/rollback. Durable training-job execution remains future work. Historical scope proposals are superseded by MODEL_LIFECYCLE.md.

## Provenance and availability
Individual source checksums are SHA-256 of exact bytes. Compound snapshot identity hashes a sorted filename/checksum manifest, source contract version and explicit availability policy. Validation date bounds do not change identity because they do not transform data. Identical valid sources/policy reuse the same dataset even on a later day; different bytes/policy create an independent full snapshot. No silent merge, correction overwrite, or incremental lineage inference occurs.

Raw copies are preserved under ignored data/raw/<compound-checksum>/. Import verifies copy checksums before publication. A snapshot transaction inserts version, stores, actuals, unlabeled inputs and success/duplicate audit together; batches do not commit independently. A separate audit transaction records failed publication after rollback. Equal concurrent snapshots are serialized with a PostgreSQL advisory transaction lock plus a unique checksum constraint. Raw files can remain after failed publication for review; no incomplete dataset is visible.

The default date policy is 2000-01-01 through the current UTC date, configurable by --min-date/--max-date. Historical simulation assumes train labels are available on their business date and supplied store metadata/test plans are known at forecast cutoff. This assumption is persisted and disclosed; archived CSVs cannot prove real historical availability. available_through is the latest observed train label date, never the last test date.

## Engineered fields â€” not implemented
No features or predictions are created during ingestion. Phase 6 adds a separate feature builder using cutoff_date, target_date, horizon_days and available_as_of; both observation and availability dates must be at/before cutoff for history. See the generated FEATURE_REGISTRY.md and FEATURES.md for the implemented lags, windows, target covariates and fitted encoding contract. Future actual Sales and all Customers predictors remain forbidden. No promotion optimization or causal effect inference is supported.


## Phase 5 Parquet mapping
File tables use normalized source names with Arrow int8/int16/int32, boolean, date32, exact decimal128(18,4) and string types. Source order and NULLs remain intact. submission_template uses submission_id/placeholder_sales; it is not an actuals table. Portable manifests identify artifacts and their last historical label date. No feature columns are engineered; DATA_VERSIONING.md explains checksums and SQL relationships.

## Phase 6 feature view

FeatureRow contains request identity, registered predictors and optional snapshot context, never y or Customers. LabeledExample attaches the aligned target separately and requires its availability at/after target date. No database columns or migration changed. Raw/normalized source fields above retain their original meaning; learned imputation affects only the model matrix. Engineered field names, types, sources and policies are generated in FEATURE_REGISTRY.md rather than duplicated here.

## Phase 7 evaluation artifacts

Outcome is scoring-only (store_id, target_date, actual_sales, available_as_of, observed_open). PredictionPoint keeps raw/adjusted predictions, training/cutoff dates, known_open separately from observed_open, coverage status and nullable actual/error fields. Only labeled available outcomes can produce errors; sample submission/test never supply outcomes. Segment records contain requested/labeled/scored counts, coverage, zero exclusions, real sales totals and MAE/RMSE/RMSPE. MODEL_STRATEGY.md defines their units/masks and the JSON/Parquet publication manifest. These files remain ignored under artifacts/evaluation; no business schema or migration changed.

## Phase 8 supervised and model contracts

PreparedData contains fold-local float32 predictors and labels plus fitted preprocessing and TrainingSpan (origin/label bounds, row/origin counts, requested cadence, cap flag, stores). Expanded one-hot columns derive only from saved training vocabularies. BundleMetadata records algorithm/class, internal and actual native parameters, seed/threads, trained_until, dataset context, encoded order, preprocessing version, pinned libraries, coverage/capabilities and file checksums. training.json adds Git/source/lock/registry identity, UTC trained_at, actual duration, MLflow IDs and artifact references. No source CSV/SQL fields change; Customers stay excluded. File manifests may receive new environment fingerprints after dependency changes even when source bytes and ingestion identity are unchanged.


## Phase 9 model lifecycle tables

| Table | Keys/fields | Meaning |
|---|---|---|
| model_versions | existing UUID PK, dataset/training references, algorithm/cutoff, artifact URI, feature schema hash, MLflow run, status | application role: candidate/active/rejected/archived; one active per scope enforced by partial index |
| model_registrations | PK/FK model_version_id; bundle_sha256, dataset_fingerprint, mlflow_model_name/version, evidence JSON, approval_required, decision_reason | sealed provenance and actual comparison/approval evidence; no serialized weights |
| model_slots | scope PK; active_model_version_id FK nullable; generation >= 0 | global-v1 serving authority and compare-and-swap token |
| model_events | UUID PK; model/previous-model FKs, generation, action, reason, UTC created_at | activation, rejection, missing-evidence, validation-failure and rollback audit |

The native bundle hash seals its file manifest; registration evidence additionally seals training and evaluation manifests. Those manifests bind raw/processed dataset identities, source/code/lock hashes, fitted preprocessing/order and actual metric reports. MLflow registry technical READY is distinct from the application active role. Native model files remain outside both PostgreSQL databases. Source/engineered feature fields are unchanged; Customers remain excluded from predictors.

## Phase 10 persisted forecast contracts

| Table / value | Meaning |
|---|---|
| forecast_runs.request_context | Versioned JSON: canonical request/scenarios, visible-input hash, pinned model/generation/schema, dataset identities, source/visible dates, per-store coverage, knowledge assumptions, policy and warnings |
| forecast_runs.id / source_version / model_version_id / cutoff_date / created_at | UUID, imported source FK, immutable model FK, inclusive information cutoff, UTC generation event |
| forecast_points run/store/target_date | One daily forecast per requested store and direct horizon, never a retrospective actual |
| forecast_points.horizon / predicted_sales | Target date minus cutoff (1..48); nonnegative rounded NUMERIC(18,4) in unspecified source Sales units |
| forecast_points.known_open | Nullable opening plan known at cutoff, distinct from retrospectively observed opening |
| forecast_points.nonnegative_clamped / closure_adjusted | Whether evaluated nonnegative / explicit-known-closure policies adjusted this point |

Source and engineered fields remain distinct. Daily/weekly/monthly totals derive from rounded point values, not additional model targets or database copies. Historical cutoff and generation timestamp have different meanings. CSV repeats frozen run metadata for portable store-day rows. See API_CONTRACT.md and frozen migration a10f0c03b002; old rows with empty context cannot claim current reproducibility metadata.

## Phase 11 operational and additional-observation fields

| Entity | Added meaning |
|---|---|
| dataset_lineage | child dataset FK, parent FK, additional raw-file checksum, operator provenance and synthetic flag; application-published chains preserve all existing metadata/history |
| dataset_versions child | immutable copied history plus validated later actuals; compound checksum/version binds parent and new file report; raw_uri points to preserved additional CSV |
| training_jobs | nullable source FK for no-data missed checks; algorithm, six-state status, canonical trigger key/public request hash, pinned backend/data context, stage/message, counts/retry time, heartbeat, timestamps, result model reference |
| training_attempts | job/attempt unique identity, opaque owner token, state/times, actual process PID/creation time, owned output path, exit code and safe log summary |
| retraining_schedules | existing manual/weekly/monthly/quarterly intent plus UTC anchor, revision, selected algorithm and last_check_at; next_run advances with unique due audit |
| model_versions.training_job_id | at most one published version per non-null job, enabling idempotent restart recovery |
| forecast data.feature_context_dataset_fingerprint | saved feature context, separately exposing observed append-only source identity/checksum/history coverage |

Job state is distinct from model role: succeeded training can leave a candidate rejected or pending while the incumbent stays active. Skipped does not create a training attempt or model version. File materialization retains exact raw/Parquet hashes and binds its export checksum back to the pinned business source/job; PostgreSQL still contains no serialized model bytes. SQL snapshot exports may legitimately contain empty remaining test/template tables after their dates become actual; no future row or label is fabricated. Original competition four-file import remains strict. Full operator contracts and protected-history fitting policy are in TRAINING_JOBS.md.


## Phase 13 descriptive dashboard fields

Business reporting derives total_sales, calendar period Sales, per-store totals, weekday means, observed/expected/missing store-days and historical open/closed counts from DailySale only. These are read-only descriptive outputs, not engineered model features or forecast-error metrics. observed_from/observed_through are actual business dates; covered_from/covered_through describe the requested part of each calendar bucket. Null Sales denotes no observations; known zero Sales is preserved. closed_positive_sales_days counts retained source quirks. Weekday mean denominator is observed store-days including closed zeros. Dataset/checksum and applied filters accompany CSV.

Forecast options expose verified model fit date, source and per-supported-store observed ranges plus recorded availability delay. Saved subset views return original points and shared exact totals, not new forecasts. Source Sales units have no confirmed currency. DASHBOARDS.md and generated OpenAPI define bounds and public schemas.
