"""Internal subprocess entrypoint; normal users invoke training.train instead."""

from __future__ import annotations

import argparse
from pathlib import Path

from retailforecast.training.contracts import TrainingRequest

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    """Execute a frozen request only inside the supervised child process."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    request = TrainingRequest.model_validate_json((args.output / "request.json").read_bytes())
    from retailforecast.training.workflow import execute

    execute(request, args.output, root=args.root)


if __name__ == "__main__":
    main()
