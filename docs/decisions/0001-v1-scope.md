# 0001 — V1 product scope

Date: 2026-10-19
Status: Accepted for product definition; implementation awaits later phases.

## Context
The project needs a working, auditable portfolio demo using historical Rossmann data on an 8 GB laptop without paid services. A historical dataset cannot support claims of current-live forecasting.

## Decision
Forecast daily per-store Sales for horizons 1–48 days. Support LightGBM, XGBoost, and budgeted Auto selection. Train when no suitable saved model exists and reuse the active compatible model afterward; do not retrain for each prediction. Permit optional manual/weekly/monthly/quarterly retraining after explicit new-label ingestion. Version models and record runs and feature provenance.

Use Python modules, FastAPI, React/Next.js TypeScript, Tailwind/shadcn/ui, Apache ECharts, Docker PostgreSQL, MLflow, and DVC, with CPU-first models. Keep architecture and implementation for subsequent phases. Exclude notebooks from product work, LLM features, promotion optimization, causal promotion claims, and automatic/live Kaggle feeds. Use promotion inputs only as non-causal predictors known at cutoff.

## Consequences and trade-offs
CPU-first operation reduces hardware requirements but constrains tuning speed. Local PostgreSQL, MLflow, and the web stack create memory pressure requiring measured budgets. Historical demos require explicit cutoffs and held-out labels. Local scheduling cannot run while the host is asleep/off. Saved-model reuse requires explicit compatibility and promotion rules. Feature availability and future Sales/Customers leakage demand dedicated tests. These details must be resolved during design without expanding V1 silently.
