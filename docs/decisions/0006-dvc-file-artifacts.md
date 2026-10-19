# 0006 — DVC file artifacts and deterministic Parquet

## In plain English
Files and database rows need different versioning tools. DVC tracks dataset bytes while PostgreSQL keeps transactional history. Checked inputs/settings should reproduce the same files. A synthetic example avoids requiring Kaggle access. The remote is private local storage outside Git.

Date: 2026-10-19. Status: Phase 5 implementation; verification is recorded in the phase report.

## Decision
Use one configs/data.yaml and DVC foreach profiles for validation, typed Parquet normalization and final manifest publication. Generate synthetic CSVs only from labeled hand-authored JSON. Never commit real CSV/Parquet. Reuse SQL ingestion's source contracts without changing PostgreSQL. Fixed validation dates, exact schemas and bounded batches avoid timestamp dependence, inference and full-dataframe memory.

Manifests include raw SHA-256, effective config, actual code, lock, writer version, table hashes/counts and last historical label date; exclude private absolute paths/timestamps. Validation context and normalization receipts prevent new provenance being attributed to old equal-row-count files. Future UI/API consumers verify these contracts. No features/models/new endpoints are implemented.

Use DVC's copy-based cache and an outside-repository local filesystem remote, configured privately in ignored config.local. Git stores code and DVC pointers, PostgreSQL owns transactions, and future MLflow owns experiment/run/model references. DVC hashes and SQL UUIDs are not interchangeable.

## Trade-offs
Raw byte identity is stricter than semantic row equality. New processing settings can change artifacts without new SQL imports. Local byte-identical reruns are verified; all-platform equivalence is not assumed. Validation retains uniqueness sets; conversion batches are capped. Files publish individually and the manifest comes last; failed processing may leave intermediate/stale files that verification rejects. Local cache/remote consume disk and are not off-machine backup. DVC executes synchronous commands; no orchestrator services are introduced.
