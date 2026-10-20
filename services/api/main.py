"""FastAPI liveness and checked local model lifecycle endpoints."""

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from forecasts import router as forecasts_router
from models import router as models_router
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from training_jobs import router as training_jobs_router

from retailforecast.forecasting.contracts import ErrorDetail, ErrorResponse
from retailforecast.forecasting.errors import ForecastError


class HealthResponse(BaseModel):
    """Describe API liveness, not readiness of future storage or ML services."""

    status: Literal["ok"]
    service: Literal["retailforecast-api"]
    api_version: Literal["v1"]


def create_app() -> FastAPI:
    """Build the HTTP application without connecting to external services."""
    application = FastAPI(title="RetailForecast AI", version="0.1.0")

    @application.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Return process liveness; no database, dataset, or model is required."""
        return HealthResponse(status="ok", service="retailforecast-api", api_version="v1")

    @application.exception_handler(ForecastError)
    async def forecast_error(request: Request, error: ForecastError) -> JSONResponse:
        """Keep domain errors actionable without exposing SQL, credentials or local paths."""
        body = ErrorResponse(error=ErrorDetail(code=error.code, message=error.message))
        return JSONResponse(status_code=error.status_code, content=body.model_dump(mode="json"))

    @application.exception_handler(SQLAlchemyError)
    async def storage_error(request: Request, error: SQLAlchemyError) -> JSONResponse:
        """Fail honestly when the local database is unavailable, never return fake results."""
        body = ErrorResponse(
            error=ErrorDetail(
                code="storage_unavailable",
                message="Database operation failed; check PostgreSQL and migrations",
            )
        )
        return JSONResponse(status_code=503, content=body.model_dump(mode="json"))

    application.include_router(training_jobs_router)
    application.include_router(forecasts_router)
    application.include_router(models_router)
    return application


app = create_app()
