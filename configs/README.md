# Configuration

`data.yaml` is the single shared configuration for synthetic and Rossmann validation, normalized Parquet processing, and dataset manifests. See [DATA_VERSIONING.md](../docs/DATA_VERSIONING.md) for commands and field semantics.

Runtime secrets belong in ignored `.env` files. The laptop DVC remote path belongs only in ignored `.dvc/config.local`. Model and training settings remain future work.
