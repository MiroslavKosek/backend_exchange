"""Tests for exchange service behavior and latest rates endpoint."""

# Pylint in this setup may not resolve app imports from conftest path injection.
# For pytest tests, short helper functions/classes are intentionally compact.
# pylint: disable=import-error,missing-function-docstring,missing-class-docstring,redefined-outer-name

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.auth_service import AuthService
from app.services.exchange_service import ExchangeRateError, ExchangeService, rates_cache

@pytest.fixture(autouse=True)
def clear_exchange_cache():
    rates_cache.clear()

@pytest.fixture
def exchange_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "super-secret")
    monkeypatch.setattr(settings, "jwt_secret_key", "unit-test-secret-key-32-bytes-long")
    return TestClient(app)

@patch("httpx.AsyncClient.get")
def test_get_latest_rates_returns_cached_data_without_http_call(mock_get):
    # Setup cache for EUR base and CZK symbol
    cached = {"base": "EUR", "date": "2026-03-08", "rates": {"CZK": 25.0}}
    rates_cache["latest_EUR_CZK"] = cached

    data = asyncio.run(ExchangeService.get_latest_rates("EUR", ["CZK"]))

    assert data == cached
    mock_get.assert_not_called()

@patch("httpx.AsyncClient.get")
def test_get_latest_rates_fetches_and_caches_data(mock_get):
    expected = {"base": "USD", "date": "2026-03-08", "rates": {"EUR": 0.91}}

    # Use MagicMock here so .json() behaves as a normal synchronous method
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = expected
    mock_get.return_value = mock_response

    data = asyncio.run(ExchangeService.get_latest_rates("USD", ["EUR"]))

    assert data == expected
    assert rates_cache["latest_USD_EUR"] == expected
    mock_get.assert_called_once()
    assert "latest?base=USD&symbols=EUR" in mock_get.call_args[0][0]

@patch("httpx.AsyncClient.get")
def test_get_latest_rates_converts_http_error_to_domain_error(mock_get):
    request = httpx.Request("GET", "https://example.test/latest?base=EUR")

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad status",
        request=request,
        response=httpx.Response(500, request=request),
    )
    mock_get.return_value = mock_response

    with pytest.raises(ExchangeRateError, match="Failed to retrieve current exchange rates"):
        asyncio.run(ExchangeService.get_latest_rates("EUR", ["CZK"]))

@patch("httpx.AsyncClient.get")
def test_get_available_currencies_returns_cached_data_without_http_call(mock_get):
    cached = {"USD": "United States Dollar", "CZK": "Czech Koruna"}
    rates_cache["currencies"] = cached

    data = asyncio.run(ExchangeService.get_available_currencies())

    assert data == cached
    mock_get.assert_not_called()

@patch("httpx.AsyncClient.get")
def test_get_available_currencies_fetches_and_caches_data(mock_get):
    expected = {"AUD": "Australian Dollar", "CHF": "Swiss Franc"}

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = expected
    mock_get.return_value = mock_response

    data = asyncio.run(ExchangeService.get_available_currencies())

    assert data == expected
    assert rates_cache["currencies"] == expected

@patch("httpx.AsyncClient.get")
def test_get_available_currencies_converts_http_error_to_domain_error(mock_get):
    request = httpx.Request("GET", "https://example.test/currencies")

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad status",
        request=request,
        response=httpx.Response(500, request=request),
    )
    mock_get.return_value = mock_response

    with pytest.raises(ExchangeRateError, match="Failed to retrieve supported currencies"):
        asyncio.run(ExchangeService.get_available_currencies())

def test_latest_rates_endpoint_returns_data_for_authorized_user(
    exchange_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_latest_rates(base: str, symbols: list[str]) -> dict:
        _ = (base, symbols)  # Avoid unused parameter warnings
        return {"base": base, "date": "2026-03-08", "rates": {"CZK": 25.0}}

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_client.get(
        "/api/rates/latest?base=EUR&symbols=CZK",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"base": "EUR", "date": "2026-03-08", "rates": {"CZK": 25.0}}

def test_latest_rates_endpoint_returns_502_on_exchange_service_error(
    exchange_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_latest_rates(_base: str, _symbols: list[str]) -> dict:
        _ = (_base, _symbols)  # Avoid unused parameter warnings
        raise ExchangeRateError("Failed to retrieve current exchange rates")

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_client.get(
        "/api/rates/latest?base=EUR&symbols=CZK",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Failed to retrieve current exchange rates"}

def test_currencies_endpoint_returns_data_for_authorized_user(
    exchange_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_available_currencies() -> dict:
        return {"AUD": "Australian Dollar", "CAD": "Canadian Dollar"}

    monkeypatch.setattr(
        ExchangeService,
        "get_available_currencies",
        staticmethod(fake_get_available_currencies),
    )

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_client.get(
        "/api/rates/currencies",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "currencies": {"AUD": "Australian Dollar", "CAD": "Canadian Dollar"}
    }

def test_currencies_endpoint_returns_502_on_exchange_service_error(
    exchange_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_available_currencies() -> dict:
        raise ExchangeRateError("Failed to retrieve supported currencies")

    monkeypatch.setattr(
        ExchangeService,
        "get_available_currencies",
        staticmethod(fake_get_available_currencies),
    )

    token = AuthService.create_access_token({"sub": "admin"})
    response = exchange_client.get(
        "/api/rates/currencies",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Failed to retrieve supported currencies"}

def test_currencies_endpoint_requires_authentication(exchange_client: TestClient):
    response = exchange_client.get("/api/rates/currencies")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
