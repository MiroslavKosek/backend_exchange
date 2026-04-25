"""Unit tests for JWT token creation and current-user validation."""

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Pylint in some environments does not pick up test-time sys.path setup from conftest.
# pylint: disable=import-error
from app.config import settings
from app.main import app
from app.services.auth_service import (
    ALGORITHM,
    AuthService,
    _revoked_token_ids,
)

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


def test_create_access_token_uses_default_expiration():
    """Create an access token and verify default expiry and subject claims."""
    before = datetime.now(timezone.utc)
    token = AuthService.create_access_token({"sub": "admin"})
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    after = datetime.now(timezone.utc)

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    assert payload["sub"] == "admin"
    assert before + timedelta(minutes=14) <= exp <= after + timedelta(minutes=16)

def test_create_access_token_respects_custom_expiration():
    """Create an access token with custom expiry and assert it is honored."""
    custom_delta = timedelta(minutes=60)
    before = datetime.now(timezone.utc)
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=custom_delta)
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    after = datetime.now(timezone.utc)

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert before + timedelta(minutes=59) <= exp <= after + timedelta(minutes=61)

def test_create_access_token_with_negative_expiration_delta():
    """Allow negative expiry deltas and verify produced token is already expired."""
    negative_delta = timedelta(minutes=-5)
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=negative_delta)
    payload = jwt.decode(
        jwt=token,
        key=settings.jwt_secret_key,
        algorithms=[ALGORITHM],
        options={"verify_exp": False},
    )

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert exp < datetime.now(timezone.utc)

def test_create_access_token_generates_unique_jti_per_call():
    """Generate two tokens and confirm each has a distinct JTI claim."""
    token1 = AuthService.create_access_token({"sub": "admin"})
    token2 = AuthService.create_access_token({"sub": "admin"})

    payload1 = jwt.decode(token1, settings.jwt_secret_key, algorithms=[ALGORITHM])
    payload2 = jwt.decode(token2, settings.jwt_secret_key, algorithms=[ALGORITHM])

    assert payload1["jti"] != payload2["jti"]

def test_create_access_token_structure_has_required_claims():
    """Verify created access token contains all required standard claims."""
    token = AuthService.create_access_token({"sub": "admin", "custom": "data"})
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])

    assert all(claim in payload for claim in ("sub", "exp", "type", "jti"))
    assert payload["type"] == "access"


def test_get_current_user_returns_username_for_valid_token():
    """Return the username when get_current_user receives a valid access token."""
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=5))
    username = asyncio.run(AuthService.get_current_user(token))
    assert username == "admin"

def test_get_current_user_rejects_token_with_wrong_signature():
    """Reject tokens signed with an unexpected key as invalid credentials."""
    bad_token = jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "wrong-secret-key-32-bytes-long-test",
        algorithm=ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(bad_token))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"

@pytest.mark.parametrize(
    "payload_override, remove_key",
    [
        ({"sub": "other-user"}, None),               # Non-admin subject
        ({"type": "refresh"}, None),                 # Wrong type
        ({"jti": 12345}, None),                      # Non-string JTI
        (None, "sub"),                               # Missing sub
        (None, "jti"),                               # Missing JTI
        ({"exp": datetime.now(timezone.utc) - timedelta(minutes=5)}, None), # Expired
    ],
    ids=["wrong_sub", "wrong_type", "int_jti", "missing_sub", "missing_jti", "expired"]
)
def test_get_current_user_rejects_invalid_payloads(payload_override, remove_key):
    """Ensure token validation fails correctly for various malformed or invalid payloads."""
    payload = {
        "sub": "admin",
        "type": "access",
        "jti": "test-jti",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }

    if payload_override:
        payload.update(payload_override)
    if remove_key:
        del payload[remove_key]

    bad_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(bad_token))

    assert exc_info.value.status_code == 401


def test_revoke_token_adds_jti_to_revoked_list():
    """Revoke a token, record its JTI, and deny subsequent authentication."""
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])

    AuthService.revoke_token(token)
    assert payload["jti"] in _revoked_token_ids

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(token))
    assert exc_info.value.status_code == 401

def test_revoke_expired_token_succeeds():
    """Ensure we can revoke a token even if its expiration time has passed."""
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(seconds=-10))

    # Should not raise an exception, testing the fallback decode logic in revoke_token
    AuthService.revoke_token(token)

    payload = jwt.decode(
        token, settings.jwt_secret_key, algorithms=[ALGORITHM], options={"verify_exp": False}
    )
    assert payload["jti"] in _revoked_token_ids

def test_revoke_token_with_invalid_signature_raises_error():
    """Raise unauthorized error when attempting to revoke a tampered token."""
    bad_token = jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "wrong-secret-key",
        algorithm=ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc_info:
        AuthService.revoke_token(bad_token)
    assert exc_info.value.status_code == 401

def test_revoke_token_double_revocation_is_idempotent():
    """Support revoking the same token multiple times without failure."""
    token = AuthService.create_access_token({"sub": "admin"})

    AuthService.revoke_token(token)
    AuthService.revoke_token(token) # Second time should not crash

    with pytest.raises(HTTPException):
        asyncio.run(AuthService.get_current_user(token))
