# RetailForecast AI product specification

## Audience and purpose
A local-first portfolio application helps a non-technical retailer inspect historical store sales and modeled daily revenue, while allowing a technical reviewer to audit data preparation, evaluation, model versions, and reproducibility. Rossmann Sales are the daily target; do not invent currency units absent source confirmation.

## Source and information cutoff
Use the historical Rossmann Kaggle competition dataset. Its 2015 records are not current-live data. New Kaggle sales do not arrive automatically. Users must explicitly import new labeled observations; ingestion validates schema, dates, store identity, duplicates, and data availability. Respect dataset access terms and do not distribute raw files in Git.

A forecast has an explicit cutoff_date, selected store, and horizon_days from 1 through 48 inclusive. Actual sales are observed labels; forecasts are model estimates for dates after cutoff. Never use future actual Sales or future Customers as predictors. In backtests, those values remain hidden until scoring. Final competition test labels are not assumed available. Use known-label historical holdouts for honest demos.

## Three primary journeys
1. First use, no suitable saved model: user selects store, cutoff, horizon, and algorithm. Explain preparation, launch a bounded training run, show progress/errors, save a validated model, and produce forecasts after successful training. Do not show fabricated results while waiting.
2. Existing active model: validate compatibility and reuse it for prediction. There is no need to retrain for each prediction. Show its version, training cutoff, algorithm, evaluation, and any stale-data notice.
3. Optional retraining: after new labeled data is imported, user may trigger manual retraining or configure weekly/monthly/quarterly retraining. Keep the active model usable while a candidate trains. Failed candidates do not replace it. Record training runs and model versions; define promotion checks in a later design phase.

## Scope and algorithm semantics
V1 includes daily per-store forecasts, horizons 1–48 days, historical/forecast charts, exports, LightGBM, XGBoost, Auto, model reuse, retraining settings, run/version history, feature explanations, and evaluation. CPU-first implementation targets an 8 GB laptop and requires no external paid services.

LightGBM or XGBoost requests select that model family and a compatible saved model when available. Auto compares candidates using the same temporal validation folds, metrics, and declared CPU/time budget, then selects by documented policy. It must not imply exhaustive optimization or guaranteed superiority. Model compatibility and fallback policies must be explicit in the architecture phase; do not silently change the requested algorithm.

Exclude promotion optimization, causal uplift claims, LLM features, live data feeds, and production managed/cloud infrastructure. Promotion fields are non-causal predictive inputs only, used when their values were known at forecast cutoff. Do not recommend promotions based on correlation.

## Forecasts, explanations, and exports
Separate actual and forecast series visually. Identify cutoff, target dates, horizon, algorithm, model version, and missing data. Display genuine computed values. Explain features and errors in plain language. CSV export includes store_id, cutoff_date, target_date, horizon_days, forecast_sales, algorithm, and model_version; version any future schema changes. Do not present unsupported confidence bands.

## Evaluation and fair comparison
Use chronological holdouts/rolling-origin evaluation, never random row splits. Report RMSPE with zero actual Sales excluded from that metric and the exclusion count disclosed; report MAE and a simple seasonal baseline too. Document closed-store treatment, missing dates, and non-negative output policy before implementing them. Compare algorithms and baseline on identical dates/stores/cutoffs, features, and compute budgets; disclose selection folds and untouched final evaluation. Report per-store and aggregate coverage and errors so large stores do not hide poor performance elsewhere. Never hardcode scores or claim universal algorithm superiority.

## UI pages
- Forecast: store/cutoff/horizon/algorithm selection, real history/forecast chart, status, export.
- Data: imported dataset identity, coverage, quality issues, availability assumptions.
- Models and runs: active version, candidate states, reproducibility details, comparisons and failures.
- Evaluation and explanation: temporal splits, metrics, baseline, feature provenance and limitations.
- Settings: local paths/resources and optional retraining schedule.

## Local scheduling and implementation constraints
The local app/scheduler must be running for scheduled work; laptop sleep/shutdown prevents execution. Explain missed-run policy once designed; do not promise background cloud uptime. Retraining needs new labeled data, not merely a timer tick. Prevent overlapping jobs and surface failures. Use Python modules (no notebooks), FastAPI, React/Next.js TypeScript, Tailwind/shadcn/ui, Apache ECharts, Docker PostgreSQL, MLflow, DVC, quality tooling, tests, diagrams, and documentation. Detailed boundaries and resource limits belong to the architecture phase.

## Acceptance criteria
- Given no suitable saved model, when a user requests a valid forecast, then a recorded training run produces a validated model before real predictions appear, or shows an actionable failure.
- Given a compatible active model, when another prediction is requested, then it reuses that model without retraining.
- Given horizon 1 or 48, when a forecast succeeds, then exactly that many daily target dates follow the cutoff; invalid horizons are rejected.
- Given changed post-cutoff actual Sales or Customers, when features/predictions are recomputed with a fixed model, then those changes cannot affect them.
- Given known-at-cutoff promotion plans, when they enter features, then provenance is recorded and the UI makes no causal uplift or optimization claim.
- Given historical Kaggle records, when users view the app, then data dates and cutoff are explicit and no current-live or automatic new-sales claim appears.
- Given new validated labels and a requested retraining run, when it fails, then the previous active model remains usable and failure details are recorded.
- Given no new labels, when a scheduled retraining check runs, then it records a skip rather than implying fresh data arrived.
- Given a stopped local scheduler, when a scheduled time passes, then the product does not claim the run executed.
- Given model comparisons, when results are displayed, then they use identical temporal evaluation slices and computed metrics with coverage and zero-label handling disclosed.
- Given a successful forecast, when exported, then CSV values match the displayed predictions and identify cutoff/model version.

## Demo strategy
Use a documented historical cutoff with labeled subsequent dates for 1–48-day forecasts. Show first training, reuse without training, actual versus predicted values, honest baseline comparison, export, and optional retraining after simulated explicit label import. Distinguish the historical simulation from live operation. Keep runs reproducible on CPU; record timings and resource limitations rather than promising a speed target before measurement.
