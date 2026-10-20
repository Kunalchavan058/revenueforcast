"""Hand-computed business reports against real isolated PostgreSQL; no estimator is needed."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from forecasts import forecast_service
from main import create_app
from sqlalchemy import Engine, select

from retailforecast.forecasting.service import ForecastService
from retailforecast.lifecycle.registry import ModelRegistry
from retailforecast.reporting.contracts import HistoryQuery
from retailforecast.reporting.history import HistoryService
from retailforecast.storage.models import DailySale, DatasetVersion, Store


@pytest.fixture
def reports(
    postgres_database: tuple[Engine, str], tmp_path: Path
) -> tuple[HistoryService, ModelRegistry, str]:
    """Two synthetic stores, a missing Friday, Sunday zeros and one closed-positive quirk."""
    registry = ModelRegistry(postgres_database[0], tmp_path / "models", tmp_path / "tracking")
    with registry.sessions.begin() as session:
        source = DatasetVersion(
            source="synthetic-report-fixture",
            checksum="a" * 64,
            version="b" * 64,
            rows=9,
            available_through=date(2015, 8, 3),
            availability_policy="explicit fixture",
            raw_uri="synthetic-only",
            validation_report={},
        )
        session.add(source)
        session.flush()
        source_id = source.id
        session.add_all([Store(source_version=source_id, store_id=store) for store in (1, 2, 3)])
        session.flush()
        for store, day, sales, opened in [
            (1, "2015-07-30", "10.1", True),
            (2, "2015-07-30", "20.2", True),
            (1, "2015-07-31", "0", False),
            (1, "2015-08-01", "4.3", True),
            (2, "2015-08-01", "8.4", True),
            (1, "2015-08-02", "0", False),
            (2, "2015-08-02", "5", False),
            (1, "2015-08-03", "7", True),
            (2, "2015-08-03", "9", True),
        ]:
            observed = date.fromisoformat(day)
            session.add(
                DailySale(
                    source_version=source_id,
                    store_id=store,
                    date=observed,
                    sales=Decimal(sales),
                    customers=0,
                    is_open=opened,
                    promotion=False,
                    day_of_week=observed.isoweekday(),
                    state_holiday="0",
                    school_holiday=False,
                )
            )
    return HistoryService(registry), registry, source_id


def query(source_id: str, frequency: str = "day", stores: tuple[int, ...] = (1, 2)) -> HistoryQuery:
    """Keep the five-day reporting interval explicit for hand calculations."""
    return HistoryQuery.model_validate(
        dict(
            dataset_version_id=source_id,
            store_ids=stores,
            start_date="2015-07-30",
            end_date="2015-08-03",
            frequency=frequency,
        )
    )


@pytest.fixture
def report_client(reports: tuple[HistoryService, ModelRegistry, str]) -> TestClient:
    """HTTP uses the same real migrated schema; no database or numbers are mocked."""
    app = create_app()
    app.dependency_overrides[forecast_service] = lambda: ForecastService(reports[1])
    return TestClient(app)


def params(source_id: str, frequency: str = "day") -> list[tuple[str, str]]:
    """Represent repeated query IDs exactly like the browser URLSearchParams client."""
    return [
        ("dataset_version_id", source_id),
        ("store_ids", "1"),
        ("store_ids", "2"),
        ("start_date", "2015-07-30"),
        ("end_date", "2015-08-03"),
        ("frequency", frequency),
    ]


def test_exact_totals_missingness_and_closed_days(
    reports: tuple[HistoryService, ModelRegistry, str],
) -> None:
    """No epsilon labels, missing-day zeros or deletion of closed positive sales."""
    service, _, source = reports
    result = service.summary(query(source))
    assert result.total_sales == Decimal("64")
    assert (
        result.observed_store_days == 9
        and result.expected_store_days == 10
        and result.missing_store_days == 1
    )
    assert (
        result.open_store_days == 6
        and result.closed_store_days == 3
        and result.closed_positive_sales_days == 1
    )
    assert [row.sales for row in result.by_store] == [Decimal("21.4"), Decimal("42.6")]
    sunday = result.weekdays[6]
    assert sunday.sales == 5 and sunday.observations == 2 and sunday.mean_sales == Decimal("2.5000")
    assert result.series[1].sales == 0 and result.series[1].observed_store_days == 1


@pytest.mark.parametrize("frequency,totals", [("week", ["48", "16"]), ("month", ["30.3", "33.7"])])
def test_calendar_buckets_keep_partial_periods(
    reports: tuple[HistoryService, ModelRegistry, str], frequency: str, totals: list[str]
) -> None:
    """Week/month totals have the same grand sum and disclose the requested partial period."""
    result = reports[0].summary(query(reports[2], frequency))
    assert [row.sales for row in result.series] == list(map(Decimal, totals))
    assert result.series[0].covered_from == date(2015, 7, 30)
    assert sum(row.sales or Decimal(0) for row in result.series) == 64


def test_store_filter_and_source_mutation_recompute(
    reports: tuple[HistoryService, ModelRegistry, str],
) -> None:
    """Both cohort changes and legitimate SQL observations change computed report results."""
    service, registry, source = reports
    assert service.summary(query(source, stores=(1,))).total_sales == Decimal("21.4")
    with registry.sessions.begin() as session:
        row = session.scalar(
            select(DailySale).where(
                DailySale.source_version == source,
                DailySale.store_id == 1,
                DailySale.date == date(2015, 7, 30),
            )
        )
        assert row is not None
        row.sales += Decimal(10)
    assert service.summary(query(source)).total_sales == 74


def test_no_observations_is_null_not_zero(
    reports: tuple[HistoryService, ModelRegistry, str],
) -> None:
    """Imported metadata without labels remains an explicit empty cohort."""
    result = reports[0].summary(query(reports[2], stores=(3,)))
    assert result.total_sales is None and result.observed_through is None
    assert all(row.sales is None for row in result.series)
    assert result.observed_store_days == 0 and result.missing_store_days == 5


def test_http_filters_and_csv_match(
    report_client: TestClient, reports: tuple[HistoryService, ModelRegistry, str]
) -> None:
    """CSV and JSON share provenance, exact totals and coverage without training."""
    source = reports[2]
    response = report_client.get(
        "/api/v1/history/summary", params=urlencode(params(source, "week"))
    )
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["total_sales"]) == 64
    download = report_client.get(
        "/api/v1/history/download.csv", params=urlencode(params(source, "week"))
    )
    rows = list(csv.DictReader(io.StringIO(download.text)))
    assert sum(Decimal(row["observed_sales"]) for row in rows) == 64
    assert {row["dataset_version_id"] for row in rows} == {source}
    assert rows[0]["observed_store_days"] == "7"
    coverage = report_client.get("/api/v1/history/coverage").json()["coverage"]
    assert coverage["observed_from"] == "2015-07-30" and coverage["default_store_ids"] == [1, 2]
    assert report_client.get("/api/v1/forecasts/options").json()["model"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("store_ids", "0"),
        ("store_ids", "999"),
        ("start_date", "bad"),
        ("start_date", "2015-08-04"),
        ("end_date", "2015-08-05"),
    ],
)
def test_invalid_history_filter_is_actionable(
    report_client: TestClient,
    reports: tuple[HistoryService, ModelRegistry, str],
    field: str,
    value: str,
) -> None:
    """Invalid identifiers/date ranges fail with 422 instead of a silent truncated report."""
    arguments = [(key, val) for key, val in params(reports[2]) if key != field] + [(field, value)]
    assert (
        report_client.get("/api/v1/history/summary", params=urlencode(arguments)).status_code == 422
    )


def test_duplicate_store_selection_rejected(
    report_client: TestClient, reports: tuple[HistoryService, ModelRegistry, str]
) -> None:
    """Repeated IDs never inflate the selected store count or sales totals."""
    arguments = params(reports[2]) + [("store_ids", "1")]
    assert (
        report_client.get("/api/v1/history/summary", params=urlencode(arguments)).status_code == 422
    )
