# 0015 - Bounded SQL business reporting and saved forecast views

Date: 2026-10-20. Status: implemented in Phase 13.

## Decision

Keep historical business reporting in src/retailforecast/reporting within the existing installable package. Query explicit immutable sources with selected stores and inclusive dates. SQL reduces actuals before sending calendar/store/weekday aggregates; shared calendar bounds and exact Decimal sums keep JSON/CSV consistent. Preserve null versus zero and closed-positive source quirks, report denominators and avoid assuming currency.

Forecast setup verifies the active model's compatible source/cohort without inference. The UI constrains cutoff to selected-store overlap, fit date and recorded label delay. Only an explicit Generate action POSTs inference, never training. Results display returned version/source/cutoff. Display history ends at returned actual-data cutoff; the chart marks that date and uses separate actual/predicted series. Per-store/weekly views reuse saved values and server aggregation, with full-cohort CSV scope disclosed.

## Trade-offs

Overview defaults to three stores and the latest observed 28-day interval, with explicit 32-store/1,096-day bounds rather than unbounded laptop/browser scans. Apply filters separates draft edits from displayed/exported context. Missing store-days are not imputed and partial calendar coverage is explicit. Current data/model remain historical and the trained model covers a small cohort. Existing import/operator workflows remain separate from this dashboard phase.

Read-only reporting does not alter labels/features, train/retrain, score the locked holdout or implement promotion planning. Multiple read queries rely on immutable application-published snapshots. A small saved-subset endpoint reuses existing decimal aggregation instead of duplicating calendar/financial arithmetic in TypeScript. Development browser verification uses ignored isolated Next output when the operator already has a dev server; normal ports/build are restored afterward.

## Evidence

DASHBOARDS.md documents contracts/units/missingness and operator behavior. PHASE_13_REPORT.md records actual tests, dev/browser smoke, screenshots and any runtime limits. Existing saved-model temporal/persistence tests remain regression coverage.
