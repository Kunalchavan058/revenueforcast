"""Deterministic JSON/Parquet reports and workflow guards for a reserved holdout."""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict

from retailforecast.data.pipeline_config import canonical_json, content_hash, text_hash
from retailforecast.data.validation import file_checksum
from retailforecast.evaluation.contracts import BacktestConfig, BacktestPlan
from retailforecast.evaluation.metrics import Segment, choose_method
from retailforecast.evaluation.runner import PredictionPoint
from retailforecast.features.contracts import SnapshotContext
from retailforecast.features.registry import registry_fingerprint

ROOT = Path(__file__).resolve().parents[3]
PARQUET_BATCH_ROWS = 10_000


class EvaluationProtocol(BaseModel):
    """Bind data, dates, assumptions, source bytes and reproducibility settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    config: BacktestConfig
    plan: BacktestPlan
    snapshot: SnapshotContext
    code_revision: str
    working_tree_dirty: bool
    source_hashes: dict[str, str]
    dependency_lock_sha256: str
    registry_sha256: str
    python_version: str
    pyarrow_version: str

    @property
    def fingerprint(self) -> str:
        """Return identity without timestamps, private paths or output locations."""
        return content_hash(self.model_dump(mode="json"))


class EvaluationReport(BaseModel):
    """Publication manifest; references deterministic files and all fold/segment metrics."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    stage: Literal["development", "final"]
    protocol: EvaluationProtocol
    methods: tuple[str, ...]
    selected_method: str | None
    summaries: tuple[Segment, ...]
    file_checksums: dict[str, str]


class SelectionRecord(BaseModel):
    """Frozen development selection; final CLI has no method/tuning override."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    protocol: EvaluationProtocol
    selected_method: str | None
    development_report_sha256: str

    @property
    def fingerprint(self) -> str:
        """Identify this exact development decision, not merely the method name."""
        return content_hash(self.model_dump(mode="json"))


def build_protocol(
    config: BacktestConfig, plan: BacktestPlan, context: SnapshotContext
) -> EvaluationProtocol:
    """Capture actual source bytes, including uncommitted work, and the checked dataset."""
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
    )
    files = [
        path
        for package in ("data", "features", "evaluation", "forecasting")
        for path in (ROOT / "src" / "retailforecast" / package).glob("*.py")
    ]
    return EvaluationProtocol(
        config=config,
        plan=plan,
        snapshot=context,
        code_revision=revision,
        working_tree_dirty=dirty,
        source_hashes={
            path.relative_to(ROOT).as_posix(): text_hash(path) for path in sorted(files)
        },
        dependency_lock_sha256=text_hash(ROOT / "uv.lock"),
        registry_sha256=registry_fingerprint(),
        python_version=platform.python_version(),
        pyarrow_version=pa.__version__,
    )


def _write_table(path: Path, rows: list[dict[str, object]], schema: pa.Schema) -> None:
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=3,
        version="2.6",
        row_group_size=PARQUET_BATCH_ROWS,
    )


def write_results(
    output: Path,
    protocol: EvaluationProtocol,
    stage: Literal["development", "final"],
    methods: tuple[str, ...],
    points: Sequence[PredictionPoint],
    summaries: Sequence[Segment],
    selected_method: str | None,
) -> EvaluationReport:
    """Write private result files, publishing results.json last; never overwrite an old run."""
    if output.exists():
        raise ValueError("Output directory already exists; choose a new run directory")
    output.mkdir(parents=True)
    fields = [
        pa.field("fold_id", pa.string()),
        pa.field("method", pa.string()),
        pa.field("store_id", pa.int32()),
        pa.field("cutoff_date", pa.date32()),
        pa.field("target_date", pa.date32()),
        pa.field("horizon_days", pa.int8()),
        pa.field("trained_until", pa.date32()),
    ]
    for name in (
        "raw_prediction",
        "predicted_sales",
        "actual_sales",
        "signed_error",
        "absolute_error",
        "squared_error",
        "squared_percentage_error",
    ):
        fields.append(pa.field(name, pa.float64()))
    for name in ("known_open", "observed_open", "nonnegative_clamped", "closure_adjusted"):
        fields.append(pa.field(name, pa.bool_()))
    fields.append(pa.field("status", pa.string()))
    _write_table(
        output / "predictions.parquet", [point.model_dump() for point in points], pa.schema(fields)
    )
    summary_rows = [
        dict(method=item.method, axis=item.axis, value=item.value, **item.metrics.model_dump())
        for item in summaries
    ]
    summary_fields = [pa.field(name, pa.string()) for name in ("method", "axis", "value")]
    for name in ("requested", "labeled", "scored", "zero_actuals", "rmspe_zero_excluded"):
        summary_fields.append(pa.field(name, pa.int64()))
    for name in (
        "coverage",
        "labeled_actual_sales_sum",
        "scored_actual_sales_sum",
        "scored_predicted_sales_sum",
        "mae",
        "rmse",
        "rmspe",
    ):
        summary_fields.append(pa.field(name, pa.float64()))
    _write_table(output / "segments.parquet", summary_rows, pa.schema(summary_fields))
    report = EvaluationReport(
        stage=stage,
        protocol=protocol,
        methods=methods,
        selected_method=selected_method,
        summaries=tuple(summaries),
        file_checksums={
            name: file_checksum(output / name)
            for name in ("predictions.parquet", "segments.parquet")
        },
    )
    (output / "results.json").write_bytes(canonical_json(report.model_dump(mode="json")))
    if stage == "development":
        selection = SelectionRecord(
            protocol=protocol,
            selected_method=selected_method,
            development_report_sha256=file_checksum(output / "results.json"),
        )
        (output / "selection.json").write_bytes(canonical_json(selection.model_dump(mode="json")))
    return report


def verify_results(output: Path) -> EvaluationReport:
    """Reject incomplete or modified cached artifacts before reporting success."""
    report = EvaluationReport.model_validate_json((output / "results.json").read_bytes())
    if set(report.file_checksums) != {"predictions.parquet", "segments.parquet"}:
        raise ValueError("Result file manifest is incomplete")
    for name, checksum in report.file_checksums.items():
        if file_checksum(output / name) != checksum:
            raise ValueError(f"Result artifact checksum mismatch: {name}")
    return report


def load_selection(path: Path, protocol: EvaluationProtocol) -> SelectionRecord:
    """Validate development evidence and current protocol before any final scoring."""
    selection = SelectionRecord.model_validate_json(path.read_bytes())
    report = verify_results(path.parent)
    if (
        report.stage != "development"
        or selection.protocol != protocol
        or report.protocol != protocol
    ):
        raise ValueError("Selection data/config/code/environment differs from the current protocol")
    if file_checksum(path.parent / "results.json") != selection.development_report_sha256:
        raise ValueError("Development report changed after selection")
    if (
        selection.selected_method is None
        or choose_method(report.summaries) != selection.selected_method
    ):
        raise ValueError("No eligible frozen development winner, or selection was changed")
    return selection


def reserve_holdout(ledger: Path, protocol: EvaluationProtocol) -> None:
    """Reserve the final calendar for this dataset/store scope before development scoring."""
    ledger.mkdir(parents=True, exist_ok=True)
    scope = content_hash(
        {
            "dataset": protocol.snapshot.dataset_fingerprint,
            "stores": sorted(protocol.config.store_ids),
        }
    )
    path = ledger / f"reservation-{scope}.json"
    reserved = canonical_json(protocol.plan.folds[-1].model_dump(mode="json"))
    try:
        with path.open("xb") as handle:
            handle.write(reserved)
    except FileExistsError:
        if path.read_bytes() != reserved:
            raise ValueError(
                "Final holdout dates already reserved for this dataset/store scope"
            ) from None


def claim_final(
    ledger: Path, selection: SelectionRecord, output_relative: str, *, output_exists: bool = False
) -> bool:
    """Claim final once; same decision/output can reuse verified cached results.

    Returns True when a completed identical release already exists. A pending
    failed release stays visible and cannot silently become a new tuned attempt.
    This is an auditable local workflow guard, not protection from manual tampering.
    """
    reserve_holdout(ledger, selection.protocol)
    path = _release_path(ledger, selection)
    if output_exists and not path.exists():
        raise ValueError("Output already exists; choose a new final run directory")
    receipt = HoldoutReceipt(
        selection=selection.fingerprint, output=output_relative, state="pending"
    )
    try:
        with path.open("xb") as handle:
            handle.write(canonical_json(receipt.model_dump(mode="json")))
    except FileExistsError:
        prior = HoldoutReceipt.model_validate_json(path.read_bytes())
        if prior.selection != selection.fingerprint or prior.output != output_relative:
            raise ValueError("Final holdout already released for another decision/output") from None
        if prior.state != "complete":
            raise ValueError(
                "Final release is incomplete; inspect/restore its artifacts before retry"
            ) from None
        return True
    return False


def complete_final(
    ledger: Path, selection: SelectionRecord, output_relative: str, report_sha256: str
) -> None:
    """Finish the claimed release after writing and verifying its publication manifest."""
    path = _release_path(ledger, selection)
    prior = HoldoutReceipt.model_validate_json(path.read_bytes())
    if (
        prior.state != "pending"
        or prior.selection != selection.fingerprint
        or prior.output != output_relative
    ):
        raise ValueError("Final completion must match an existing pending claim")
    receipt = HoldoutReceipt(
        selection=selection.fingerprint,
        output=output_relative,
        state="complete",
        report_sha256=report_sha256,
    )
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(canonical_json(receipt.model_dump(mode="json")))
    temporary.replace(path)


def verify_final_cache(ledger: Path, selection: SelectionRecord, output: Path) -> EvaluationReport:
    """Verify the exact final report and referenced Parquet files on an idempotent rerun."""
    receipt = HoldoutReceipt.model_validate_json(_release_path(ledger, selection).read_bytes())
    report = verify_results(output)
    if (
        receipt.state != "complete"
        or receipt.selection != selection.fingerprint
        or file_checksum(output / "results.json") != receipt.report_sha256
        or report.protocol != selection.protocol
        or report.stage != "final"
        or report.selected_method != selection.selected_method
    ):
        raise ValueError("Final cached report differs from the released result")
    return report


class HoldoutReceipt(BaseModel):
    """Typed local release ledger entry; interrupted releases remain explicit."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    selection: str
    output: str
    state: Literal["pending", "complete"]
    report_sha256: str | None = None


def _release_path(ledger: Path, selection: SelectionRecord) -> Path:
    scope = content_hash(
        {
            "dataset": selection.protocol.snapshot.dataset_fingerprint,
            "stores": sorted(selection.protocol.config.store_ids),
            "final": selection.protocol.plan.folds[-1].model_dump(mode="json"),
        }
    )
    return ledger / f"release-{scope}.json"
