"""Inspect one genuine cutoff-safe feature row; no model training or predictions."""

from __future__ import annotations

import argparse
import json
from datetime import date

from retailforecast.data.pipeline_config import DEFAULT_CONFIG
from retailforecast.features.contracts import ForecastKey, HistoricalAssumptions
from retailforecast.features.registry import registry_fingerprint
from retailforecast.features.snapshot import load_feature_builder


def main() -> None:
    """Print predictors with dataset identity and caller-declared historical assumptions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("synthetic", "rossmann"), default="synthetic")
    parser.add_argument("--store-id", type=int, required=True)
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True)
    parser.add_argument("--horizon", type=int, required=True)
    parser.add_argument("--metadata-known-as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--plans-known-as-of", type=date.fromisoformat)
    parser.add_argument("--sales-delay-days", type=int, default=0)
    parser.add_argument("--assumption", required=True)
    args = parser.parse_args()
    try:
        assumptions = HistoricalAssumptions(
            explanation=args.assumption,
            metadata_known_as_of=args.metadata_known_as_of,
            calendar_known_as_of=args.plans_known_as_of,
            sales_delay_days=args.sales_delay_days,
        )
        key = ForecastKey(
            store_id=args.store_id, cutoff_date=args.cutoff, horizon_days=args.horizon
        )
        builder = load_feature_builder(
            DEFAULT_CONFIG, args.profile, store_ids=[key.store_id], assumptions=assumptions
        )
        row = builder.build(key)
        print(
            json.dumps(
                {
                    "key": key.model_dump(mode="json"),
                    "target_date": key.target_date.isoformat(),
                    "registry_sha256": registry_fingerprint(),
                    "context": row.context.model_dump(mode="json") if row.context else None,
                    "features": dict(row.values),
                },
                indent=2,
            )
        )
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Cannot build features: {exc}\n")


if __name__ == "__main__":
    main()
