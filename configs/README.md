# Configuration

`data.yaml` is the single shared configuration for synthetic and Rossmann validation, normalized Parquet processing, and dataset manifests. See [DATA_VERSIONING.md](../docs/DATA_VERSIONING.md) for commands and field semantics.

Runtime secrets belong in ignored `.env` files. The laptop DVC remote path belongs only in ignored `.dvc/config.local`. Model and training settings remain future work.

`backtest.yaml` configures the separate evaluation protocol: explicit stores, horizon length, development fold count, historical seasonal window, seed, closure policy and knowledge-time assumptions. It does not change the data normalization configuration. See [MODEL_STRATEGY.md](../docs/MODEL_STRATEGY.md). Advanced model settings remain future work.
