"""Resource-bounded rolling-origin CLI with a frozen final-holdout release."""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

import yaml

from retailforecast.data.file_pipeline import verify_manifest
from retailforecast.data.pipeline_config import DEFAULT_CONFIG, canonical_json
from retailforecast.data.validation import file_checksum
from retailforecast.evaluation.artifacts import (
    ROOT,
    build_protocol,
    claim_final,
    complete_final,
    load_selection,
    reserve_holdout,
    verify_final_cache,
    write_results,
)
from retailforecast.evaluation.contracts import BacktestConfig, ForecasterFactory
from retailforecast.evaluation.metrics import choose_method, summarize
from retailforecast.evaluation.runner import generate_predictions, score_predictions
from retailforecast.evaluation.snapshot import historical_span, load_outcomes
from retailforecast.evaluation.splits import make_plan
from retailforecast.features.snapshot import load_feature_builder
from retailforecast.forecasting.baselines import BASELINE_NAMES, BaselineFactory


def output_path(relative: str) -> Path:
    """Keep result files in a non-root ignored evaluation directory, including symlinks."""
    path = Path(relative)
    allowed = (ROOT / "artifacts" / "evaluation").resolve()
    resolved = (ROOT / path).resolve()
    if path.is_absolute() or not resolved.is_relative_to(allowed) or resolved == allowed:
        raise ValueError("Output must be a relative subdirectory of artifacts/evaluation")
    if resolved.is_relative_to(allowed / "holdout_locks"):
        raise ValueError("Output cannot replace the holdout workflow ledger")
    return resolved


def run(args: argparse.Namespace) -> None:
    """Verify, forecast, join truth, summarize and publish one reproducible stage."""
    config = BacktestConfig.model_validate(yaml.safe_load(args.config.read_text(encoding="utf-8")))
    if args.stores is not None:
        config = BacktestConfig.model_validate({**config.model_dump(), "store_ids": args.stores})
    builder = load_feature_builder(
        args.data_config, args.profile, store_ids=config.store_ids, assumptions=config.assumptions
    )
    if builder.context is None:
        raise ValueError("CLI requires a verified dataset/availability context")
    start, end = historical_span(args.data_config, args.profile)
    plan = make_plan(start, end, config)
    protocol = build_protocol(config, plan, builder.context)
    if args.plan_only:
        print(canonical_json(protocol.model_dump(mode="json")).decode(), end="")
        return
    output = output_path(args.output or f"artifacts/evaluation/{args.stage}")
    ledger = ROOT / "artifacts" / "evaluation" / "holdout_locks"
    factories: list[ForecasterFactory] = [
        BaselineFactory(name, config.seasonal_weeks) for name in BASELINE_NAMES
    ]
    selection = None
    if args.stage == "final":
        if args.selection is None:
            raise ValueError("Final scoring requires --selection from a completed development run")
        selection = load_selection(args.selection, protocol)
        relative = output.relative_to(ROOT).as_posix()
        if claim_final(ledger, selection, relative, output_exists=output.exists()):
            verify_final_cache(ledger, selection, output)
            print(
                "Final result already released: verified cached files; no re-evaluation performed."
            )
            return
        factories = [factory for factory in factories if factory.name == selection.selected_method]
        folds = plan.folds[-1:]
    else:
        if output.exists():
            raise ValueError("Output already exists; choose a new development directory")
        reserve_holdout(ledger, protocol)
        folds = plan.folds[:-1]
    predictions = generate_predictions(builder, folds, config, factories)
    # Only now expose subsequently observed actuals/Open to the scoring path.
    # They were never arguments to fit() or predict().
    outcomes = load_outcomes(args.data_config, args.profile, config.store_ids, config.assumptions)
    scored = score_predictions(
        predictions,
        outcomes,
        scoring_as_of=end + timedelta(days=config.assumptions.sales_delay_days),
    )
    summaries = summarize(scored)
    chosen = (
        choose_method(summaries)
        if args.stage == "development"
        else selection.selected_method
        if selection
        else None
    )
    current = verify_manifest(args.data_config, args.profile)
    if current.dataset_fingerprint != protocol.snapshot.dataset_fingerprint:
        raise ValueError("Dataset changed during evaluation; results not published")
    report = write_results(
        output,
        protocol,
        args.stage,
        tuple(factory.name for factory in factories),
        scored,
        summaries,
        chosen,
    )
    if selection is not None:
        complete_final(
            ledger,
            selection,
            output.relative_to(ROOT).as_posix(),
            file_checksum(output / "results.json"),
        )
    print(
        f"Stage: {args.stage}; points: {len(scored)}; selected method: {chosen or 'none eligible'}"
    )
    for item in report.summaries:
        if item.axis == "aggregate":
            print(f"{item.method}: {item.metrics.model_dump_json()}")
    print(f"Saved: {output.relative_to(ROOT).as_posix()}/results.json")


def main() -> None:
    """Run development by default; final holdout requires its frozen selection record."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "backtest.yaml")
    parser.add_argument("--data-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--profile", choices=("synthetic", "rossmann"), default="rossmann")
    parser.add_argument("--stage", choices=("development", "final"), default="development")
    parser.add_argument("--stores", type=int, nargs="+")
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--output")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"Backtest failed: {exc}\n")


if __name__ == "__main__":
    main()
