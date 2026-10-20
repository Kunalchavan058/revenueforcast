# Coding standards

This is a living, required reference. Read and enforce it before every code change in every phase. Update it when conventions change; review readability, docstrings, and comments before completion.

## Names, types, formatting, and boundaries
Use domain names such as `forecast_sales` and `store_id`, not `do_it`, `x`, or unexplained abbreviations. Use snake_case for Python functions/variables, PascalCase for classes, and UPPER_CASE for constants. Use camelCase for TypeScript values/functions and PascalCase for components/types. Declare Python parameter and return types and explicit TypeScript boundary types; avoid unvalidated `Any` or `any`. The Phase 3 tooling baseline uses Ruff for Python formatting/lint, strict mypy, strict TypeScript, ESLint with TypeScript/React Hooks rules, and Prettier. Direct versions and transitive resolutions are pinned in pyproject.toml, package.json, uv.lock, and package-lock.json; update them deliberately with full checks.

Keep functions short and focused on one responsibility. Separate UI, HTTP contracts, ML/features, persistence, scheduling, and artifacts. Prefer direct implementations over clever abstractions. Define input shape, units, valid ranges, output shape, and error behavior at public boundaries.

## Documentation and comments
Give public modules, classes, and functions concise docstrings describing purpose, inputs, outputs, and relevant caveats. Explain non-obvious algorithms and business assumptions. Comments should explain why a choice is necessary, especially cutoff logic, temporal joins, windows, evaluation, and training states.

Bad:
```python
# Add one.
x = x + 1


def calc(df):
    return df["Sales"].shift(1)
```

Good contract example (illustrative, not an implemented API):
```python
from datetime import date, timedelta


def latest_observed_date(target_date: date, horizon_days: int) -> date:
    """Return the forecast cutoff for a target and positive horizon in days."""
    if horizon_days < 1:
        raise ValueError("horizon_days must be positive")
    return target_date - timedelta(days=horizon_days)
```

Useful comment example:
```python
# Restrict labels to the cutoff before building windows: shifting alone
# would expose holdout sales for later dates in a multi-day forecast.
```

Do not comment trivial assignments, obvious loops, or syntax. Avoid stale narrative; refactor confusing code before adding lengthy explanations. Examples must not be mistaken for finished feature implementations.

## Temporal contracts and feature provenance
Use `cutoff_date`, `target_date`, `horizon_days`, and `available_as_of` consistently. State inclusive/exclusive boundaries. Store event timestamps in UTC and preserve daily store business dates without timezone-induced date shifts.

For every feature, document source columns/version, grain and join keys, transformation, lookback/window boundaries, missing-value policy, availability time, and how availability is checked against the cutoff. Validate chronological ordering and store boundaries. Historical lags and rolling statistics may use only observations available as of the cutoff. A horizon of several days does not permit reading intermediate future actuals. Any recursive predictions must be documented as predictions, never actuals.

Future Sales are the unknown target; future Customers are also unavailable at prediction time and correlate with sales. Neither can be used as future predictors. Planned promotion inputs are allowed only when known at cutoff and are non-causal associations, not evidence of promotion uplift. Calendar facts and planned inputs need explicit availability assumptions.

## Configuration, errors, and logging
Use named validated settings for horizons, seeds, paths, tuning limits, and scheduling policies. Pin dependencies in the implementation phase. Keep secrets outside source control. Raise actionable, typed/domain-appropriate errors; never silently substitute fake results. Use structured logs with UTC time and run/model IDs. Do not log credentials, raw secrets, or unnecessary data rows. Surface incomplete/failed training without replacing the active model.

## Tests and reproducibility
Test observable behavior with tiny hand-checkable examples. For example: with cutoff 2015-06-30, a target on 2015-07-02 cannot use actual sales from 2015-07-01. Changing all post-cutoff Sales/Customers must leave predictors and fixed-model predictions unchanged. Test store isolation, horizon boundaries 1 and 48, missing dates, temporal joins, rolling windows, failed training, and model reuse. Use identical rolling-origin splits for algorithm comparisons; record seeds, configuration, source revision, dataset identity, and environment. Explain nondeterministic library limitations where relevant.

## Architecture and visual explanations
Follow `docs/DIAGRAM_STYLE_GUIDE.md` for editable Mermaid and required narrative. Use Data, Features, Train, Evaluate, Approve, Predict consistently. Document contracts, availability/cutoff, failure behavior, and persistence ownership before implementation. Keep attempt statuses distinct from approval roles. Proposed resource limits are configuration, never measured performance. Update architecture and decision records when boundaries change.

## Starter HTTP and UI contracts
Health means API liveness only, not storage/model readiness. Validate external JSON as unknown with a typed runtime schema. Show loading until the real response arrives; expose offline/invalid-response states and retry without fake successful data. API/frontend behavior changes need contract, component, and appropriate browser checks. The legacy Colab notebook is excluded from product tools and is not a domain package. Keep public functions typed and documented; use a single Python package root. Portable local tools and caches stay ignored.

## Database and ingestion conventions
Use SQLAlchemy 2-style Mapped annotations with one metadata root and frozen explicit Alembic operations. Do not import live model metadata to recreate an old revision. Business transactions are owned by the ingestion/application boundary; batch helpers never commit. Keep failure audit writes separate from rollback of business rows, and serialize idempotent publication with database constraints/locks rather than a racy pre-check alone. UTC events and source business dates must remain distinct. Preserve actual labels, unknown Open and optional metadata; never impute zero observations during import. Source/report contracts belong in data modules, persistence in storage, CLI orchestration in import_rossmann. Normal tests use real isolated PostgreSQL schemas and must fail visibly when infrastructure is missing.


## File artifact reproducibility
Use configs/data.yaml as the single preprocessing configuration. Pin validation bounds, explicit Arrow schemas, batches and source order. Exclude wall-clock times and private paths from artifact identity. Normalization preserves labels/missingness and is not feature engineering. Bind reports/receipts to code/config/lock and verify before manifest consumption. A scoped mypy import exception covers PyArrow's untyped native API; owned interfaces remain explicitly typed and schema/runtime tests verify that boundary. DVC versions files, never PostgreSQL rows; private remote locations belong only in ignored config.local.

## As-of feature conventions

Use the generated Python feature registry as the sole feature-description/order contract. Regenerate FEATURE_REGISTRY.md and run --check after changing it. Features must use both business-date and knowledge-date gates. Name exact calendar lags with _from_cutoff and inclusive means with _through_cutoff; never shift across stores or substitute a previous row for a missing date. Full dated plan/metadata revisions replace earlier snapshots, including explicit unknowns. Customers are forbidden entirely. Keep labels outside FeatureRow.

Fit preprocessing only within the selected training fold; persist medians, category vocabulary, feature order, registry identity and dataset/availability context. Inference applies saved state and rejects fit dates beyond its cutoff. Keep the explicit training transform separate from serving's temporal guard, sharing value conversion. Missing flags distinguish model imputation from facts. Bound selected stores and fit rows; reject oversized work rather than silently sampling. Test future mutations and hand-check inclusive dates whenever temporal logic changes.

## Evaluation boundaries and honest coverage

Pass physically cutoff-filtered TrainingHistory into forecaster adapters; do not pass scoring outcomes or the complete label-bearing builder. Generate all forecasts before loading/joining truth. Known-at-cutoff Open and retrospectively observed Open must have separate fields. Keep optional actual/error values null when unsupported/unavailable; never manufacture zero labels or epsilon denominators to make metrics defined. Compare common target/support masks, report exclusions and retain zero actuals in business metrics.

Reserve chronological development/final windows before scores exist. Only development summaries may select methods. Persist data/config/source/lock/registry identities, fold cutoffs and seed; do not include volatile timestamps/private paths in deterministic result identity. Final release validates frozen development evidence, records a claim and caches completed results; a changed choice cannot silently re-open the same holdout. Treat local receipts as auditable workflow state, not a security guarantee. Preserve incomplete runs for inspection rather than automatic deletion.

## Native training and model bundles

Keep algorithm adapters independent of CLI/tracking/process supervision. Build fold-local matrices only from TrainingHistory through the shared feature builder; preserve target/availability boundaries, origin sampling and row-cap provenance. Encode arbitrary category IDs explicitly, persisting vocabulary/order with the model. Native parameters and actual metrics must be logged; never expose tuning knobs in normal product flows or silently substitute model families.

One coordinator owns the training lock and watchdog. Native fitting happens in an owned child with CPU, memory and elapsed bounds; stage and validate native/JSON bundles before publication. Failures retain audit artifacts and do not mutate prior models or serving pointers. Use native model formats rather than pickle; verify file checksums, feature order, data context, versions, supported stores/horizons and trained-through cutoff before prediction. Reuse existing evaluation adjustments/metrics rather than creating a divergent scoring path. Log runtime separately from deterministic candidate identity and keep final targets out of fitting/selection.


## Model lifecycle transitions

Keep experiment runs, registry references and application approval roles distinct. Seal immutable bundles/manifests before publishing a candidate. A generation-checked PostgreSQL transaction owns archive/pointer/audit writes; flush the old active role before the immediate partial unique index. Readers pin a version/object and never resolve mutable MLflow aliases during prediction. Never compare unrelated stored CV scores. For training-recipe selection, re-score retained models fitted separately at each shared historical origin; bind those fold artifacts to the final refit and its exact recipe. Final refits can include development labels and must never predict backward. Exact serving-weight evaluation separately requires origins after both fit cutoffs. Both paths protect locked final targets and record which evaluation basis was used. Missing evidence requires an explicit reason, and approval cannot bypass artifact/schema checks or a measured losing candidate. Preserve failed publication audit/files and document cross-store failure boundaries. Testing-only SQLite tracking requires explicit isolated opt-in; production always uses a distinct PostgreSQL database.

## Forecast serving and persistence

Resolve a model version once per request and keep its object/identity throughout. Forecast routes must never call fit, training or automatic registration. Reuse the evaluation adjustment helper and shared feature builder; physically filter SQL observations by business and knowledge cutoff before constructing features. Project Customers out. Bind serving to the model's dataset/availability context, expose old source dates, preserve unknown future flags, and validate scenario provenance and temporal eligibility. Do not infer plans from retrospective outcomes.

Round store-day Sales once with explicit decimal precision; sum those saved values for every total/CSV. Validate the complete result before one metadata/points transaction; a failed insert must leave no partial report. Retrieval must work from stored values without model or MLflow availability. Freeze request, per-store history coverage, schema/model/dataset identities, input fingerprint, policy and UTC generation metadata. Test active switches during prediction, no-fit reuse, future mutation, transaction rollback and exact totals against real isolated PostgreSQL schemas. Column-altering migrations must explicitly target the configured test schema, because schema translation alone does not qualify every Alembic DDL operation.

Prettier honors checkout line endings (`endOfLine: auto`) so existing Windows CRLF files pass the same content/style rules without unrelated whole-tree rewrites. Git still normalizes committed text to LF through .gitattributes. New Python/generated contract files use explicit UTF-8/LF.
