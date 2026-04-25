"""Endpoint tests for exchange analytics routes."""

# Pylint may not resolve app imports from conftest path setup in test context.
# Pytest fixture argument shadowing and terse test helpers are intentional.
# pylint: disable=import-error,missing-function-docstring,redefined-outer-name,duplicate-code

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.auth_service import AuthService
from app.services.exchange_service import ExchangeRateError, ExchangeService

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
    async def fake_get_latest_rates(base: str, symbols: list[str]) -> dict:
        _ = (base, symbols)  # Avoid unused parameter warnings
        return {
            "base": base,
            "date": "2026-03-08",
            "rates": {"USD": 1.08, "CZK": 25.30, "JPY": 161.2},
        }

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = AuthService.create_access_token({"sub": "admin"})

    response = exchange_analytics_client.get(
        "/api/rates/analytics/extremes?base=EUR&symbols=USD&symbols=CZK&symbols=JPY",
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
    async def fake_get_latest_rates(base: str, symbols: list[str]) -> dict:
        _ = (base, symbols)  # Avoid unused parameter warnings
        return {"base": base, "date": "2026-03-08", "rates": {}}

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_analytics_client.get(
        "/api/rates/analytics/extremes?base=EUR&symbols=USD",
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
    async def fake_get_latest_rates(_base: str, _symbols: list[str]) -> dict:
        _ = (_base, _symbols)  # Avoid unused parameter warnings
        raise ExchangeRateError("Failed to retrieve current exchange rates")

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_analytics_client.get(
        "/api/rates/analytics/extremes?base=EUR&symbols=USD",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Failed to retrieve current exchange rates"}

def test_extremes_endpoint_requires_authentication(exchange_analytics_client: TestClient):
    response = exchange_analytics_client.get("/api/rates/analytics/extremes?base=EUR&symbols=USD")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

def test_average_endpoint_returns_averages_for_requested_symbols(
    exchange_analytics_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_historical_rates(
        base: str,
        start_date: str,
        end_date: str,
        symbols: list[str],
    ) -> dict:
        assert base == "EUR"
        assert start_date == "2026-03-01"
        assert end_date == "2026-03-03"
        assert symbols == ["USD", "CZK"]
        return {
            "rates": {
                "2026-03-01": {"USD": 1.10, "CZK": 25.20},
                "2026-03-02": {"USD": 1.20, "CZK": 25.40},
                "2026-03-03": {"USD": 1.00, "CZK": 25.00},
            }
        }

    monkeypatch.setattr(
        ExchangeService,
        "get_historical_rates",
        staticmethod(fake_get_historical_rates),
    )

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_analytics_client.get(
        "/api/rates/analytics/average"
        "?start_date=2026-03-01"
        "&end_date=2026-03-03"
        "&symbols=USD"
        "&symbols=CZK"
        "&base=EUR",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "base": "EUR",
        "period": {"start": "2026-03-01", "end": "2026-03-03"},
        "averages": {"USD": 1.1, "CZK": 25.2},
    }

def test_average_endpoint_sets_none_for_symbol_without_any_data(
    exchange_analytics_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_historical_rates(
        _base: str,
        _start_date: str,
        _end_date: str,
        _symbols: list[str],
    ) -> dict:
        _ = (_base, _start_date, _end_date, _symbols)  # Avoid unused parameter warnings
        return {
            "rates": {
                "2026-03-01": {"USD": 1.1},
                "2026-03-02": {"USD": 1.3},
            }
        }

    monkeypatch.setattr(
        ExchangeService,
        "get_historical_rates",
        staticmethod(fake_get_historical_rates),
    )

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_analytics_client.get(
        "/api/rates/analytics/average"
        "?start_date=2026-03-01"
        "&end_date=2026-03-02"
        "&symbols=USD"
        "&symbols=CZK",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["averages"] == {"USD": 1.2, "CZK": None}

def test_average_endpoint_returns_message_when_no_history(
    exchange_analytics_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_historical_rates(
        _base: str,
        _start_date: str,
        _end_date: str,
        _symbols: list[str],
    ) -> dict:
        _ = (_base, _start_date, _end_date, _symbols)  # Avoid unused parameter warnings
        return {"rates": {}}

    monkeypatch.setattr(
        ExchangeService,
        "get_historical_rates",
        staticmethod(fake_get_historical_rates),
    )

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_analytics_client.get(
        "/api/rates/analytics/average"
        "?start_date=2026-03-01"
        "&end_date=2026-03-02"
        "&symbols=USD",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "No data available for the specified period."}

def test_average_endpoint_returns_502_on_exchange_service_error(
    exchange_analytics_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_historical_rates(
        _base: str,
        _start_date: str,
        _end_date: str,
        _symbols: list[str],
    ) -> dict:
        raise ExchangeRateError("Failed to retrieve historical exchange rates")

    monkeypatch.setattr(
        ExchangeService,
        "get_historical_rates",
        staticmethod(fake_get_historical_rates),
    )

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_analytics_client.get(
        "/api/rates/analytics/average"
        "?start_date=2026-03-01"
        "&end_date=2026-03-02"
        "&symbols=USD",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Failed to retrieve historical exchange rates"}

def test_average_endpoint_requires_authentication(
    exchange_analytics_client: TestClient,
):
    response = exchange_analytics_client.get(
        "/api/rates/analytics/average"
        "?start_date=2026-03-01"
        "&end_date=2026-03-02"
        "&symbols=USD"
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
