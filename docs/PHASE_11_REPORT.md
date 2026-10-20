# Phase 11 implementation and verification report

Date: 2026-10-20. Status: complete and verified; stop after Phase 11. Subsequent user-authorized logical commits are recorded in IMPLEMENTATION_LOG.md; no GitHub push.

## Delivered behavior

The API saves training requests and immediately returns 202. One separately started local scheduler/worker owns fitting, recurrence and restart recovery. Jobs have queued/running/succeeded/failed/skipped/cancelled states, real stages/times, heartbeat visibility, bounded attempt summaries and queued-only cancellation. Idempotency keys, short PostgreSQL locks and unique constraints prevent duplicate requests/publications and concurrent running jobs. A job can succeed while its candidate remains rejected or pending; model approval is a separate decision.

Manual is the disabled schedule default. Weekly, monthly and quarterly use timezone-aware calendar anchors, explicit short-month/DST rules and unique due-occurrence keys. After downtime, older occurrences are audited as skipped and the latest due check is considered. Catch-up and retries are bounded. Saving a schedule does not start the worker or wake a sleeping laptop. There is no browser-owned scheduler, broker, Redis, Celery or cloud service.

The operator additional-actuals CLI validates a strict Rossmann-shaped observed CSV, preserves raw checksums/provenance and publishes an immutable append-only dataset child transactionally. Missing labels, future dates, duplicate pairs, backfills, unknown stores and divergent branches fail explicitly. Re-import is idempotent. Synthetic fixtures are labeled synthetic and are never represented as downloaded Kaggle updates. SQL-export normalization uses bounded batches and permits legitimately empty remaining plan/submission tables without weakening actual-label validation.

Fresh forecasts can use certified descendant observations through the requested cutoff with the existing saved weights/preprocessing. Retraining separately requires later selected-store labeled observations beyond both the previous fitting date and consumed-source watermark. Existing withheld labels do not count as new observations. Unchanged data records `skipped: no new labeled observations` without fitting or publishing a model.

A later fit preserves the original chronological development folds and removes every protected final-window observation from the entire fitting history, including lag/rolling inputs. The manifest records the interval and excluded count. Shared-window promotion re-scores retained origin-specific models and bridges saved contexts only with certified unchanged-prefix SQL lineage, unchanged knowledge assumptions/schema/cohort and identical row values. Serving weights never predict backward. A measured tie/loss retains the incumbent. The original real final holdout remains unscored.

Minimal browser onboarding offers first training only when no active model exists, otherwise candidate training with incumbent continuity. Algorithm selection is the only tuning input. Loading/offline/queued states are honest; polling reads persisted status only. Full forecast charts and schedule settings pages remain outside this phase.

## Live database/API/worker smoke

A temporary current API on loopback 8001 returned real active-model/schedule state, accepted an Auto request and deduplicated its Idempotency-Key. While that request was queued, a genuine saved-LightGBM forecast completed for store 1, cutoff 2015-07-31, horizon 1. The one-shot standalone worker exited successfully and marked the request skipped with zero attempts and no result model. The active pointer remained generation 2, model c0e51310-98a8-4c34-afd9-ca658fbcd468, fitted through 2015-06-13. Observations still end 2015-07-31 and the model supports stores 1,2,3 only.

| Live business state | Before | After |
|---|---|---|
| Daily sales | 1,017,209 | 1,017,209 |
| Dataset versions | 1 | 1 |
| Model versions | 3 | 3 |
| Model decision events | 6 | 6 |
| Training jobs | 0 | 1, skipped |
| Forecast runs | 4 | 5 |
| Final-holdout release receipts | 0 | 0 |

Job c98af72f-dc75-4e98-a79b-0d722dfb44d3 ran its eligibility check on 2026-10-20. The genuine one-day estimate was 4565.9409 source Sales units for 2015-08-01; it is an estimate, not a measured accuracy score. No live new-sales import, model refit or enabled recurring schedule was created. Temporary owned processes were stopped; existing operator services were preserved. Private scripts/logs/summary remain ignored under artifacts/phase11/.

## Commands and observed results

Run from the repository root. `.venv/Scripts/python.exe` is the existing locked environment; `uv run --locked python` is its portable equivalent. Windows frontend checks used the existing portable Node 22.23.3 on PATH.

| Command/check | Observed result |
|---|---|
| `.venv/Scripts/python.exe -m pytest -q --tb=short` | 186 passed, no skips, in 549.59 seconds |
| Four targeted native/lifecycle cases after final ownership/context hardening | 4 passed in 109.61 seconds: real worker bootstrap/unchanged skip, append retrain/protected mask/shared comparison, failed training concurrent with incumbent forecast, measured winner promotion |
| `.venv/Scripts/python.exe -m ruff check .` | All checks passed |
| `.venv/Scripts/python.exe -m ruff format --check .` | 136 files already formatted |
| `.venv/Scripts/python.exe -m mypy` | Success, 91 source files |
| `.venv/Scripts/python.exe -m alembic upgrade head`, `current`, `check` | b110c0d4e003 applied; no new upgrade operations detected |
| `uv lock --check` | 148 packages resolved; no dependency or lock change |
| `.venv/Scripts/python.exe -m dvc status` | Data and pipelines are up to date |
| `.venv/Scripts/python.exe -m retailforecast.features.registry --check` | Generated feature registry current |
| `.venv/Scripts/python.exe artifacts/phase11/smoke.py` | Real current HTTP routes and standalone `--once` worker passed; unchanged data skipped, incumbent forecast succeeded |
| `npm.cmd run lint --workspace apps/web` | ESLint passed, including the final isolated-server configuration |
| `npm.cmd run typecheck --workspace apps/web` | Route generation and strict TypeScript passed |
| `npm.cmd exec -- prettier --check .` | All matched files use Prettier style; docs follow the repository's existing exclusion |
| `npm.cmd run test --workspace apps/web` | 10 passed across 2 files, 41.81 seconds on final component run |
| `npm.cmd run build --workspace apps/web` | Optimized Next.js build and TypeScript passed; isolated API proxy build also passed |
| `npm.cmd run test:e2e --workspace apps/web` | 3 passed in 19.6 seconds against current isolated API 8001/web 13000; real health/model availability, retry and explicitly mocked first-model enqueue UI |
| `.venv/Scripts/python.exe -m pytest tests/test_forecast_api.py::test_openapi_contract_is_current -q --tb=short` | 1 passed in 4.40 seconds on final snapshot check |
| `git diff --check` and publication exclusions | No whitespace errors; changed text contains no local credential values/private absolute paths or dataset/model binaries; no CSV is Git-tracked; documentation links resolve |

The four final targeted cases were run with:

```text
.venv/Scripts/python.exe -m pytest tests/test_training_jobs.py::test_standalone_process_genuinely_trains_bootstraps_and_skips_unchanged tests/test_training_jobs.py::test_append_retraining_masks_holdout_and_compares_shared_windows tests/test_training_jobs.py::test_failed_training_keeps_incumbent_forecasts tests/test_model_lifecycle.py::test_measured_winner_is_promoted_without_override -q --tb=short
```

The full Python run includes the prior phases' database/forecast/temporal tests and 22 job cases. The new coverage exercises request/claim races, actual-data validation/idempotency/rollback/branch rejection, schedule restart/DST/month ends, consumed watermarks, retry exhaustion/fencing, stale heartbeat reporting, idempotent publication, migration round-trip and genuine supervised bootstrap/refitting. All business database tests use real PostgreSQL disposable schemas; native smoke fits use explicitly synthetic data. One existing MLflow/SQLAlchemy `noload` deprecation warning remains visible; no failures were replaced with skips.

The isolated browser screenshot was inspected: API connected and active-model candidate training were visible. The production build was then restored to the normal API proxy on port 8000.

Windows virtualenv Python can launch through a redirector with a different PID. Authorization now verifies PID plus creation time in the live ancestry and acknowledges the actual interpreter before work; real child-process tests pass. Strict frontend test typing and isolated browser ports were corrected before final checks. Final targeted checks followed the last runtime changes; the full native suite was not unnecessarily repeated after documentation-only changes.

## Exact changed files

- `README.md`
- `apps/web/e2e/health.spec.ts`
- `apps/web/playwright.config.ts`
- `apps/web/src/app/page.tsx`
- `apps/web/src/components/api-health.tsx`
- `apps/web/src/components/training-control.tsx`
- `apps/web/src/lib/api/training.ts`
- `apps/web/tests/training-control.test.tsx`
- `configs/README.md`
- `configs/jobs.yaml`
- `docs/API_CONTRACT.md`
- `docs/ARCHITECTURE.md`
- `docs/CODING_STANDARDS.md`
- `docs/DATA_DICTIONARY.md`
- `docs/DIAGRAM_STYLE_GUIDE.md`
- `docs/IMPLEMENTATION_LOG.md`
- `docs/MODEL_LIFECYCLE.md`
- `docs/PHASE_11_REPORT.md`
- `docs/ROADMAP.md`
- `docs/TRAINING_JOBS.md`
- `docs/decisions/0013-background-jobs-and-append-only-actuals.md`
- `docs/openapi.json`
- `infra/migrations/versions/b110c0d4e003_background_training.py`
- `services/api/main.py`
- `services/api/training_jobs.py`
- `src/retailforecast/data/import_actuals.py`
- `src/retailforecast/data/lineage.py`
- `src/retailforecast/forecasting/catalog.py`
- `src/retailforecast/forecasting/contracts.py`
- `src/retailforecast/forecasting/service.py`
- `src/retailforecast/lifecycle/comparison.py`
- `src/retailforecast/lifecycle/job_contracts.py`
- `src/retailforecast/lifecycle/job_execution.py`
- `src/retailforecast/lifecycle/job_snapshot.py`
- `src/retailforecast/lifecycle/job_worker.py`
- `src/retailforecast/lifecycle/jobs.py`
- `src/retailforecast/lifecycle/registry.py`
- `src/retailforecast/lifecycle/scheduling.py`
- `src/retailforecast/storage/models.py`
- `src/retailforecast/training/adapters.py`
- `src/retailforecast/training/contracts.py`
- `src/retailforecast/training/workflow.py`
- `tests/test_training_jobs.py`

## Readability, temporal review and limits

Reviewed typed public schemas/docstrings, focused API/queue/schedule/process/data boundaries, named settings, explicit transactions and comments explaining cutoff masks, immutable prefix certification, calendar rules and attempt ownership. Shared feature construction, preprocessing and scoring remain authoritative. Customers remain historical audit fields and are excluded from V1 predictors. Tests exercise no HTTP fitting, future-mutation invariance, fresh descendant forecasts, protected-history exclusion and incumbent continuity on actual failure.

One optional local worker is required alongside API/web and Docker PostgreSQL; it cannot run while the laptop is off. Recovery is for one laptop, not distributed scheduling. Running-job cancellation is deliberately unavailable. Immutable child snapshots cost local disk/SQL space; each actuals append is capped at 50,000 rows and must extend the latest parent. New stores, corrected metadata, backfills and unrelated-lineage adoption need a later explicit policy.

Masking the original protected final interval creates a fit-time history gap. Fixed historical development evidence supports a controlled recipe comparison but does not measure newly observed-period quality; schedule-performance claims require matched historical replay. Current real source/model coverage remains historical and three-store limited. Existing CPU/RAM/time budgets are reused, but whole-stack peak RAM/throughput and multi-host reliability were not benchmarked. Mermaid sources received static narrative/state review; no Mermaid renderer is installed, so rendered diagram layout was not verified. Remote CI was not run.

Restart the API/web to load the new code, then explicitly start `uv run --locked python -m retailforecast.lifecycle.job_worker` when training/schedules are wanted. Recurrence stays manual/disabled until deliberately configured. Phase 11 stops here; no forecast dashboard, schedule-performance leaderboard, final-holdout release or GitHub push.
