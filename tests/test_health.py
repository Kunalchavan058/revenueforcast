"""Verify the public liveness contract and the scaffold's limited API surface."""

from fastapi.testclient import TestClient
from main import create_app


def test_health_contract() -> None:
    """Report API liveness without infrastructure or dataset dependencies."""
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "retailforecast-api",
        "api_version": "v1",
    }


def test_forecasting_rejects_empty_request() -> None:
    """Require a valid forecast request before any prediction."""
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/forecasts", json={})
    assert response.status_code == 422
