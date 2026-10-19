# 0003 — Storage, registry, and artifact ownership

## In plain English
The database records activity while files contain the learned model. MLflow organizes runs and registered model versions. DVC identifies exact datasets. Distinct ownership helps reproduce forecasts and restore an earlier model. A version label alone cannot recover lost bytes.

Date: 2026-10-19. Status: Accepted design, not implemented.

## Decision
Use one local Docker PostgreSQL instance with separate app and MLflow backend databases/credentials on durable storage. Application tables hold actuals, plans, import versions, jobs, predictions, approval pointers, and audit. Store no fitted model bytes in PostgreSQL.

Use dedicated ignored local directories/volumes for immutable model bundles and original/validated dataset files. Configure MLflow artifacts to use/reference the managed artifact store. MLflow is run/registry authority; the app model_slots pointer is serving authority. DVC identifies immutable dataset snapshots and local objects. Git later tracks only small manifests/configuration, never raw datasets. No paid remote store is required.

## Publication and recovery
Publish verified immutable artifact files, record MLflow run/version, then operational candidate metadata. Approve through a generation-checked database transaction and reconcile aliases/tags eventually. There is no distributed transaction; partial candidates never serve. Preserve old artifacts for rollback. Automated cleanup needs a separate retention design. Back up app and MLflow databases, artifact files, original data, and DVC objects consistently; local volumes/cache are not disaster-recovery backups.

## Alternatives and trade-offs
Using only a registry alias couples serving to registry availability and lacks the app's atomic approval/audit boundary. PostgreSQL model blobs enlarge operational storage and blur responsibilities. Unversioned CSV cannot establish provenance. The selected split adds reconciliation and backup complexity; implementation must test failure recovery before durability is claimed.
