# Configuration

`data.yaml` is the single shared configuration for synthetic and Rossmann validation, normalized Parquet processing, and dataset manifests. See [DATA_VERSIONING.md](../docs/DATA_VERSIONING.md) for commands and field semantics.

Runtime secrets belong in ignored `.env` files. The laptop DVC remote path belongs only in ignored `.dvc/config.local`. Model and training settings remain future work.

`backtest.yaml` configures the separate evaluation protocol: explicit stores, horizon length, development fold count, historical seasonal window, seed, closure policy and knowledge-time assumptions. It does not change the data normalization configuration. See [MODEL_STRATEGY.md](../docs/MODEL_STRATEGY.md). Advanced model settings remain future work.

`training.yaml` now owns internal CPU/RAM/time limits, deterministic trial candidates and dev/full origin/row policies. The current store cohort/chronological fold policy comes from `backtest.yaml`; full mode expands history/cadence/trials within that explicit cohort. Normal product input is algorithm and mode, never raw tree parameters. See [TRAINING.md](../docs/TRAINING.md).

`jobs.yaml` controls the standalone worker mode, bounded attempts/retry/poll/heartbeat/expiry and catch-up batch size. Recurring user intent is transactional PostgreSQL state, manual/disabled by default; saving it never starts a process. Training resource/search controls remain exclusively in training.yaml.
