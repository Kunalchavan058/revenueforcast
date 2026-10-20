# 0010 — Separate tracking metadata and transactional serving authority



Date: 2026-10-20. Status: implemented Phase 9; supersedes decision 0009's temporary SQLite production backend. The original post-refit-only comparison policy below is superseded by decision 0011; retained historical fold models now supply normal promotion evidence.



## Decision



Use the existing local PostgreSQL container with a distinct MLflow database/login and filesystem artifacts. Keep application model UUIDs/approval roles separate from MLflow run IDs and registry version numbers. PostgreSQL global-v1 slot, monotonic generation, partial unique active index and same-transaction audit control serving; no MLflow alias is a serving authority. Preserve existing SQLite experiments and adopt successful bundles through new linked PostgreSQL tracking runs.



Verify sealed native/preprocessing/provenance hashes before publication and use. Compare saved candidate/incumbent weights on shared eligible development windows using the existing feature/evaluation runner. Do not refit a substitute incumbent or compare unrelated stored CV scores. Require two complete shared folds and strict lower mean RMSPE; ties retain the incumbent. Insufficient evidence requires explicit approval, never automatic promotion. Rollback checks retained immutable bytes and records a reason.



## Trade-offs



No extra tracking server/process is needed. SQL row locks serialize transitions, while ordinary pointer readers retain the committed version. Local native prediction requests pin an immutable object/model ID through switches. Cross-store publication is intentionally not atomic: orphan non-serving files/MLflow records may require manual inspection. No destructive automatic cleanup or alias synchronization is claimed.



Current final weights leave no unused post-training development windows in the Rossmann snapshot. A later candidate remains pending rather than misusing the locked final holdout. Replacement currently requires identical data context/schema/cohort; corrected/new snapshots require a later explicit compatibility policy. Adoption preserves original files and lineage but does not migrate all historical experiments. The public API exposes checked transitions/inspection; browser forecasting and durable scheduling remain deferred.
