# Phase 9 implementation report

Historical snapshot: its pending-candidate limitation was a workflow bug, corrected in [VALIDATION_FIX_REPORT.md](VALIDATION_FIX_REPORT.md). Current behavior is described by MODEL_LIFECYCLE.md and decision 0011. The data are sufficient; original cutoff-fitted validation models are now retained and re-scored. The results below record the earlier implementation, not the corrected live model state.

Date: 2026-10-20. Status: implemented and locally verified; stop before forecast execution/UI or scheduling.

## Delivered

MLflow's normal backend now uses a distinct local PostgreSQL database/login, with experiment/model artifacts on disk. A frozen Alembic migration adds sealed registrations, one global generation-checked serving slot and transactional decision events. The business model row references MLflow run and registered-model version identifiers; neither database stores serialized weights.

Candidates pass successful-run, selected-trial, chronological validation, native reload, checksums, schema, dataset and final-holdout checks. Fixed candidate/incumbent weights are re-evaluated on identical eligible development windows through the existing shared runner. Two complete shared folds and strict lower mean RMSPE permit automatic replacement; ties/failures retain the incumbent. Missing evidence remains pending explicit approval. Approval cannot bypass corruption or a measured losing comparison. Checked rollback restores retained compatible files; pinned loaded predictions remain unchanged during a switch.

CLI and typed API support listing, inspecting evaluation/provenance, activation and rollback. Registration is local CLI-only. The browser remains health-only. See MODEL_LIFECYCLE.md and decision 0010 for commands, contracts and recovery limits.

## Actual local result

| Item | Verified value |
|---|---|
| MLflow database/login | retailforecast_mlflow, distinct from business credentials |
| Active model | XGBoost, application UUID 36399e6f-7088-41e4-a5a5-f44ebbe32f58 |
| Later candidate | LightGBM, UUID 509779bf-2b3d-485d-b14e-03ceae85a248; approval_required=true |
| Global slot generation | 1 |
| Real training cutoff | 2015-06-13 for both models; original trained_at retained |
| Forecast coverage | explicitly trained stores 1,2,3; horizons 1..48 |
| Business data preserved | 1 dataset version, 1,115 stores, 1,017,209 daily actual rows |
| Operational metadata | 2 model versions and 2 decision events |
| Real final holdout | June 14..July 31 remains unscored; no real final-release claims |

The LightGBM candidate is not labeled worse or better based on unrelated historical CV scores. Both final saved models were fitted after the available development origins; the remaining labeled dates are final holdout. No eligible shared post-training development window exists, so the incumbent remains active. No manual approval override was applied to this real candidate. Rollback/approval/rejection are verified in isolated PostgreSQL schemas with genuine synthetic native models.

A real active-model load/pin and finite horizon-48 prediction were verified without joining/scoring final outcomes. Actual PostgreSQL-backed API health/model inspection succeeded through TestClient. Both real MLflow registered versions report READY, and adoption runs contain actual parameters/validation metrics and local model artifacts. Original SQLite runs/files were retained and linked, not erased or falsely relabeled as PostgreSQL runs. Private verification output is in ignored artifacts/phase09-verification/verification.json.

## Executed validation

Commands below ran against the repository virtual environment; `uv run --locked` is the equivalent onboarding form.

| Command/check | Actual result |
|---|---|
| python scripts/configure_mlflow.py, repeated | dedicated local role/database ready; credentials retained privately |
| python -m alembic upgrade head | revision 719de0a9b001 applied |
| python -m alembic check | No new upgrade operations detected |
| python -m pytest -q | **124 passed**, 1 upstream warning, 78.43 seconds; no skips |
| pytest tests/test_model_lifecycle.py tests/test_tracking_postgres.py -q | 13 passed, 1 upstream warning |
| python -m mypy | 69 source files, no issues |
| python -m ruff check src services scripts tests infra/migrations | all checks passed |
| uv lock --check | 148 resolved packages; no new dependency changes in Phase 9 |
| uv run --locked dvc status | Data and pipelines are up to date |
| python -m retailforecast.features.registry --check | generated registry current |
| Real CLI register/activate/list/inspect equivalents and active pin | model links/roles/generation verified |

The visible warning is MLflow's existing SQLAlchemy `noload` deprecation; it is not suppressed. Real PostgreSQL migration downgrade/reapply, competing promotions, corruption/missing files, transactional failure after archive flush, insufficient evidence, measured tie rejection, rollback, pinned prediction stability and HTTP validation/conflict contracts are tested. Offline synthetic MLflow workflow fixtures explicitly opt into disposable SQLite; a separate integration test exercises the default PostgreSQL path and filesystem artifact roundtrip.

Frontend source was not changed, so browser/build checks were not repeated. Existing Python liveness/forecast-not-implemented tests passed. CI onboarding was updated to provision the MLflow database before the full quality checks; GitHub CI itself was not triggered. Mermaid was reviewed statically against the diagram guide, without claiming a rendered preview.

## Exact Phase 9 files

- .env.example; .github/workflows/checks.yml; README.md.
- scripts/configure_mlflow.py.
- infra/migrations/versions/719de0a9b001_model_lifecycle.py.
- src/retailforecast/storage/models.py; src/retailforecast/training/tracking.py.
- src/retailforecast/lifecycle/__init__.py, settings.py, comparison.py, registry.py, manage.py.
- services/api/main.py; services/api/models.py.
- tests/test_model_lifecycle.py; tests/test_tracking_postgres.py; tests/test_training_workflow.py.
- docs/MODEL_LIFECYCLE.md, TRAINING.md, ARCHITECTURE.md, DATA_DICTIONARY.md, CODING_STANDARDS.md, ROADMAP.md, IMPLEMENTATION_LOG.md, PHASE_09_REPORT.md.
- docs/decisions/0010-postgresql-model-lifecycle.md.

Earlier uncommitted Phase 8 implementation/dependency/DVC files were preserved. No commit or push was performed. Models, dataset files, database files, private credentials and local artifact paths belong outside Git.

## Readability, leakage and limitations

Reviewed public types/docstrings, named scope/minimum-fold policy, separated tracking/comparison/storage/API boundaries and the shared evaluator rather than duplicated scoring. Comments explain fixed weights, fit-date/holdout boundaries, outcome joining, pointer pinning, adoption-run lineage and the archive flush required by PostgreSQL's immediate unique index. Customers remain absent from predictors, and future actuals cannot enter saved-model comparison features. Existing temporal mutation/horizon/store-isolation checks passed in the full suite.

Compatibility is deliberately conservative: replacement/rollback requires the same data/availability context, schema and store cohort. Automatic adoption of corrected/new snapshots needs a future explicit policy. Filesystem, MLflow and business SQL have no distributed transaction; interrupted registration can leave non-serving orphan files/records for manual inspection. No automatic deletion, complete historic-run migration, alias reconciler, durable queue, scheduler, forecast API/UI or final-holdout release is claimed. Local disk loss cannot be repaired by a version ID alone; back up both databases and complete artifact/data/DVC files together.

Implementation follows the primary [MLflow backend-store documentation](https://mlflow.org/docs/latest/ml/tracking/backend-stores/) and [MLflow client API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.client.html). Application-native bundles use the application's validated adapter loader rather than claiming an MLflow pyfunc flavor.
