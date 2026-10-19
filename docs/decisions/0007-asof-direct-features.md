# 0007 — Explicit as-of direct features

## In plain English

Every forecast row carries its own information cutoff. Actual labels, metadata and planned inputs have different knowledge rules. A missing plan remains unknown; a convenient future CSV row is not evidence that its flags were known earlier.

Date: 2026-10-19. Status: implemented Phase 6, without estimator training.

## Decision

Use one pure Python builder with typed immutable source contracts and explicit per-store/date indexes, exact calendar lags and inclusive calendar windows. No DataFrame shift can cross stores or silently compress missing dates. Filter both observation and availability dates. Full as-of metadata/plan revisions replace earlier snapshots; ambiguous equal-time revisions fail.

The Python registry generates the reference and determines feature/preprocessor order. Customers are projected out entirely; target labels are attached only by the supervised iterator. Default horizons are 1..48; fold label end constrains target date and availability, not just origin. Do not materialize all store/origin/horizon combinations at once.

Persist training-only medians, missing indicators and sorted categorical vocabularies as validated JSON, including registry fingerprint, fold end and dataset assumptions. Missing/unseen category codes are distinct. A future estimator adapter must handle ordinal category identifiers explicitly and persist this same object with its model. Serving never fits and refuses preprocessing learned beyond the forecast cutoff.

## Trade-offs

Archived Rossmann files do not prove publication dates. The loader requires written simulation assumptions and loads no target plans by default; real dated plan revisions can be passed directly. Promo2 expansion is allowed only for an asserted known schedule; missing components remain unknown. Static metadata also requires an as-of snapshot.

Simple Python indexes favor auditability over maximum throughput. Parquet projection/batches and bounded store partitions avoid loading the complete expanded dataset. Exact median fitting has an explicit 50,000-row cap; future larger-scale training must deliberately revise resource handling. Missing coverage is exposed rather than inventing zero actuals or masking cold-start uncertainty.

Model accuracy, categorical estimator integration, temporal evaluation runners, model approval and UI/API features remain future work. FEATURES.md and the generated registry are the current implementation contracts.
