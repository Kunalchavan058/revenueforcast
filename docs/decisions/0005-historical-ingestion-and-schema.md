# 0005 — Historical ingestion and minimal business schema

## In plain English
A source snapshot must be complete and traceable before it appears in the database. Train actuals and unlabeled competition inputs have separate tables. Missing values and unusual labels are preserved rather than corrected silently. Duplicate imports reuse the original snapshot. Only PostgreSQL runs in Docker.

Date: 2026-10-19. Status: Phase 4 implementation; verified results recorded in implementation log.

## Decisions
Use SQLAlchemy 2-style typed models, explicit frozen Alembic migrations, psycopg, typed Pydantic contracts and bounded validation/inserts. Preserve source bytes locally and record per-file/compound SHA-256, availability assumptions, counts, date spans, missingness, duplicates and closure diagnostics. Validate the complete four-file Rossmann bundle; sample submission is checked for matching Id coverage but is never a label table.

Version stores by (source_version, store_id) and actuals/inputs by (source_version, store_id, date). Full snapshots are independent, not destructive updates. Separate forecast_inputs physically excludes Sales/Customers. Normalize forecast point provenance through its run. Enforce active model uniqueness with a partial scope index. Serving-slot CAS/audit and training execution stay future work; entity definitions do not implement ML.

Publish all business rows and success audit in one transaction. A separate durable import attempt allows failure reporting after rollback. Serialize equal snapshots with an advisory lock plus unique checksum; bounded batches never commit independently. Preserve valid raw copies before publication and check bytes against validation hashes.

## Storage refinement
Architecture decision 0003 plans a separate MLflow database/user. Defer its creation until MLflow is installed: no current consumer warrants an empty second database. The business database contains only records/metadata; artifact URIs and MLflow IDs are references, not serialized models. Compose uses an immutable PostgreSQL 17 image digest, loopback port, named volume and 512 MiB cap; host processes remain unchanged.

## Trade-offs
Streaming validation still retains uniqueness keys for the million-row source, using memory proportional to key count. Full snapshots duplicate observations across versions but make auditing and rollback understandable. CLI import is synchronous and revalidates on every attempt, favoring safety over fast duplicate checks. Historical availability assumptions are explicit, not inferred facts. Process death can leave a stale audit even though the data transaction rolls back; richer recovery belongs to a later worker phase.

See DATA_DICTIONARY.md for field/entity contracts and INGESTION.md for setup and verification.
