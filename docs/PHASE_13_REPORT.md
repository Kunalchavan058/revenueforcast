# Phase 13 implementation and verification report

Date: 2026-10-20. Scope: functional Business Overview and Forecast dashboard. Phase 12's foundation is preserved. Verification preceded subsequent user-authorized logical commits; see IMPLEMENTATION_LOG.md. No GitHub push.

## Delivered behavior

Overview now computes real historical date coverage, selected-store count, observed Sales, daily/weekly/monthly totals, per-store comparison, mean weekday patterns and recorded open/closed counts. Its source is an explicit immutable SQL import; date defaults use the last observed 28-day interval, not today. Searchable multi-store filters default to three stores and cap at 32; reporting intervals cap at 1,096 inclusive days. Draft edits are distinct from applied results/export. CSV uses exactly the same source/checksum/cohort/date/grain, amounts and coverage.

SQL reduces source records to bounded daily/store/weekday aggregates. A missing store-day is not a closed day or zero Sales. Buckets without observations return null; genuine zero stays zero. Closed-positive source quirks remain in totals with disclosure. Means divide by observed store-days, including closed zeros. Shared calendar bounds keep actual and predicted weekly/monthly logic aligned; decimal aggregation and four-place export are server-owned.

Forecasts reads validated active-model/source/cohort metadata, constrains as-of selection to selected-store observed overlap plus saved fit date and declared label delay, supports 1–48 days, and has one explicit Generate Forecast action. It never trains. Missing models link to Model Studio; absent history and API errors are explicit. Results identify the actual returned saved version, cutoff and source. A changed-input notice prevents old results being mistaken for a new request.

The real ECharts chart keeps solid-blue historical actuals and dashed-teal predictions distinct, with a vertical dotted Last observed date line and a visible marker for a one-day series. Preview-history queries use the saved response's exact source and end at its actual-data cutoff, never future actuals. Per-store and weekly views reuse persisted values and existing server Decimal totals. Tables are paged and keyboard-scrollable; CSV remains the original complete saved cohort and its scope is stated. Values use Sales units, never an assumed currency. No promotion planning or unsupported confidence/accuracy claims were added.

## Real local evidence

The real source contains 1,017,209 labeled rows from 2013-01-01 through 2015-07-31 across 1,115 stores. The default Overview cohort, stores 1,2,3 over 2015-07-04..2015-07-31, produced **381752.0000 observed Sales units**, 84 observed store-days, zero missing store-days, 72 open and 12 closed store-days. These values were recomputed from imported SQL data, not configured in the UI.

A genuine dev-browser request deselected store 3 and generated seven days for stores 1,2 from cutoff 2015-07-31: 14 saved daily predictions totaling **55350.0306 source Sales units**. This is a model estimate, not an accuracy score. It reused LightGBM version c0e51310-98a8-4c34-afd9-ca658fbcd468, generation 2, fitted through 2015-06-13. The observed line ended July 31; the prediction series covered August 1–7. Download and weekly-view actions worked. Browser monitoring found no POST training-jobs request from Forecasts.

At evidence capture, real business state was one dataset, 1,017,209 daily-sales rows, three model versions, six decision events and one pre-existing skipped training job. Genuine browser tests add saved forecast runs/points; no import, training job, model version or activation is needed. Additional reruns can add another identical-value forecast with a distinct ID/timestamp by the established API contract. Original final-holdout release remains untouched. Detailed aggregate/request/count evidence is ignored under artifacts/phase13/evidence.json.

The following real dev-server captures were visually inspected; the mobile Overview capture waits for all three plotted charts rather than loading skeletons:

- [Overview desktop](screenshots/phase13/overview-desktop.png)
- [Overview mobile](screenshots/phase13/overview-mobile.png)
- [Forecast desktop](screenshots/phase13/forecast-desktop.png)
- [Forecast mobile](screenshots/phase13/forecast-mobile.png)

## Commands and results

Commands ran from the actual repository root using locked .venv Python and portable Node 22.23.3 on PATH. No new dependency was added in Phase 13; the Phase 12 npm changes were still uncommitted at verification time.

| Command/check | Actual result |
|---|---|
| `.venv/Scripts/python.exe -m pytest tests/test_business_reporting.py -q --tb=short -x` | 12 passed in 15.61 seconds: exact hand totals, missing/closed/zero cases, partial calendars, mutation/filter changes, null empty history, HTTP/CSV and invalid queries |
| `.venv/Scripts/python.exe -m pytest tests/test_business_reporting.py tests/test_forecast_api.py tests/test_health.py -q --tb=short` | 49 passed, one existing MLflow/SQLAlchemy deprecation warning, 137.36 seconds |
| `.venv/Scripts/python.exe -m mypy` | Success: 97 source files after HTTP test parameter typing correction |
| `.venv/Scripts/python.exe -m ruff check .` / `ruff format --check .` | All checks passed; 149 files already formatted |
| `npm.cmd run test --workspace apps/web` | 45 passed across five files; post-correction run 70.23 seconds; final post-accessibility run: 45 passed in 40.16 seconds |
| `npm.cmd run lint --workspace apps/web` / `typecheck` | ESLint and strict TypeScript passed after the schema/keyboard corrections |
| `npm.cmd run build --workspace apps/web` | Optimized Next build/type checks passed; final normal-port rebuild: passed with API proxy restored to 127.0.0.1:8000 |
| `.venv/Scripts/python.exe artifacts/phase13/dev_smoke.py` | 7 passed in 17.4 seconds on current real API/Next dev; mobile capture strengthened and 1 targeted test passed in 7.6 seconds |
| `npm.cmd exec -- prettier --check .` | All matched files use Prettier code style |
| Migration/lock/DVC/registry contracts | Alembic reports no new operations; lock resolves 148 packages; DVC up to date; generated feature registry current |
| Publication exclusions, relative documentation links, `git diff --check` | passed; no credentials/private paths/raw CSV/model binaries in changes; no CSV tracked; screenshot provenance/relative links verified; normal tsconfig restored |

Tests assert selected stores modify requests, real response values/model metadata render, display history ends at actual cutoff, missing-model/error behavior never fabricates results, and no training request fires. Existing 1/7/48-day, no-fitting, future-mutation, persistence, totals, cohort/schema and forecast migration regressions remain passing in the 49-test backend run. Saved one-store/weekly views are checked against filtered original points with exact server sums. The chart lifecycle test checks actual/predicted line patterns, one-day visibility and the vertical observed marker.

The initial browser pass caught an Overview schema argument introduced during cleanup, which was corrected. The accessibility audit then identified the vertically scrollable report table's missing keyboard focus; named focusable scroll regions now cover report/result tables. Tests were not skipped or replaced. A dev navigation compile took about five seconds, so dev-only expectation time allows compilation while production expectations remain unchanged.

The operator's existing Next server initially owned .next/dev/lock. Test development output uses ignored .next-browser, separately owned API 8001/web 13000 and captured local logs. The dev helper supervises only its own processes, restores Next-generated TypeScript include changes and stops its servers afterward. Production build/proxy is restored to normal port 8000. No user's existing process is deliberately stopped.

## Changed-file inventory

At phase verification, Phase 12 was uncommitted, so this inventory includes its preserved foundation as well as Phase 13 changes. It records the working tree before the subsequent user-authorized logical commits.

- `.gitignore`
- `.prettierignore`
- `README.md`
- `apps/web/e2e/health.spec.ts`
- `apps/web/eslint.config.mjs`
- `apps/web/next.config.ts`
- `apps/web/package.json`
- `apps/web/playwright.config.ts`
- `apps/web/src/app/[workspace]/page.tsx`
- `apps/web/src/app/error.tsx`
- `apps/web/src/app/forecasts/page.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/app/layout.tsx`
- `apps/web/src/app/loading.tsx`
- `apps/web/src/app/model-studio/page.tsx`
- `apps/web/src/app/not-found.tsx`
- `apps/web/src/app/page.tsx`
- `apps/web/src/components/charts/category-chart.tsx`
- `apps/web/src/components/charts/sales-chart.tsx`
- `apps/web/src/components/charts/types.ts`
- `apps/web/src/components/dashboards/forecast-dashboard.tsx`
- `apps/web/src/components/dashboards/forecast-results.tsx`
- `apps/web/src/components/dashboards/overview-report.tsx`
- `apps/web/src/components/foundation/chart-shell.tsx`
- `apps/web/src/components/foundation/data-freshness-notice.tsx`
- `apps/web/src/components/foundation/date-range-picker.tsx`
- `apps/web/src/components/foundation/empty-state.tsx`
- `apps/web/src/components/foundation/error-banner.tsx`
- `apps/web/src/components/foundation/icon.tsx`
- `apps/web/src/components/foundation/job-status.tsx`
- `apps/web/src/components/foundation/methodology-hint.tsx`
- `apps/web/src/components/foundation/metric-card.tsx`
- `apps/web/src/components/foundation/multi-store-picker.tsx`
- `apps/web/src/components/foundation/page-header.tsx`
- `apps/web/src/components/foundation/store-picker.tsx`
- `apps/web/src/components/training-control.tsx`
- `apps/web/src/components/ui/badge.tsx`
- `apps/web/src/components/ui/button.tsx`
- `apps/web/src/components/ui/card.tsx`
- `apps/web/src/components/ui/input.tsx`
- `apps/web/src/components/ui/skeleton.tsx`
- `apps/web/src/components/workspace/app-shell.tsx`
- `apps/web/src/components/workspace/overview.tsx`
- `apps/web/src/components/workspace/workspace-provider.tsx`
- `apps/web/src/components/workspace/workspace-status.tsx`
- `apps/web/src/lib/api/catalog.ts`
- `apps/web/src/lib/api/client.ts`
- `apps/web/src/lib/api/dashboards.ts`
- `apps/web/src/lib/api/training.ts`
- `apps/web/src/lib/api/transport.ts`
- `apps/web/src/lib/api/use-api-resource.ts`
- `apps/web/src/lib/dashboard-dates.ts`
- `apps/web/src/lib/format.ts`
- `apps/web/src/lib/navigation.ts`
- `apps/web/tests/dashboard-fixtures.ts`
- `apps/web/tests/dashboards.test.tsx`
- `apps/web/tests/foundation.test.tsx`
- `apps/web/tests/sales-chart.test.tsx`
- `docs/API_CONTRACT.md`
- `docs/ARCHITECTURE.md`
- `docs/CODING_STANDARDS.md`
- `docs/DASHBOARDS.md`
- `docs/DATA_DICTIONARY.md`
- `docs/IMPLEMENTATION_LOG.md`
- `docs/PHASE_12_REPORT.md`
- `docs/PHASE_13_REPORT.md`
- `docs/ROADMAP.md`
- `docs/TRAINING_JOBS.md`
- `docs/UI_DESIGN.md`
- `docs/decisions/0014-frontend-foundation.md`
- `docs/decisions/0015-business-history-and-forecast-dashboards.md`
- `docs/openapi.json`
- `docs/screenshots/phase12/overview-desktop.png`
- `docs/screenshots/phase12/overview-mobile.png`
- `docs/screenshots/phase13/forecast-desktop.png`
- `docs/screenshots/phase13/forecast-mobile.png`
- `docs/screenshots/phase13/overview-desktop.png`
- `docs/screenshots/phase13/overview-mobile.png`
- `package-lock.json`
- `services/api/main.py`
- `services/api/reporting.py`
- `src/retailforecast/forecasting/totals.py`
- `src/retailforecast/reporting/__init__.py`
- `src/retailforecast/reporting/contracts.py`
- `src/retailforecast/reporting/history.py`
- `src/retailforecast/reporting/options.py`
- `tests/test_business_reporting.py`
- `tests/test_forecast_api.py`

## Readability, temporal review and limits

Reviewed explicit typed public contracts/docstrings, focused reporting/options/HTTP/client/view modules, shared calendar and Decimal arithmetic, bounded settings and comments explaining missingness, frozen result context and display-history cutoff. The reporting package is a documented refinement under the existing single Python package, separating business descriptions from model scoring. Coding standards, architecture, API/OpenAPI, UI guide, README, roadmap, decision 0015 and log explain current behavior.

Reporting can display historical observed outcomes, including dates from the reserved evaluation window, but does not score, tune or fit that holdout. No Customers column enters reports or predictors; no feature/training/database schema change was made. Raw competition data, generated models, credentials and ignored development/smoke outputs remain excluded from Git. Real screenshot aggregates/predictions are deliberate review artifacts, not raw dataset publication.

The current saved model supports stores 1,2,3 only; Overview can explore other imported stores independently. New upload/schedule/settings/experiment/feature-explorer workflows, promotion planning, causal recommendations and hosted deployment remain outside this phase. No dark mode or broad manual screen-reader/OS calendar/zoom audit is claimed. Existing whole-training/scheduling tests were not unnecessarily repeated because their code is unchanged; relevant shared calendar/forecast regressions passed. Restart normal API/web to use the added endpoints and pages. Implementation stopped after Phase 13; subsequent commits were explicitly requested by the user. No GitHub push.
