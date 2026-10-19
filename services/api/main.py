"""FastAPI service entry point; forecasting and storage are not implemented."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


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

    return application


app = create_app()
