"""Local CLI for candidate registration, evaluation inspection, activation and rollback."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from retailforecast.lifecycle.registry import ModelRegistry
from retailforecast.storage.database import ROOT, database_engine


def main() -> None:
    """Run explicit lifecycle actions; normal users never supply training hyperparameters."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "register",
            "attach-validation",
            "list",
            "inspect",
            "slot",
            "activate",
            "rollback",
        ),
    )
    parser.add_argument(
        "value", nargs="?", help="Training directory for register; model UUID otherwise"
    )
    parser.add_argument(
        "--training-directory",
        type=Path,
        help="Original completed run for legacy validation recovery",
    )
    parser.add_argument("--expected-generation", type=int)
    parser.add_argument(
        "--approval-reason", help="Explicit approval of missing evidence; required for rollback"
    )
    parser.add_argument("--data-config", type=Path, default=ROOT / "configs/data.yaml")
    parser.add_argument("--profile", choices=("rossmann", "synthetic"), default="rossmann")
    args = parser.parse_args()
    registry = ModelRegistry(
        database_engine(), ROOT / "artifacts/registry", ROOT / "artifacts/mlflow"
    )
    if args.action == "list":
        result: object = [version.model_dump(mode="json") for version in registry.list_versions()]
    elif args.action == "slot":
        result = registry.slot().model_dump(mode="json")
    elif args.action == "register" and args.value:
        result = {"model_version_id": registry.register(Path(args.value))}
    elif args.action == "attach-validation" and args.value and args.training_directory:
        registry.attach_validation(args.value, args.training_directory)
        result = {"model_version_id": args.value, "validation_attached": True}
    elif args.action == "inspect" and args.value:
        versions = [item for item in registry.list_versions() if item.id == args.value]
        if not versions:
            parser.error("Unknown model version")
        registry.load(args.value)
        result = versions[0].model_dump(mode="json")
    elif (
        args.action in ("activate", "rollback")
        and args.value
        and args.expected_generation is not None
    ):
        result = registry.activate(
            args.value,
            expected_generation=args.expected_generation,
            approval_reason=args.approval_reason,
            rollback=args.action == "rollback",
            data_config=args.data_config,
            profile=args.profile,
        ).model_dump(mode="json")
    else:
        parser.error(
            "Provide a training directory/model UUID and --expected-generation for transitions"
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
