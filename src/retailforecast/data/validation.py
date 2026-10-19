"""Streaming Rossmann validation with bounded diagnostics and explicit label separation."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from retailforecast.data.contracts import (
    FileReport,
    ImportRequest,
    InputRow,
    SaleRow,
    SourceRow,
    StoreRow,
    SubmissionRow,
    ValidationIssue,
    ValidationReport,
)

SOURCE_MODELS: dict[str, type[SourceRow]] = {
    "store.csv": StoreRow,
    "train.csv": SaleRow,
    "test.csv": InputRow,
    "sample_submission.csv": SubmissionRow,
}
REQUIRED_COLUMNS = {
    "store.csv": {"Store"},
    "train.csv": {
        "Store",
        "Date",
        "Sales",
        "Customers",
        "Open",
        "Promo",
        "DayOfWeek",
        "StateHoliday",
        "SchoolHoliday",
    },
    "test.csv": {"Id", "Store", "Date", "Promo", "DayOfWeek", "StateHoliday", "SchoolHoliday"},
    "sample_submission.csv": {"Id", "Sales"},
}
MAX_ISSUE_EXAMPLES = 50
HASH_CHUNK_BYTES = 1024 * 1024


def file_checksum(path: Path) -> str:
    """Hash bytes without loading the dataset into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_rows(path: Path) -> Iterator[tuple[int, dict[str, str | None]]]:
    """Yield line-numbered CSV mappings, rejecting extra cells and malformed quoting."""
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream, strict=True)
        for row in reader:
            if None in row:
                raise ValueError(f"{path.name} row {reader.line_num}: extra CSV cells")
            yield reader.line_num, row


def add_issue(report: ValidationReport, filename: str, row: int | None, message: str) -> None:
    """Count every error while bounding in-memory and persisted diagnostic examples."""
    report.valid = False
    report.issue_count += 1
    if len(report.issues) < MAX_ISSUE_EXAMPLES:
        report.issues.append(ValidationIssue(file=filename, row=row, message=message))


def inspect_headers(path: Path, report: ValidationReport, file_report: FileReport) -> bool:
    """Validate required/unknown/duplicate headers before reading records."""
    with path.open(newline="", encoding="utf-8-sig") as stream:
        headers = next(csv.reader(stream, strict=True), [])
    expected = {
        field.alias or name for name, field in SOURCE_MODELS[path.name].model_fields.items()
    }
    missing = REQUIRED_COLUMNS[path.name] - set(headers)
    unknown = set(headers) - expected
    file_report.missing_optional_columns = sorted(expected - set(headers) - missing)
    if missing or unknown or len(headers) != len(set(headers)):
        add_issue(
            report,
            path.name,
            1,
            f"Invalid columns: missing={sorted(missing)}, unknown={sorted(unknown)}; "
            "headers must be unique and match the source contract.",
        )
        return False
    file_report.missingness = dict.fromkeys(sorted(expected), 0)
    return True


def validate_record(
    values: dict[str, str | None],
    model: type[SourceRow],
    request: ImportRequest,
) -> SourceRow:
    """Coerce CSV numerics and enforce date policy without replacing bad data."""
    parsed = model.model_validate(values)
    record_date = getattr(parsed, "date", None)
    if isinstance(record_date, date) and not (
        request.minimum_date <= record_date <= request.maximum_date
    ):
        raise ValueError("Date is outside configured minimum_date/maximum_date")
    return parsed


def scan_file(
    path: Path,
    request: ImportRequest,
    report: ValidationReport,
    known_stores: set[int],
) -> tuple[set[tuple[int, date]], set[int]]:
    """Scan one file, retaining only uniqueness keys rather than full data rows."""
    summary = report.files[path.name]
    pairs: set[tuple[int, date]] = set()
    identifiers: set[int] = set()
    stores: set[int] = set()
    if not inspect_headers(path, report, summary):
        return pairs, identifiers
    for line, values in source_rows(path):
        summary.rows += 1
        for column in summary.missingness:
            if values.get(column) is None or not str(values[column]).strip():
                summary.missingness[column] += 1
        try:
            parsed = validate_record(values, SOURCE_MODELS[path.name], request)
            if isinstance(parsed, StoreRow):
                if parsed.store_id in identifiers:
                    summary.duplicates += 1
                    raise ValueError("Duplicate Store identifier")
                identifiers.add(parsed.store_id)
                known_stores.add(parsed.store_id)
                stores.add(parsed.store_id)
            if isinstance(parsed, (SaleRow, InputRow)):
                stores.add(parsed.store_id)
                if parsed.store_id not in known_stores:
                    raise ValueError("Store is absent from store.csv")
                key = (parsed.store_id, parsed.date)
                if key in pairs:
                    summary.duplicates += 1
                    raise ValueError("Duplicate (Store, Date)")
                pairs.add(key)
                summary.date_min = min(summary.date_min or parsed.date, parsed.date)
                summary.date_max = max(summary.date_max or parsed.date, parsed.date)
                summary.closed_stores += parsed.is_open == 0
                summary.missing_open += parsed.is_open is None
                if isinstance(parsed, SaleRow):
                    summary.closed_with_sales += parsed.is_open == 0 and parsed.sales > 0
                    summary.zero_sales_when_open += parsed.is_open == 1 and parsed.sales == 0
            if isinstance(parsed, (InputRow, SubmissionRow)):
                if parsed.submission_id in identifiers:
                    summary.duplicates += 1
                    raise ValueError("Duplicate Id")
                identifiers.add(parsed.submission_id)
            summary.valid_rows += 1
        except (ValidationError, ValueError) as error:
            summary.invalid_rows += 1
            message = (
                "; ".join(f"{item['loc']}: {item['msg']}" for item in error.errors())
                if isinstance(error, ValidationError)
                else str(error)
            )
            add_issue(report, path.name, line, message)
    summary.unique_stores = len(stores)
    if summary.rows == 0:
        add_issue(report, path.name, None, "File contains no data records")
    if file_checksum(path) != summary.checksum:
        add_issue(report, path.name, None, "Source changed while validating; retry a stable copy")
    return pairs, identifiers


def validate_bundle(request: ImportRequest) -> ValidationReport:
    """Validate all four files and cross-file keys; does not connect to a database."""
    directory = Path(request.source_dir).resolve()
    if request.minimum_date > request.maximum_date:
        raise ValueError("minimum_date must be on or before maximum_date")
    manifest = {
        name: file_checksum(directory / name) if (directory / name).is_file() else "missing"
        for name in SOURCE_MODELS
    }
    identity = {
        "files": manifest,
        "contract": "rossmann-v1",
        "availability": request.availability_policy,
    }
    checksum = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    report = ValidationReport(
        checksum=checksum,
        minimum_date=request.minimum_date,
        maximum_date=request.maximum_date,
        availability_policy=request.availability_policy,
        files={name: FileReport(filename=name, checksum=value) for name, value in manifest.items()},
    )
    known_stores: set[int] = set()
    train_pairs: set[tuple[int, date]] = set()
    test_ids: set[int] = set()
    submission_ids: set[int] = set()
    for name in SOURCE_MODELS:
        path = directory / name
        if not path.is_file():
            add_issue(
                report,
                name,
                None,
                f"Missing {name}; download/unzip the Rossmann competition files first.",
            )
            continue
        try:
            pairs, ids = scan_file(path, request, report, known_stores)
            if name == "train.csv":
                train_pairs = pairs
            elif name == "test.csv":
                test_ids = ids
                if train_pairs.intersection(pairs):
                    add_issue(report, name, None, "Train and test (Store, Date) keys overlap")
                train_pairs.clear()
            elif name == "sample_submission.csv":
                submission_ids = ids
        except (csv.Error, UnicodeError, OSError, ValueError) as error:
            add_issue(report, name, None, f"Cannot parse CSV: {error}")
    if test_ids != submission_ids:
        add_issue(
            report,
            "sample_submission.csv",
            None,
            "Id coverage must exactly match test.csv; template Sales are not actuals.",
        )
    for summary in report.files.values():
        if summary.closed_with_sales:
            report.warnings.append(
                f"{summary.filename}: {summary.closed_with_sales} closed rows have positive Sales; "
                "retained unchanged, not automatically zeroed."
            )
        if summary.missing_open:
            report.warnings.append(
                f"{summary.filename}: {summary.missing_open} unknown Open values retained as NULL."
            )
        if summary.zero_sales_when_open:
            report.warnings.append(
                f"{summary.filename}: {summary.zero_sales_when_open} open rows "
                "have zero Sales; retained."
            )
    report.warnings.append(
        "test.csv has no labels; sample_submission.csv contains placeholders, never ground truth."
    )
    return report
