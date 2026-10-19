"""End-to-end synthetic CLI stages with real Parquet files and no Kaggle or database."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import yaml
from test_backtest_artifacts import protocol
from test_backtesting import config
from test_file_pipeline import fixture_project

from retailforecast.data.file_pipeline import run_pipeline
from retailforecast.evaluation import backtest
from retailforecast.evaluation.artifacts import EvaluationProtocol, verify_results
from retailforecast.evaluation.contracts import BacktestConfig, BacktestPlan
from retailforecast.features.contracts import SnapshotContext


def extended_fixture(root: Path) -> Path:
    """Create explicit synthetic store-days sufficient for a small rolling-origin test."""
    data_config = fixture_project(root)
    path = root / "data/raw/synthetic/train.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        columns = csv.DictReader(handle).fieldnames
    assert columns is not None
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for offset in range(20):
            day = date(2015, 7, 12) + timedelta(days=offset)
            for store in (9001, 9002):
                is_open = int(day.isoweekday() != 7)
                writer.writerow(
                    {
                        "Store": store,
                        "Date": day.isoformat(),
                        "DayOfWeek": day.isoweekday(),
                        "Sales": (100 + offset + store % 10) if is_open else 0,
                        "Customers": 5 if is_open else 0,
                        "Open": is_open,
                        "Promo": 0,
                        "StateHoliday": "0",
                        "SchoolHoliday": 0,
                    }
                )
    run_pipeline(data_config, "synthetic")
    return data_config


def test_cli_development_final_and_idempotent_final_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise split/fit/predict/score/persistence with isolated test provenance."""
    data_config = extended_fixture(tmp_path)
    settings = config(2, (9001, 9002))
    config_path = tmp_path / "configs/backtest.yaml"
    config_path.write_text(yaml.safe_dump(settings.model_dump(mode="json")))
    monkeypatch.setattr(backtest, "ROOT", tmp_path)

    def synthetic_provenance(
        current: BacktestConfig, plan: BacktestPlan, context: SnapshotContext
    ) -> EvaluationProtocol:
        return protocol(current).model_copy(update={"plan": plan, "snapshot": context})

    monkeypatch.setattr(backtest, "build_protocol", synthetic_provenance)
    args = argparse.Namespace(
        config=config_path,
        data_config=data_config,
        profile="synthetic",
        stage="development",
        stores=None,
        selection=None,
        output="artifacts/evaluation/development",
        plan_only=False,
    )
    backtest.run(args)
    development = tmp_path / args.output
    report = verify_results(development)
    assert report.selected_method is not None
    assert all(item.metrics.scored == item.metrics.requested for item in report.summaries)
    assert all(
        row["target_date"] <= report.protocol.plan.folds[-1].cutoff_date
        for row in pq.read_table(development / "predictions.parquet").to_pylist()
    )
    args.stage = "final"
    args.selection = development / "selection.json"
    args.output = "artifacts/evaluation/final"
    changed = settings.model_copy(update={"seasonal_weeks": 3})
    config_path.write_text(yaml.safe_dump(changed.model_dump(mode="json")))
    with pytest.raises(ValueError, match="differs"):
        backtest.run(args)
    assert not list((tmp_path / "artifacts/evaluation/holdout_locks").glob("release-*.json"))
    config_path.write_text(yaml.safe_dump(settings.model_dump(mode="json")))
    backtest.run(args)
    final = tmp_path / args.output
    before = (final / "results.json").read_bytes()
    assert verify_results(final).methods == (report.selected_method,)

    def forbidden(*unused_args: object, **unused_kwargs: object) -> None:
        raise AssertionError(
            "A final cache hit must not generate predictions or read scoring outcomes"
        )

    monkeypatch.setattr(backtest, "generate_predictions", forbidden)
    monkeypatch.setattr(backtest, "load_outcomes", forbidden)
    backtest.run(args)
    assert (final / "results.json").read_bytes() == before


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "artifacts/evaluation",
        "artifacts/evaluation/holdout_locks/overwrite",
        "data/processed/run",
    ],
)
def test_cli_rejects_output_outside_owned_run_directory(path: str) -> None:
    """Results cannot overwrite datasets, the ledger or arbitrary private locations."""
    with pytest.raises(ValueError):
        backtest.output_path(path)
