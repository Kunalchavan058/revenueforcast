# Business Overview and saved-model Forecasts

Phase 13 implements both browser pages using real imported SQL data and saved-model responses. No browser route substitutes sample results. The existing operator import contract supplies historical actuals; upload/settings forms remain separate later work.

## Run locally

Follow README to start Docker PostgreSQL and apply migrations. From the repository root, in PowerShell or bash, run `npm run dev` for the normal API on 8000 and web on 3000. Restart already-running API/web processes to load new endpoints. A training worker is not required to reuse an active saved model. If no active version exists, Forecasts links to Model Studio rather than starting training.

## Overview

The source is explicitly the latest historical import, or an API-pinned dataset ID. Default dates are the last 28 calendar days within observed coverage; today's date never replaces the dataset end. Default stores are the first three observed stores, or fewer if fewer exist. Select 1–32 stores, an inclusive ordered interval of at most 1,096 days, then **Apply filters**. Search/paging can browse every imported store, independent of model coverage. Pending edits are labeled; displayed/exported filters remain the last applied values until application.

Observed Sales, selected-store count, observed/expected store-days and open/closed counts come from SQL. Daily, Monday–Sunday weekly and calendar-monthly totals use the same shared calendar helper as forecast totals. Calendar buckets disclose the actually requested subrange. Missing store-days are counted separately and never imputed as zero; a bucket without observations has a null amount, while a genuine zero remains zero. Means divide by observed store-days and include closed-store zeros. Recorded closed-positive Sales quirks remain in totals and are disclosed.

Store comparison totals use identical selected dates. Weekday patterns use mean Sales per observed store-day, with their denominator in the accessible data table. Historical Open is a known source field; it does not establish future opening hours. Tooltips, visible Sales-unit axes and keyboard-readable tables accompany charts. The observed CSV contains exactly the applied source/checksum/cohort/date/grain, coverage counts and four-decimal period totals. Two-decimal display formatting does not change stored/exported precision. No currency symbol is inferred.

## Forecasts

Read-only setup verifies the active saved model/source and lists supported stores with actual history. Defaults select at most three stores and a seven-day horizon. A selection can contain at most 32 stores; horizon is 1–48 days. The form computes selected-store overlap plus saved training date and declared sales-availability delay. The latest allowed as-of date is the minimum selected-store latest observation plus delay; it may be earlier than global source coverage. This conservative UI avoids implying every store has equally fresh inputs. The API remains authoritative and reports missing/gapped history explicitly.

**Generate Forecast** is the single prediction action. Visiting, changing filters, choosing a store view or selecting weekly aggregation never calls training. A new POST uses the currently active model; every result displays the actual returned immutable version and as-of date, even if the active pointer changed after form setup. A changed-input notice keeps existing results tied to their saved request. Errors never trigger an automatic fit or fabricate replacement points.

Daily forecasts use only observations available by the fixed cutoff for all horizons. The chart separately loads a 28-day observed preview from the response's exact immutable source, ending at the returned actual-data cutoff. Actuals after that cutoff are never requested for display. A vertical dotted **Last observed date** marker, solid-blue actual series and dashed-teal prediction series expose the boundary. A one-day forecast renders a point so it remains visible. Actual chart totals can have partial store-day coverage; missing points remain gaps. Estimates are not guarantees, future plans remain unknown, and no confidence band or promotion decision is invented.

All-store and per-store views read saved values. Daily and weekly totals use the existing server Decimal aggregation helper rather than a second browser arithmetic implementation. Weekly coverage exposes partial first/last weeks. Tables page 48 rows at a time. The CSV is the existing immutable daily forecast export and always contains the complete originally selected cohort, regardless of the current store view; that scope is stated beside the download. No prediction or model load is required for saved view/export retrieval.

## Supporting API contracts

All routes use /api/v1. Full schemas are in openapi.json.

| Route | Contract |
|---|---|
| GET /history/coverage | Actual date bounds, observed-store count, immutable dataset/checksum, bounded default IDs; null coverage without import |
| GET /history/summary | Required dataset_version_id, repeated store_ids, start_date/end_date and optional frequency=day/week/month; exact total, covered calendar series, per-store/weekday data and missing/open/closed counts |
| GET /history/download.csv | Same query and same aggregation/provenance as summary |
| GET /forecasts/options | Validated active version, compatible certified-descendant source, supported store coverage and declared label delay; no side effect |
| POST /forecasts | Existing saved-model prediction/persistence contract; no fitting |
| GET /forecasts/{id}/view?store_id=... | Optional one-store saved subset, exact daily/weekly/monthly totals and actual coverage; no new inference |
| GET /forecasts/{id}/download.csv | Original full saved cohort with model/cutoff/source metadata |

Example historical query, usable in either shell with curl:

```text
curl "http://127.0.0.1:8000/api/v1/history/summary?dataset_version_id=YOUR_DATASET_UUID&store_ids=1&store_ids=2&start_date=2015-07-04&end_date=2015-07-31&frequency=week"
```

Use the UUID returned by coverage; dates/IDs above are illustrative, not fabricated results. Reversed/outside-source dates, >1,096 days, duplicate/unknown stores or >32 selected stores return actionable validation errors. Missing dataset is 404; missing/corrupt active model is explicit. Empty actual selections return null amounts/zero observation counts, never invented zero-sales days. Historical reports describe observed outcomes and do not measure forecast error or unlock the final holdout.

## Verification and limits

The reporting package is a deliberate domain boundary under the existing single src/retailforecast root: business aggregation does not belong in model fitting/evaluation. PostgreSQL performs reduction to at most 1,096 daily, 32 store and seven weekday rows. No raw SQL history is downloaded wholesale to the browser. Source datasets are immutable and explicit, making the multiple read queries stable under legitimate append-only imports. The business schema and model features are unchanged.

The phase report/log records hand-computed real-PostgreSQL tests, request/render/no-training component integration tests, real dev-server/browser screenshots, accessibility checks, actual smoke results and known limits. Browser transport fixtures are labeled test-only. Real local smoke uses the historical LightGBM model, not a sample prediction.

When another dev server owns .next/dev/lock, set PLAYWRIGHT_DEV=1 with isolated API/web ports per TRAINING_JOBS.md. Test development output then goes into ignored .next-browser; normal output remains .next. The verification restores any generated TypeScript include changes and the normal API proxy after stopping its owned test servers. This does not stop the operator's existing dev server. Production/default CI browser mode remains unchanged.
