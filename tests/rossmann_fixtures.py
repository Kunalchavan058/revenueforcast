"""Hand-checkable synthetic Rossmann examples, not copied source data."""

from __future__ import annotations

import csv
from pathlib import Path

TRAIN_FIELDS = [
    "Store",
    "DayOfWeek",
    "Date",
    "Sales",
    "Customers",
    "Open",
    "Promo",
    "StateHoliday",
    "SchoolHoliday",
]
TEST_FIELDS = ["Id", "Store", "DayOfWeek", "Date", "Open", "Promo", "StateHoliday", "SchoolHoliday"]


def write_csv(path: Path, fields: list[str], rows: list[list[str]]) -> None:
    """Write a small source-shaped fixture preserving exact caller-supplied scalars."""
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)


def write_bundle(directory: Path) -> Path:
    """Create two observed days, one unlabeled future day, and its placeholder."""
    directory.mkdir(parents=True, exist_ok=True)
    write_csv(directory / "store.csv", ["Store"], [["1"]])
    write_csv(
        directory / "train.csv",
        TRAIN_FIELDS,
        [
            ["1", "4", "2015-07-30", "20", "2", "1", "0", "0", "0"],
            ["1", "5", "2015-07-31", "0", "0", "0", "0", "0", "0"],
        ],
    )
    write_csv(
        directory / "test.csv",
        TEST_FIELDS,
        [
            ["1", "1", "6", "2015-08-01", "", "0", "0", "0"],
        ],
    )
    write_csv(directory / "sample_submission.csv", ["Id", "Sales"], [["1", "0"]])
    return directory
