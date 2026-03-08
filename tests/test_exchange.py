import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token
from app.config import settings
from app.main import app
from app.services.exchange import ExchangeRateError, ExchangeService, rates_cache

@pytest.fixture(autouse=True)
def clear_exchange_cache():
    rates_cache.clear()

@pytest.fixture
def exchange_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "super-secret")
    monkeypatch.setattr(settings, "jwt_secret_key", "unit-test-secret-key-32-bytes-long")
    return TestClient(app)

def test_get_latest_rates_returns_cached_data_without_http_call(monkeypatch: pytest.MonkeyPatch):
    cached = {"base": "EUR", "date": "2026-03-08", "rates": {"CZK": 25.0}}
    rates_cache["latest_EUR"] = cached

    class ShouldNotBeCalledClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            raise AssertionError("HTTP client should not be called on cache hit")

    monkeypatch.setattr(httpx, "AsyncClient", ShouldNotBeCalledClient)

    data = asyncio.run(ExchangeService.get_latest_rates("EUR"))

    assert data == cached

def test_get_latest_rates_fetches_and_caches_data(monkeypatch: pytest.MonkeyPatch):
    expected = {"base": "USD", "date": "2026-03-08", "rates": {"EUR": 0.91}}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return expected

    class DummyAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str, timeout: float):
            assert "latest?base=USD" in url
            assert timeout == 5.0
            return DummyResponse()

    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)

    data = asyncio.run(ExchangeService.get_latest_rates("USD"))

    assert data == expected
    assert rates_cache["latest_USD"] == expected

def test_get_latest_rates_converts_http_error_to_domain_error(monkeypatch: pytest.MonkeyPatch):
    request = httpx.Request("GET", "https://example.test/latest?base=EUR")

    class FailingResponse:
        def raise_for_status(self):
            raise httpx.HTTPStatusError("bad status", request=request, response=httpx.Response(500, request=request))

        def json(self):
            return {}

    class DummyAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, *_args, **_kwargs):
            return FailingResponse()

    monkeypatch.setattr(httpx, "AsyncClient", DummyAsyncClient)

    with pytest.raises(ExchangeRateError, match="Failed to retrieve current exchange rates"):
        asyncio.run(ExchangeService.get_latest_rates("EUR"))

def test_latest_rates_endpoint_returns_data_for_authorized_user(exchange_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    async def fake_get_latest_rates(base: str) -> dict:
        return {"base": base, "date": "2026-03-08", "rates": {"CZK": 25.0}}

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = create_access_token({"sub": "admin"})
    response = exchange_client.get(
        "/api/rates/latest?base=EUR",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"base": "EUR", "date": "2026-03-08", "rates": {"CZK": 25.0}}

def test_latest_rates_endpoint_returns_502_on_exchange_service_error(
    exchange_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_latest_rates(_base: str) -> dict:
        raise ExchangeRateError("Failed to retrieve current exchange rates")

    monkeypatch.setattr(ExchangeService, "get_latest_rates", staticmethod(fake_get_latest_rates))

    token = create_access_token({"sub": "admin"})
    response = exchange_client.get(
        "/api/rates/latest?base=EUR",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Failed to retrieve current exchange rates"}
