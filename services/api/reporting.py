"""Read-only historical dashboard, options and saved forecast subset HTTP adapters."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from forecasts import ServiceDependency
from pydantic import ValidationError

from retailforecast.forecasting.contracts import MAX_FORECAST_STORES, ErrorResponse
from retailforecast.forecasting.errors import ForecastError
from retailforecast.reporting.contracts import (
    CoverageResponse,
    ForecastOptions,
    ForecastView,
    HistoryQuery,
    HistorySummary,
)
from retailforecast.reporting.history import HistoryService, history_csv
from retailforecast.reporting.options import forecast_options, forecast_view

router = APIRouter(
    prefix="/api/v1",
    tags=["business reporting"],
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


def history_query(
    dataset_version_id: UUID,
    start_date: date,
    end_date: date,
    store_ids: Annotated[list[int], Query(min_length=1, max_length=MAX_FORECAST_STORES)],
    frequency: Literal["day", "week", "month"] = "day",
) -> HistoryQuery:
    """Parse repeated store_ids query fields before applying domain interval/cohort limits."""
    try:
        return HistoryQuery(
            dataset_version_id=str(dataset_version_id),
            store_ids=tuple(store_ids),
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
        )
    except ValidationError as error:
        raise ForecastError("invalid_history_filters", str(error.errors()[0]["msg"])) from error


HistoryDependency = Annotated[HistoryQuery, Depends(history_query)]


@router.get("/history/coverage", response_model=CoverageResponse)
def coverage(
    service: ServiceDependency, dataset_version_id: UUID | None = None
) -> CoverageResponse:
    """Inspect the latest actual import or an explicitly pinned source."""
    return CoverageResponse(
        coverage=HistoryService(service.registry).coverage(
            str(dataset_version_id) if dataset_version_id else None
        )
    )


@router.get("/history/summary", response_model=HistorySummary)
def summary(query: HistoryDependency, service: ServiceDependency) -> HistorySummary:
    """Compute actual totals, calendar series, store and weekday comparisons from SQL."""
    return HistoryService(service.registry).summary(query)


@router.get(
    "/history/download.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
def download_history(query: HistoryDependency, service: ServiceDependency) -> Response:
    """Download exactly the same filter/grain and missingness used by the business dashboard."""
    return Response(
        history_csv(HistoryService(service.registry).summary(query)),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="observed-sales.csv"'},
    )


@router.get("/forecasts/options", response_model=ForecastOptions)
def options(service: ServiceDependency) -> ForecastOptions:
    """Read actual model/source coverage; never train or generate on page visit."""
    return forecast_options(service.registry)


@router.get("/forecasts/{forecast_id}/view", response_model=ForecastView)
def view(
    forecast_id: UUID,
    service: ServiceDependency,
    store_id: Annotated[int | None, Query(gt=0)] = None,
) -> ForecastView:
    """Aggregate one saved store subset with existing exact-decimal helpers, without fitting."""
    return forecast_view(service.get(str(forecast_id)), store_id)
