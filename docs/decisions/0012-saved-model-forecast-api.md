# 0012 - Serve pinned models and persist exact daily forecasts

Date: 2026-10-20. Status: implemented in Phase 10.

## Decision

ForecastService resolves one global-v1 model version/generation per request, verifies and loads its native bundle/preprocessing, and keeps that object while predicting. Use its exact imported dataset, shared as-of feature builder and evaluated output policy. SQL physically excludes post-cutoff/unavailable Sales and all Customers. Future plans require the saved explicit knowledge assumption or a validated declared scenario; missing means unknown.

Do not train from a forecast request. Restrict cutoff to model fit date through source observed-through plus configured availability delay; later targets may be unlabeled predictions. Expose all source/actual/request/generation dates. A new import cannot silently change an old model's data context. Current native models cover only stores 1,2,3.

Validate the complete response before one SQL transaction publishes run metadata and all points. Store full versioned context, input fingerprint, scenario provenance, dataset/model/schema identities, actual-history coverage, adjustment policy and UTC event timestamp. Round daily outputs half-even to four decimal places; sums and CSV use those exact saved values, with decimal strings in JSON. Partial calendar periods disclose coverage. Forecast reads never require a model reload or active slot and therefore survive a subsequent switch or missing model file.

## Trade-offs

Reload and integrity verification per POST avoids stale/corrupted process-cache behavior and simplifies pinning. It costs I/O/latency compared with caching; introduce a bounded checksum-aware immutable-version cache only after measurement. One in-process semaphore and 32-store/48-day bounds suit one laptop API process; they are not a distributed queue or a memory watchdog. Large serialized artifacts remain files, not SQL rows.

Repeated requests create new report IDs/timestamps, with identical points and input fingerprint for unchanged input/model. No request deduplication, automatic cohort expansion, current-date extrapolation, scenario causal claim, automatic plan inference or retraining fallback is introduced. Storage/domain errors are typed and sanitized. Legacy reports without context fail replay explicitly.

## Evidence

Real PostgreSQL tests cover future Sales mutation/erasure, SQL/Parquet feature parity, unknown categories, closures, gaps, exact totals/CSV, failed point inserts, unavailable artifacts, model switches during prediction and no fitting. The local HTTP smoke uses actual active LightGBM weights without changing model/training/source state; PHASE_10_REPORT.md records the commands and measured outputs. The final evaluation holdout remains unscored.
