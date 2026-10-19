# Local infrastructure

Only PostgreSQL runs in Docker Compose; API/web/ingestion stay on the host. The image is digest-pinned with a durable named volume and a loopback port. MLflow database creation is deferred until its integration phase.

See [INGESTION.md](../docs/INGESTION.md) for private local configuration, start/stop, migrations, validation/import, tests and backup limitations. Do not remove the data volume or downgrade the real imported database casually.
