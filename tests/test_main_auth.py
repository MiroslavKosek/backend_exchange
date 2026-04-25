"""Endpoint tests for auth token issuance."""

# Pylint may not resolve app imports from conftest path setup in test runs.
# Pytest fixture parameter names intentionally shadow fixture definitions.
# pylint: disable=import-error,missing-function-docstring,redefined-outer-name

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply stable auth settings automatically to all tests for determinism."""
    monkeypatch.setattr(settings, "jwt_secret_key", "unit-test-secret-key-32-bytes-long")
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "super-secret")

@pytest.fixture
def auth_client() -> TestClient:
    """Provide a TestClient for endpoint testing."""
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

def test_token_endpoint_rejects_invalid_credentials(auth_client: TestClient):
    response = auth_client.post(
        "/token",
        data={"username": "admin", "password": "wrong-password"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"

def test_renew_endpoint_returns_new_token_for_valid_bearer(auth_client: TestClient):
    login_response = auth_client.post(
        "/token",
        data={"username": "admin", "password": "super-secret"},
    )
    old_token = login_response.json()["access_token"]

    renew_response = auth_client.post(
        "/token/renew",
        headers={"Authorization": f"Bearer {old_token}"},
    )

    assert renew_response.status_code == 200
    assert renew_response.json()["access_token"] != old_token

def test_renew_endpoint_rejects_previously_revoked_token(auth_client: TestClient):
    login_response = auth_client.post(
        "/token",
        data={"username": "admin", "password": "super-secret"},
    )
    token = login_response.json()["access_token"]

    auth_client.post("/token/renew", headers={"Authorization": f"Bearer {token}"})
    second_renew = auth_client.post("/token/renew", headers={"Authorization": f"Bearer {token}"})

    assert second_renew.status_code == 401

def test_logout_revokes_token_and_blocks_reuse(auth_client: TestClient):
    login_response = auth_client.post(
        "/token",
        data={"username": "admin", "password": "super-secret"},
    )
    token = login_response.json()["access_token"]

    logout_response = auth_client.post("/logout", headers={"Authorization": f"Bearer {token}"})
    reuse_response = auth_client.get(
        "/api/rates/currencies", headers={"Authorization": f"Bearer {token}"}
    )

    assert logout_response.status_code == 200
    assert reuse_response.status_code == 401
