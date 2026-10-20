"""Versioned prediction, data discovery, CSV and generated feature-contract endpoints."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from models import model_registry

from retailforecast.features.registry import (
    FEATURE_REGISTRY,
    FeatureDefinition,
    registry_fingerprint,
)
from retailforecast.forecasting.catalog import CatalogService, DatasetStatus, StorePage
from retailforecast.forecasting.contracts import (
    ApiContract,
    ErrorResponse,
    ForecastRequest,
    ForecastResponse,
)
from retailforecast.forecasting.service import ForecastService
from retailforecast.forecasting.totals import forecast_csv

router = APIRouter(
    prefix="/api/v1",
    tags=["forecasts"],
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


@lru_cache(maxsize=1)
def forecast_service() -> ForecastService:
    """Lazily share a bounded service; resolve and verify active model per POST, never fit."""
    return ForecastService(model_registry())


ServiceDependency = Annotated[ForecastService, Depends(forecast_service)]


class FeatureRegistryResponse(ApiContract):
    """The real registry includes prohibited fields explicitly marked predictor=false."""

    fingerprint: str
    features: tuple[FeatureDefinition, ...]


@router.get("/datasets/status", response_model=DatasetStatus, tags=["data"])
def dataset_status(service: ServiceDependency) -> DatasetStatus:
    """Distinguish latest imported labels from active model data and wall-clock time."""
    return CatalogService(service.registry).status()


@router.get("/stores", response_model=StorePage, tags=["data"])
def stores(
    service: ServiceDependency,
    search: Annotated[str, Query(max_length=50)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    dataset_version_id: str | None = None,
) -> StorePage:
    """Return searchable source store IDs with pagination and active-model support."""
    return CatalogService(service.registry).stores(
        search=search, page=page, page_size=page_size, dataset_version_id=dataset_version_id
    )


@router.post(
    "/forecasts",
    status_code=201,
    response_model=ForecastResponse,
    responses={
        422: {
            "description": "Invalid request or unavailable store/history/cutoff",
            "content": {
                "application/json": {
                    "schema": {
                        "anyOf": [
                            {"$ref": "#/components/schemas/HTTPValidationError"},
                            {"$ref": "#/components/schemas/ErrorResponse"},
                        ]
                    }
                }
            },
        }
    },
)
def create_forecast(request: ForecastRequest, service: ServiceDependency) -> ForecastResponse:
    """Reuse a saved model and atomically persist direct 1..48-day predictions."""
    return service.create(request)


@router.get("/forecasts/{forecast_id}", response_model=ForecastResponse)
def get_forecast(forecast_id: UUID, service: ServiceDependency) -> ForecastResponse:
    """Read frozen values and metadata without needing the original model files."""
    return service.get(str(forecast_id))


@router.get(
    "/forecasts/{forecast_id}/download.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
def download_forecast(forecast_id: UUID, service: ServiceDependency) -> Response:
    """Export the saved store-day values with model and historical source metadata."""
    return Response(
        content=forecast_csv(service.get(str(forecast_id))),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="forecast-{forecast_id}.csv"'},
    )


@router.get("/model/feature-registry", response_model=FeatureRegistryResponse, tags=["features"])
def feature_registry() -> FeatureRegistryResponse:
    """Expose generated serving and exclusion policies without infrastructure dependencies."""
    return FeatureRegistryResponse(fingerprint=registry_fingerprint(), features=FEATURE_REGISTRY)
