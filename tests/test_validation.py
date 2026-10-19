"""Test source contracts and temporal label separation with tiny examples."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from rossmann_fixtures import TRAIN_FIELDS, write_bundle, write_csv

from retailforecast.data.contracts import ImportRequest
from retailforecast.data.ingestion import import_bundle
from retailforecast.data.validation import validate_bundle


def request_for(directory: Path) -> ImportRequest:
    """Use stable date bounds so test reports do not depend on the wall clock."""
    return ImportRequest(source_dir=str(directory), maximum_date=date(2026, 12, 31))


def test_dry_run_preserves_missing_optional_metadata(tmp_path: Path) -> None:
    """Validate without DB/raw-copy side effects and retain known/unknown closure states."""
    source = write_bundle(tmp_path / "source")
    result = import_bundle(request_for(source), raw_root=tmp_path / "raw")
    assert result.state == "validated"
    assert result.dataset_version_id is None
    assert not (tmp_path / "raw").exists()
    assert result.report.files["train.csv"].closed_stores == 1
    assert result.report.files["test.csv"].missing_open == 1
    assert result.report.files["store.csv"].missing_optional_columns
    assert result.report.files["train.csv"].rows == 2
    assert result.report.files["train.csv"].date_max == date(2015, 7, 31)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Date", "2015-02-30"),
        ("Date", "1900-01-01"),
        ("Sales", "-1"),
        ("Sales", "NaN"),
        ("Sales", "abc"),
        ("Customers", "1.5"),
        ("Open", "2"),
        ("DayOfWeek", "7"),
    ],
)
def test_invalid_scalars_have_actionable_rows(tmp_path: Path, field: str, value: str) -> None:
    """Reject impossible dates, negative/nonfinite values and fractional customer counts."""
    source = write_bundle(tmp_path)
    row = ["1", "5", "2015-07-31", "20", "2", "1", "0", "0", "0"]
    row[TRAIN_FIELDS.index(field)] = value
    write_csv(source / "train.csv", TRAIN_FIELDS, [row])
    report = validate_bundle(request_for(source))
    assert not report.valid
    assert report.files["train.csv"].invalid_rows == 1
    assert any(issue.file == "train.csv" and issue.row == 2 for issue in report.issues)


def test_numeric_coercion_and_closed_store_quirk(tmp_path: Path) -> None:
    """Accept exact CSV integer coercion and preserve positive Sales on a closed row."""
    source = write_bundle(tmp_path)
    write_csv(
        source / "train.csv",
        TRAIN_FIELDS,
        [
            ["1.0", "5", "2015-07-31", "12.50", "2.0", "0", "1", "0", "0"],
        ],
    )
    report = validate_bundle(request_for(source))
    assert report.valid
    assert report.files["train.csv"].closed_with_sales == 1
    assert any("not automatically zeroed" in warning for warning in report.warnings)


def test_missing_required_column(tmp_path: Path) -> None:
    """Name a missing label column instead of substituting zero sales."""
    source = write_bundle(tmp_path)
    write_csv(source / "train.csv", ["Store", "Date"], [["1", "2015-07-31"]])
    report = validate_bundle(request_for(source))
    assert not report.valid
    assert any("Sales" in issue.message and "missing" in issue.message for issue in report.issues)


def test_duplicate_store_date(tmp_path: Path) -> None:
    """Count and reject repeated actuals rather than dropping an arbitrary row."""
    source = write_bundle(tmp_path)
    with (source / "train.csv").open("a", encoding="utf-8") as stream:
        stream.write("1,5,2015-07-31,0,0,0,0,0,0\n")
    report = validate_bundle(request_for(source))
    assert not report.valid
    assert report.files["train.csv"].duplicates == 1


def test_test_labels_are_forbidden(tmp_path: Path) -> None:
    """Never import a modified test file with an apparent ground-truth Sales column."""
    source = write_bundle(tmp_path)
    write_csv(
        source / "test.csv",
        ["Id", "Store", "Date", "Promo", "DayOfWeek", "Sales"],
        [["1", "1", "2015-08-01", "0", "6", "999"]],
    )
    report = validate_bundle(request_for(source))
    assert not report.valid
    assert any("unknown=['Sales']" in issue.message for issue in report.issues)


def test_submission_id_coverage(tmp_path: Path) -> None:
    """A mismatched export template is rejected without promoting placeholder labels."""
    source = write_bundle(tmp_path)
    write_csv(source / "sample_submission.csv", ["Id", "Sales"], [["2", "0"]])
    report = validate_bundle(request_for(source))
    assert not report.valid
    assert any("Id coverage" in issue.message for issue in report.issues)


def test_validation_bounds_do_not_change_snapshot_identity(tmp_path: Path) -> None:
    """Reruns on a later day do not invent a new version of identical source bytes."""
    source = write_bundle(tmp_path)
    first = request_for(source)
    second = first.model_copy(update={"maximum_date": date(2027, 12, 31)})
    assert validate_bundle(first).checksum == validate_bundle(second).checksum


def test_missing_download_is_reported(tmp_path: Path) -> None:
    """Missing data produces instructions, never synthetic replacement observations."""
    report = validate_bundle(request_for(tmp_path))
    assert not report.valid
    assert all(item.rows == 0 for item in report.files.values())
    assert any("download/unzip" in issue.message for issue in report.issues)


def test_issue_examples_are_bounded_but_counts_are_complete(tmp_path: Path) -> None:
    """Large broken inputs retain complete totals without unbounded diagnostic storage."""
    source = write_bundle(tmp_path)
    duplicate = ["1", "5", "2015-07-31", "0", "0", "0", "0", "0", "0"]
    write_csv(source / "train.csv", TRAIN_FIELDS, [duplicate] * 60)
    report = validate_bundle(request_for(source))
    assert report.issue_count == 59
    assert len(report.issues) == 50
    assert report.files["train.csv"].duplicates == 59
    assert report.files["train.csv"].rows == 60
