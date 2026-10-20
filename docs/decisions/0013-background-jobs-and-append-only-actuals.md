# 0013 - Durable local jobs, append-only actuals and fixed-calendar retraining

Date: 2026-10-20. Status: implemented in Phase 11.

## Decision

HTTP persists queued requests only. One separately started local worker owns recurrence, short PostgreSQL queue transactions and child process execution. Use file plus database session locks, a one-running partial unique index, attempt tokens/PID creation-time verification, heartbeat visibility and bounded retries. Restart recovery kills only verified owned orphans before fencing attempts. Reuse completed fitting/publication per job instead of creating another model on retry. Cancel queued requests only.

Validate new observed actuals through an operator CLI and publish immutable append-only SQL children with file checksums/provenance. Never fill Kaggle test Sales from placeholders. Fresh forecasts may follow a certified child without changing model weights/preprocessing. Retraining requires labels beyond both prior fitting date and consumed source watermark; existing withheld labels do not count as new data. A previously successful source is skipped on repeated checks.

Later fits inherit original development/final calendars. Remove every protected final-window observation from refit targets and feature histories while allowing legitimate later labels. The manifest records this policy/removal count. Retained per-origin models permit fair re-scoring on unchanged prefix rows, with each model's own saved encoding context only after SQL lineage proof. Require unchanged registry/schema/cohort/knowledge policy. Existing checked activation keeps the incumbent for losing/tied/invalid candidates; no new final scores or incomparable promotion evidence is invented.

## Trade-offs

The worker adds one optional local process and temporary supervised fitting children, avoiding an external broker. A sleeping/off laptop cannot run schedules. Coalesce downtime to one latest due check and audit older slots as skipped; bound catch-up work per tick. Calendar anchors avoid month-end drift, with documented DST behavior. No distributed leases/PID recovery, cloud uptime, automatic daily Kaggle updates, schedule-performance leaderboard or running-job cancellation is claimed.

Immutable child snapshots copy rows in PostgreSQL with INSERT SELECT and materialize request-owned normalized files using bounded batches. This spends local disk space to keep provenance/replay simple. Empty remaining plans/templates are legitimate after all competition target days become observed; the SQL-export contract permits only those explicit empty-plan diagnostics, never empty actual history or invalid rows. Original four-file competition import remains strict. SQL export manifests retain their exact file hashes and a checked binding to business source/job IDs.

Excluding a protected interval creates a fit-time missing-history gap. Fixed historical validation gives a controlled comparison but does not measure new-period accuracy. Different retraining schedules require a matched chronological replay before any performance claim. Unrelated datasets, new stores/metadata revisions and arbitrary lineage merges remain outside this append-only scope.

## Verification

Real PostgreSQL tests cover queue races, unchanged watermarks, immutable import/rollback, schedule restart/DST/month ends, no HTTP fitting, retries/fencing and incumbent continuity. Genuine native subprocess tests cover bootstrap and later refitting with protected-history exclusion and shared-window comparison. Browser/component tests cover honest no-model/queued/active states. PHASE_11_REPORT.md records actual final commands/results.
