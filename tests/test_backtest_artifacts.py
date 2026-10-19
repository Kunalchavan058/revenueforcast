"""Reproducible result files, frozen development evidence and final release guards."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from test_backtesting import config, history

from retailforecast.data.validation import file_checksum
from retailforecast.evaluation.artifacts import (
    EvaluationProtocol,
    EvaluationReport,
    SelectionRecord,
    claim_final,
    complete_final,
    load_selection,
    reserve_holdout,
    verify_final_cache,
    verify_results,
    write_results,
)
from retailforecast.evaluation.contracts import BacktestConfig, outcome_index
from retailforecast.evaluation.metrics import choose_method, summarize
from retailforecast.evaluation.runner import generate_predictions, score_predictions
from retailforecast.evaluation.splits import make_plan
from retailforecast.features.builder import FeatureBuilder
from retailforecast.features.contracts import SnapshotContext
from retailforecast.forecasting.baselines import BaselineFactory


def protocol(settings: BacktestConfig | None = None) -> EvaluationProtocol:
    """Construct synthetic provenance without accessing Git, Kaggle or a database."""
    settings = settings or config(2)
    return EvaluationProtocol(
        config=settings,
        plan=make_plan(date(2015, 1, 1), date(2015, 1, 14), settings),
        snapshot=SnapshotContext(
            dataset_fingerprint="synthetic-test-only", assumptions=settings.assumptions
        ),
        code_revision="synthetic-test-revision",
        working_tree_dirty=False,
        source_hashes={"synthetic-test-module": "test-only"},
        dependency_lock_sha256="test-lock",
        registry_sha256="test-registry",
        python_version="test",
        pyarrow_version="test",
    )


def development_result(output: Path, metadata: EvaluationProtocol) -> EvaluationReport:
    """Build genuine deterministic scores from the hand-authored January history."""
    from retailforecast.evaluation.contracts import Outcome

    builder = FeatureBuilder(history())
    predicted = generate_predictions(
        builder, metadata.plan.folds[:-1], metadata.config, [BaselineFactory("last_known")]
    )
    outcomes = outcome_index(
        Outcome(
            store_id=row.store_id,
            target_date=row.date,
            actual_sales=row.sales,
            available_as_of=row.available_as_of,
        )
        for row in history()
    )
    scored = score_predictions(predicted, outcomes, scoring_as_of=date(2015, 1, 14))
    segments = summarize(scored)
    report: EvaluationReport = write_results(
        output, metadata, "development", ("last_known",), scored, segments, choose_method(segments)
    )
    return report


def test_identical_runs_write_byte_identical_json_and_parquet(tmp_path: Path) -> None:
    """Output location and wall-clock time cannot change reproducible artifacts."""
    metadata = protocol()
    first, second = tmp_path / "first", tmp_path / "second"
    left = development_result(first, metadata)
    assert left == development_result(second, metadata)
    for name in ("predictions.parquet", "segments.parquet", "results.json", "selection.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert verify_results(first) == left
    rows = pq.read_table(first / "predictions.parquet").to_pylist()
    assert rows and all(row["actual_sales"] is not None for row in rows)
    assert all(row["target_date"] > row["cutoff_date"] for row in rows)
    assert load_selection(first / "selection.json", metadata).selected_method == "last_known"
    with pytest.raises(ValueError, match="already exists"):
        development_result(first, metadata)


def test_holdout_calendar_is_reserved_before_outcome_inspection(tmp_path: Path) -> None:
    """Changing final dates within the same dataset/store study cannot reset its holdout."""
    metadata = protocol()
    reserve_holdout(tmp_path, metadata)
    reserve_holdout(tmp_path, metadata)
    changed_plan = make_plan(date(2015, 1, 1), date(2015, 1, 15), metadata.config)
    with pytest.raises(ValueError, match="already reserved"):
        reserve_holdout(tmp_path, metadata.model_copy(update={"plan": changed_plan}))


def test_selection_rejects_changed_code_config_or_corrupted_results(tmp_path: Path) -> None:
    """Final selection is tied to actual development evidence and its provenance."""
    metadata = protocol()
    development_result(tmp_path / "run", metadata)
    path = tmp_path / "run/selection.json"
    with pytest.raises(ValueError, match="differs"):
        load_selection(path, metadata.model_copy(update={"code_revision": "changed"}))
    state = SelectionRecord.model_validate_json(path.read_bytes())
    path.write_text(
        state.model_copy(update={"selected_method": "weekday_average"}).model_dump_json()
    )
    with pytest.raises(ValueError, match="selection was changed"):
        load_selection(path, metadata)
    parquet = tmp_path / "run/predictions.parquet"
    parquet.write_bytes(parquet.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        verify_results(tmp_path / "run")


def test_final_is_once_only_and_same_release_reuses_verified_cache(tmp_path: Path) -> None:
    """Final scores never feed selection; rerun reads cached bytes without refitting."""
    metadata = protocol()
    dev = tmp_path / "development"
    development_result(dev, metadata)
    selection = load_selection(dev / "selection.json", metadata)
    ledger = tmp_path / "ledger"
    assert claim_final(ledger, selection, "artifacts/evaluation/final") is False
    with pytest.raises(ValueError, match="incomplete"):
        claim_final(ledger, selection, "artifacts/evaluation/final")
    from retailforecast.evaluation.contracts import Outcome

    predicted = generate_predictions(
        FeatureBuilder(history()),
        metadata.plan.folds[-1:],
        metadata.config,
        [BaselineFactory("last_known")],
    )
    outcomes = outcome_index(
        Outcome(
            store_id=row.store_id,
            target_date=row.date,
            actual_sales=row.sales,
            available_as_of=row.available_as_of,
        )
        for row in history()
    )
    scored = score_predictions(predicted, outcomes, scoring_as_of=date(2015, 1, 14))
    final = tmp_path / "final"
    write_results(
        final, metadata, "final", ("last_known",), scored, summarize(scored), "last_known"
    )
    complete_final(
        ledger, selection, "artifacts/evaluation/final", file_checksum(final / "results.json")
    )
    assert claim_final(ledger, selection, "artifacts/evaluation/final", output_exists=True) is True
    assert verify_final_cache(ledger, selection, final).stage == "final"
    with pytest.raises(ValueError, match="another decision"):
        claim_final(
            ledger,
            selection.model_copy(update={"selected_method": "weekday_average"}),
            "artifacts/evaluation/final",
        )
    with pytest.raises(ValueError, match="another decision"):
        claim_final(ledger, selection, "artifacts/evaluation/another")
    report_path = final / "results.json"
    report_path.write_bytes(report_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="differs"):
        verify_final_cache(ledger, selection, final)


def test_existing_output_does_not_consume_a_new_final_release(tmp_path: Path) -> None:
    """Bad output arguments fail before creating a pending release record."""
    metadata = protocol()
    selection = SelectionRecord(
        protocol=metadata, selected_method="last_known", development_report_sha256="test-only"
    )
    with pytest.raises(ValueError, match="already exists"):
        claim_final(tmp_path, selection, "artifacts/evaluation/existing", output_exists=True)
    assert not list(tmp_path.glob("release-*.json"))
