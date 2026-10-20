# Phase 10 implementation and verification report

Date: 2026-10-20. Status: complete; stop before forecast UI, training jobs or scheduling. Earlier uncommitted Phase 8/9 work is preserved. No Git commit or push was made.

## Delivered

All requested `/api/v1` routes exist: health, dataset status, searchable/paged stores, active model, version list, create/get forecasts, CSV download and feature registry. OpenAPI is generated from typed Pydantic contracts and checked against docs/openapi.json. Domain/storage errors are explicit and sanitized; input validation keeps FastAPI's native 422 contract. API_CONTRACT.md includes runnable PowerShell/bash examples, full response link and a real historical-cutoff rejection.

Prediction pins one verified saved native model/preprocessing and model generation. Serving uses its exact imported dataset and the shared as-of builder, excludes Customers and physically filters unavailable/post-cutoff Sales. A model fitted after cutoff, unsupported store, absent actual history, corrupt/schema-incompatible bundle or unknowable future scenario fails honestly. Future opening/promotion/holiday values remain unknown without a supported knowledge policy or explicit eligible scenario. No inference path calls training, fitting or registration.

Save the complete validated response context and daily values in one transaction. A failed point insert rolls back the whole run. All daily/store/week/month totals and CSV values sum the same four-decimal rounded store-day forecasts. Partial calendar periods disclose coverage. Retrieval works without model files or MLflow and retains the original version after an active-model switch. Evaluated nonnegative/known-closure adjustments use one shared helper and disclose flags.

## Actual HTTP smoke

A temporary Uvicorn server on loopback port 8001 used the existing active LightGBM version `c0e51310-98a8-4c34-afd9-ca658fbcd468`, generation 2, trained through June 13, 2015. The server was stopped after verification; the documented normal API command uses port 8000. No extra service is required for prediction beyond the API and PostgreSQL.

Every request used cutoff July 31, 2015. GET replay matched POST exactly; downloads had the exact row count and summed to JSON totals.

| Horizons | Stores | Saved points | Measured predicted Sales total |
|---|---|---|---|
| 1 | 1 | 1 | 4565.9409 |
| 7 | 1,2,3 | 21 | 94868.1935 |
| 48 | 1,2,3 | 144 | 641241.6613 |

These are genuine model estimates in unspecified source Sales units, not accuracy scores. A repeated one-day request reproduced the same daily values/input fingerprint. The example store-1 estimate for August 1 is `4565.9409`; the full HTTP response is FORECAST_RESPONSE_EXAMPLE.json. A request with cutoff October 20, 2026 returned 422 `cutoff_beyond_observed_data`, instructing the caller to use a cutoff no later than 2015-07-31.

The store catalog contains 1,115 source stores; the current model covers only 1,2,3. Real source actuals remained 1,017,209 rows. Four smoke forecasts saved 167 point rows. Model versions remained 3, activation events 6 and training jobs 0; the active pointer/generation did not change. Final-holdout release files remained 0. Later serving cutoffs can use then-observed historical dates as features, but no holdout labels were scored, tuned against or fitted during this phase.

Private full smoke evidence and the temporary script/log remain ignored under artifacts/phase10/. They are not required for public onboarding; integration fixtures are synthetic only.

## Commands and results

Commands ran from the repository root using the locked .venv Python. `uv run --locked` equivalents use the same environment.

| Command | Observed result |
|---|---|
| `.venv/Scripts/python.exe -m pytest tests/test_forecast_api.py tests/test_health.py -q --tb=short -x` | Initial focused 33 passed in 111.53 seconds; additional edge tests were subsequently included in the full run |
| `.venv/Scripts/python.exe -m pytest -q --tb=short` | 164 cases: 162 passed, 2 failed in 249.73 seconds; both failures were the existing expected `non-finite` wording after policy extraction |
| `.venv/Scripts/python.exe -m pytest tests/test_backtesting.py -q --tb=short` | Preserved the established error wording; all 23 passed in 0.17 seconds |
| `.venv/Scripts/python.exe -m pytest --lf -q --tb=short` | Both previously failing cases passed in 0.11 seconds; all 164 cases therefore verified across full/targeted runs, no skips |
| `.venv/Scripts/python.exe -m pytest tests/test_forecast_api.py::test_openapi_contract_is_current -q` | 1 passed, including the strengthened decimal-string schema assertion |
| `.venv/Scripts/python.exe -m ruff check .` | All checks passed |
| `.venv/Scripts/python.exe -m ruff format --check .` | 122 files already formatted |
| `.venv/Scripts/python.exe -m mypy` | Success, 80 source files |
| `.venv/Scripts/python.exe -m alembic upgrade head` / `current` / `check` | Head a10f0c03b002; no new upgrade operations detected |
| `uv lock --check` | 148 packages resolved; lock unchanged |
| `.venv/Scripts/python.exe -m dvc status` | Data and pipelines up to date |
| `.venv/Scripts/python.exe -m retailforecast.features.registry --check` | Generated registry current |
| `node node_modules/prettier/bin/prettier.cjs --check .` | All matched files use Prettier style |
| `npm.cmd run lint --workspace apps/web` | ESLint passed |
| `npm.cmd run typecheck --workspace apps/web` | Next type generation and strict TypeScript passed |
| `npm.cmd run test --workspace apps/web` | 1 file, 5 tests passed in 70.08 seconds |
| `.venv/Scripts/python.exe artifacts/phase10/smoke.py` | Actual HTTP 1/7/48-day prediction, saved replay, CSV, deterministic repeat and historical-cutoff failure passed |
| `git diff --check` / `git check-ignore ...` | Whitespace passed; .env, .venv, raw/processed data and model/smoke artifacts remain ignored |

One existing upstream MLflow/SQLAlchemy `noload` deprecation warning remains visible. The full suite was not redundantly repeated after the diagnostic-wording correction; the complete affected 23-test evaluation suite and the two recorded failures were rerun. No tests were skipped or replaced.

The first isolated-schema test attempt exposed unqualified Alembic column alterations. The new frozen migration now explicitly uses the configured schema for upgrade and downgrade. Disposable-schema roundtrip tests pass, and the public business schema matches ORM metadata. Windows checkout CRLF caused existing Prettier failures; `endOfLine: auto` resolves those without rewriting unrelated frontend files, while .gitattributes retains LF for committed text.

Frontend production build/browser E2E and remote CI were not repeated because no frontend source/proxy or browser flow changed. Existing component/lint/type checks and a real HTTP server were exercised. No new Mermaid diagram was needed; existing direct-prediction diagrams retain their flow, with updated implementation narratives.

## Exact Phase 10 file set

Earlier Phase 8/9 files also appear in Git status and are not attributable to this phase. The following files were added or changed for Phase 10:

| Files | Purpose |
|---|---|
| `src/retailforecast/forecasting/contracts.py` | Strict request, scenario, result, provenance, error and exact-total schemas |
| `src/retailforecast/forecasting/catalog.py` | Typed dataset/store metadata discovery and bounded SQL pagination |
| `src/retailforecast/forecasting/errors.py` | Stable domain errors |
| `src/retailforecast/forecasting/policy.py` | Shared evaluated nonnegative and known-closure adjustments |
| `src/retailforecast/forecasting/snapshot.py` | Cutoff/availability-filtered SQL projection and shared feature inputs/provenance |
| `src/retailforecast/forecasting/service.py` | Pinned saved-model inference, complete-result validation, atomic persistence and replay |
| `src/retailforecast/forecasting/totals.py` | Exact totals and metadata-rich CSV |
| `src/retailforecast/forecasting/__init__.py` | Current package purpose |
| `src/retailforecast/evaluation/runner.py` | Reuse the shared existing output policy without score changes |
| `src/retailforecast/storage/models.py` | Forecast run context and per-point adjustment disclosure columns |
| `infra/migrations/versions/a10f0c03b002_forecast_provenance.py` | Frozen schema-qualified column upgrade/downgrade |
| `services/api/forecasts.py` | All new thin phase-10 routes and lazy bounded service dependency |
| `services/api/main.py` | Router inclusion and sanitized domain/storage handlers |
| `services/api/models.py` | `/models/versions` alias before dynamic version lookup |
| `tests/test_forecast_api.py` | Saved-model, SQL, HTTP, temporal, output, migration, corruption, transaction and switch coverage |
| `tests/test_health.py` | Require validated input on the now-implemented forecast route |
| `.prettierrc.json` | Honor Windows checkout line endings without broad frontend rewrites |
| `docs/openapi.json` | Exact generated and tested API schema snapshot |
| `docs/FORECAST_RESPONSE_EXAMPLE.json` | Complete actual one-day example response; no actual source sales rows or secrets |
| `docs/API_CONTRACT.md` | Beginner/engineer request, result, failure, CSV, cutoff and limitation guide |
| `docs/decisions/0012-saved-model-forecast-api.md` | Pinning, precision, snapshot, integrity and local-process decisions |
| `README.md` | Current status and exact API onboarding/example |
| `docs/ARCHITECTURE.md` | Implemented serving/persistence boundary |
| `docs/DATA_FLOW.md` | Actual online prediction and replay flow |
| `docs/DATA_DICTIONARY.md` | Context and daily point persistence fields |
| `docs/MODEL_LIFECYCLE.md` | Implemented forecast pinning, version alias and deferred-scope correction |
| `docs/CODING_STANDARDS.md` | Serving contracts, temporal projection, atomic outputs and cross-platform formatting |
| `docs/ROADMAP.md` | Completed Phase 10 acceptance checklist |
| `docs/IMPLEMENTATION_LOG.md` | Changes, decisions, checks and stop point |
| `docs/PHASE_10_REPORT.md` | This exact implementation/verification record |

## Review and limits

Readability review covered meaningful names, strict typed public boundaries, concise public docstrings, named limits, focused storage/feature/policy/HTTP responsibilities, explicit decimal behavior and comments explaining why cutoff projection, full plan replacement, model pinning and atomic persistence exist. Future mutation/erasure, cross-store isolation, SQL/Parquet parity, schema/unknown-category handling and no-training tests pass.

One local API process admits one forecast at a time, up to 32 selected stores and 48 days. Native bundles are verified/reloaded per POST instead of cached; this favors integrity over minimum latency. Database imports are immutable snapshots; new datasets do not auto-adopt an old model's context. The current cohort is three stores, source labels end in 2015, future plans remain user assertions and predictions are not causal evidence or guaranteed revenue. Raw competition files, Parquet, native models, caches and credentials remain ignored. No new dependency, advanced training, holdout scoring, UI, distributed queue, GPU requirement or scheduler was introduced. Phase 10 is complete.
