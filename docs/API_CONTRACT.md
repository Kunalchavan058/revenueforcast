# Forecast API contract

Phase 10 implements local prediction and persisted exports. Start PostgreSQL, apply migrations, import a dataset and activate a validated saved model first. Forecasting never launches training. The web page remains a health screen; use the API's Swagger UI at http://127.0.0.1:8000/docs. This is historical Rossmann data, not a current sales feed.

## Start and inspect

From the repository root, in PowerShell or bash:

```text
uv run --locked alembic upgrade head
uv run --locked alembic check
uv run --locked python scripts/manage.py api
```

The default binds to loopback port 8000. `/openapi.json` is the executable contract; [openapi.json](openapi.json) is its versioned snapshot. Tests compare that snapshot to the application. Health remains independent of database/model readiness. Local lifecycle mutation endpoints retain their Phase 9 checks; no authentication or hosted deployment is introduced.

| Method and `/api/v1` path | Response / behavior |
|---|---|
| GET `/health` | 200 process liveness only |
| GET `/datasets/status` | Latest imported source, observed-through date, active model's dataset ID; null latest when no import exists |
| GET `/stores?search=1&page=1&page_size=25` | Store-ID substring search, stable ID order, one-based pagination, total, source cutoff and per-store forecast support; page size 1..100 |
| GET `/models/active` | Authoritative global V1 version pointer and generation; nullable pointer |
| GET `/models/versions` | All versions, lineage and measured decision evidence; alias of GET `/models` |
| POST `/forecasts` | 201 only after complete daily forecasts and request provenance commit |
| GET `/forecasts/{forecast_id}` | 200 frozen daily predictions, metadata and exact totals |
| GET `/forecasts/{forecast_id}/download.csv` | 200 attachment, one row per saved store/day |
| GET `/model/feature-registry` | Executable registry fingerprint, feature descriptions, serving requirements and excluded predictors |

Stores default to the active model's dataset, or latest import if no model is active. An optional `dataset_version_id` chooses another imported source for discovery only. Forecasting always uses its pinned model's dataset: importing a newer source does not silently change model context. `forecast_supported` distinguishes the imported 1,115-store catalog from the present fitted three-store cohort (1, 2, 3).

## Request and result

A minimal request:

```json
{"store_ids":[1],"cutoff_date":"2015-07-31","horizon_days":1}
```

PowerShell:

```powershell
$body = @{ store_ids = @(1); cutoff_date = '2015-07-31'; horizon_days = 7 } | ConvertTo-Json
$forecast = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/forecasts' -ContentType 'application/json' -Body $body
$forecast.points
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/forecasts/$($forecast.forecast_id)/download.csv" -OutFile "$env:TEMP/retailforecast.csv"
```

Bash:

```bash
curl -sS http://127.0.0.1:8000/api/v1/forecasts -H 'Content-Type: application/json' -d '{"store_ids":[1],"cutoff_date":"2015-07-31","horizon_days":7}'
```

The complete measured response is [FORECAST_RESPONSE_EXAMPLE.json](FORECAST_RESPONSE_EXAMPLE.json); [PHASE_10_REPORT.md](PHASE_10_REPORT.md) records its HTTP verification. It is an API prediction, not a claimed measured error or final-holdout score. The complete response includes:

- `forecast_id`, UTC `generated_at`, canonical request, and an `input_fingerprint` binding the visible input snapshot and model version.
- `model`: immutable version, algorithm, pointer generation, trained-through date and feature schema hash.
- `data`: imported dataset ID/fingerprint/checksum, latest source actual date, maximum visible actual date, per-store observed range/count/recent missing-date count, and explicit knowledge assumptions.
- `points`: ordered by target date then store ID, exactly `stores * horizon_days` values, each with horizon, predicted Sales, known opening state and adjustment flags. Target date is cutoff plus horizon.
- `totals`: grand total, store totals, daily totals, Monday-Sunday calendar week totals and calendar month totals. Partial periods expose requested covered dates and distinct forecast-day count, never estimates for unrequested dates.
- `policy` and `warnings`: historical dataset notice, missing/unseen input handling and evaluated output adjustments.

Sales JSON values are exact decimal **strings** with four places. Source currency is unspecified. Predictions round half-even once per store-day into PostgreSQL `NUMERIC(18,4)`; all totals sum those same rounded values. API aggregate amounts allow greater precision/range than an individual point. CSV uses the same four-place values. No separate portfolio model, errors, actuals or confidence bands are invented.

## Information availability and scenarios

The active native weights, saved preprocessing and registry schema are verified once per POST. A request pins the active version/generation before prediction. Concurrent activation or rollback can archive that version, but all points from the in-flight request retain its identity. GET and CSV need only the persisted database report, even if native files later become unavailable.

History SQL selects only store/date/Sales for requested stores with business date and declared sales-availability date at or before cutoff. Customers are never selected. Feature building and encoding reuse the training/backtest implementation. All horizons use the same frozen cutoff; July 31 to August 7 does not consume August 1-6 actuals. A model trained after the requested cutoff is incompatible. Missing recent dates remain missing and use saved preprocessing; completely absent per-store actual history is an error.

Future opening/promotion/holiday values remain unknown under the current model's `calendar_known_as_of=null` assumption. Neither future actual observations nor unlabeled test rows automatically prove a plan was known. Other models may consume source calendar columns only under their recorded explicit knowledge assumption. Static metadata follows the same saved availability context.

Optional `scenarios` are full replacement plans for selected store/target dates:

```json
{
  "store_ids":[1], "cutoff_date":"2015-07-31", "horizon_days":7,
  "scenarios":[{
    "store_id":1,"target_date":"2015-08-02","available_as_of":"2015-07-30",
    "provenance":"Opening plan approved July 30","is_open":false
  }]
}
```

Allowed values are `is_open`, `promotion`, `state_holiday`, `school_holiday`. At least one must be known; all omitted values remain unknown, including when replacing an existing plan. `available_as_of <= cutoff_date` is mandatory, and the date/store must be within the request. One plan per store/date is accepted; provenance is required. These are user assertions, not verified plans or causal uplift estimates. Sales, Customers, algorithms and hyperparameters are rejected. Unseen categorical values use the persisted unknown encoding and produce a warning.

The evaluated policy clips negative raw predictions to zero. Only an explicitly known closed day under `known_plan_zero` is forced to zero; unknown Sundays are not claimed closed. Adjustment flags expose what happened. Evaluation and serving call the same policy function.

## Errors and limitations

Domain/storage failures return `{"error":{"code":"...","message":"..."}}`; malformed input uses FastAPI's standard 422 `detail` list. Messages omit private paths, credentials and SQL parameters. A failure does not start training or change the active model.

| Status | Codes / meaning |
|---|---|
| 422 | Request schema validation; `unknown_store`, `unsupported_store`, `missing_history`, `cutoff_beyond_observed_data` |
| 404 | `forecast_not_found`, `dataset_not_found` |
| 409 | `model_trained_after_cutoff`, `dataset_incompatible`, `feature_schema_incompatible`, `invalid_history`, unsupported/nonfinite/out-of-range prediction or incomplete/incompatible stored report |
| 503 | `no_active_model`, `model_unavailable`, `forecast_busy`, `storage_unavailable` |

For example, use cutoff `2026-10-20` with the historical model:

```json
{"error":{"code":"cutoff_beyond_observed_data","message":"Choose a historical cutoff no later than 2015-07-31; this is not a live sales feed"}}
```

Supported cutoffs span model training date through latest source label date plus the model's recorded availability delay. Targets can extend 48 days beyond that cutoff without labeled outcomes; the API returns estimates, never accuracy claims. Source records from the locked final window may be visible as history when a user explicitly chooses a later serving cutoff; the evaluation holdout is not scored or used for selection by serving.

At most 32 distinct stores and 48 days are allowed; unknown or unsupported stores fail instead of silent fallback. One prediction runs at a time per API process, with a retryable busy response. Use one local API process; this is not a distributed inference queue. Native bundles are revalidated/reloaded per POST rather than cached, favoring integrity and transparent switching over minimum latency. There is no automatic stale-data extrapolation to today's date, retraining, inferred plan generation or forecast deduplication. Repeated identical POSTs save different run IDs/timestamps with identical values and input fingerprint.

One explicit SQL transaction commits context and every point after prediction and complete response validation. Failure rolls back the whole run. The source is an immutable imported snapshot, not a live editable stream. Forecast metadata freezes actual feature-input hashes and availability context but does not copy the entire training dataset into each report. Back up business tables, DVC data and native artifacts together. Legacy forecast rows without phase-10 provenance return a 409 rather than fabricated metadata.
