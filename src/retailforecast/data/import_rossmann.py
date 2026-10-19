"""Validate or atomically import local Rossmann CSV files; no ML is performed."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from retailforecast.data.contracts import ImportRequest
from retailforecast.data.ingestion import import_bundle
from retailforecast.storage.database import ROOT, database_engine


def main() -> int:
    """Run validate-first ingestion and write a machine-readable local validation report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--dry-run", "--validate-only", action="store_true")
    parser.add_argument("--min-date", type=date.fromisoformat, default=date(2000, 1, 1))
    parser.add_argument("--max-date", type=date.fromisoformat, default=datetime.now(UTC).date())
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    try:
        request = ImportRequest(
            source_dir=str(arguments.source_dir.resolve()),
            dry_run=arguments.dry_run,
            minimum_date=arguments.min_date,
            maximum_date=arguments.max_date,
        )
        engine = None if request.dry_run else database_engine()
        result = import_bundle(request, engine)
        report_path = arguments.report or (
            ROOT / "data" / "processed" / f"validation-{result.report.checksum}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "state": result.state,
                    "dataset_version_id": result.dataset_version_id,
                    "import_job_id": result.import_job_id,
                    "report_path": str(report_path),
                    "files": {
                        name: item.model_dump(mode="json")
                        for name, item in result.report.files.items()
                    },
                    "issues": [issue.model_dump() for issue in result.report.issues],
                    "issue_count": result.report.issue_count,
                    "warnings": result.report.warnings,
                },
                indent=2,
            )
        )
        return 0 if result.state != "rejected" else 2
    except (OSError, ValueError, SQLAlchemyError, ValidationError) as error:
        print(
            json.dumps(
                {
                    "state": "failed",
                    "error_code": type(error).__name__,
                    "message": "Check source paths, .env DATABASE_URL, "
                    "Docker health and Alembic head. "
                    "No partial dataset was published. Database failure details stay private.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
