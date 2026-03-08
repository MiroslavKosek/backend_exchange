"""Endpoint tests for auth token issuance."""

# Pylint may not resolve app imports from conftest path setup in test runs.
# Pytest fixture parameter names intentionally shadow fixture definitions.
# pylint: disable=import-error,missing-function-docstring,redefined-outer-name

from datetime import datetime, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.auth import ALGORITHM
from app.config import settings
from app.main import app

@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "super-secret")
    monkeypatch.setattr(settings, "jwt_secret_key", "unit-test-secret-key-32-bytes-long")
    return TestClient(app)

def test_token_endpoint_returns_bearer_token_for_valid_credentials(auth_client: TestClient):
    response = auth_client.post(
        "/token",
        data={"username": "admin", "password": "super-secret"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)

    payload = jwt.decode(body["access_token"], settings.jwt_secret_key, algorithms=[ALGORITHM])
    assert payload["sub"] == "admin"
    assert datetime.fromtimestamp(payload["exp"], tz=timezone.utc) > datetime.now(timezone.utc)

def test_token_endpoint_rejects_invalid_credentials(auth_client: TestClient):
    response = auth_client.post(
        "/token",
        data={"username": "admin", "password": "wrong-password"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"
    assert response.headers.get("www-authenticate") == "Bearer"

def test_token_endpoint_requires_form_fields(auth_client: TestClient):
    response = auth_client.post("/token", data={"username": "admin"})

    assert response.status_code == 422
