# RetailForecast AI engineering instructions

## Before changing code

Read `docs/PRODUCT_SPEC.md`, `docs/CODING_STANDARDS.md`, `docs/ARCHITECTURE.md` when it exists, and relevant records in `docs/decisions/`. Enforce the coding standards before every code change; update them when conventions change. Architecture is documented in docs/ARCHITECTURE.md; follow it and the relevant decision records. Design does not authorize scaffolding beyond the current phase.

## Permanent rules

1. Implement only the user's current phase. Do not advance automatically, scaffold applications, install dependencies, or train models without phase authorization.
2. Use Python modules, not notebooks, for application, data, evaluation, and training work. The existing `colab_test.ipynb` is a legacy environment experiment; do not extend it or silently remove it.
3. Keep UI, API, ML, data access, scheduler, and artifact management separated. Avoid duplicating business logic.
4. Prevent forecasting leakage. Define the information cutoff explicitly and test information availability, temporal joins, lags, rolling windows, and forecast evaluation. Future actual Sales and Customers must never enter predictors.
5. Use real calculations and data. Never fabricate predictions, hardcode performance metrics, or present mock charts as model results.
6. Never expose credentials or commit raw datasets, trained models, generated artifacts, local environments, or secret files. Keep ignore rules current.
7. Use deterministic seeds, UTC event timestamps, pinned dependencies, and reproducibility metadata: dataset version/hash, source revision, feature configuration, cutoff, seed, environment, and model version. Preserve source business dates as dates.
8. Add or update meaningful tests and documentation for every behavior change. Use small, hand-checkable temporal examples; do not bypass checks or suppress failures to claim completion.
9. Use meaningful consistent names, explicit Python/TypeScript types, small single-purpose functions, separated modules, and clear input/output contracts. Document public APIs and non-obvious algorithms concisely.
10. Explain why non-obvious choices exist, especially cutoffs, joins, lag windows, leakage prevention, evaluation, training state transitions, and business assumptions. Refactor confusing code; avoid comments that repeat obvious statements. Put configurable thresholds in named settings.
11. Do not silently delete unrelated code. Do not commit or push unless explicitly requested.
12. Favor plain-language explanations understandable to a retailer and a future engineer. Record important decisions and trade-offs.
13. Maintain a brief journal in `docs/IMPLEMENTATION_LOG.md` and a phase checklist in `docs/ROADMAP.md`.

## Phase completion checklist

Stop at the end of the authorized phase and report:

- [ ] Exact changed files and behavior delivered.
- [ ] Commands, relevant output, tests/checks run, and any checks not run.
- [ ] Documentation updated and acceptance criteria checked.
- [ ] Code readability, types, docstrings, and explanatory comments reviewed; mark not applicable for documentation-only work.
- [ ] Information-cutoff/leakage checks reviewed where applicable.
- [ ] Risks, limitations, outstanding decisions, and explicit phase completion status.

Do not automatically proceed to the next phase.
