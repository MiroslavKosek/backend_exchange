import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.config import settings
from app.main import app
from app.services.exchange import ExchangeRateError, ExchangeService

@pytest.fixture
def exchange_analytics_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "super-secret")
    monkeypatch.setattr(settings, "jwt_secret_key", "unit-test-secret-key-32-bytes-long")
    return TestClient(app)

def test_extremes_endpoint_returns_strongest_and_weakest(
    exchange_analytics_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_latest_rates(base: str) -> dict:
        return {
            "base": base,
            "date": "2026-03-08",
            "rates": {"USD": 1.08, "CZK": 25.30, "JPY": 161.2},
        }

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = create_access_token({"sub": "admin"})
    response = exchange_analytics_client.get(
        "/api/rates/analytics/extremes?base=EUR",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "base": "EUR",
        "date": "2026-03-08",
        "strongest": {"currency": "JPY", "value": 161.2},
        "weakest": {"currency": "USD", "value": 1.08},
    }

def test_extremes_endpoint_returns_404_when_rates_are_empty(
    exchange_analytics_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_latest_rates(base: str) -> dict:
        return {"base": base, "date": "2026-03-08", "rates": {}}

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = create_access_token({"sub": "admin"})
    response = exchange_analytics_client.get(
        "/api/rates/analytics/extremes?base=EUR",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "No exchange rates available for the specified base currency."
    }

def test_extremes_endpoint_returns_502_on_exchange_service_error(
    exchange_analytics_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_latest_rates(_base: str) -> dict:
        raise ExchangeRateError("Failed to retrieve current exchange rates")

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = create_access_token({"sub": "admin"})
    response = exchange_analytics_client.get(
        "/api/rates/analytics/extremes?base=EUR",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Failed to retrieve current exchange rates"}

def test_extremes_endpoint_requires_authentication(exchange_analytics_client: TestClient):
    response = exchange_analytics_client.get("/api/rates/analytics/extremes?base=EUR")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
