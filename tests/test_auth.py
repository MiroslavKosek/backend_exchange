"""Unit tests for JWT token creation and current-user validation."""

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

# Pylint in some environments does not pick up test-time sys.path setup from conftest.
# pylint: disable=import-error
from app.config import settings
from app.services.auth_service import (
    ALGORITHM,
    AuthService,
    _revoked_token_ids,
)


def _set_test_auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply stable auth settings for deterministic unit tests."""
    monkeypatch.setattr(settings, "jwt_secret_key", "unit-test-secret-key-32-bytes-long")
    monkeypatch.setattr(settings, "admin_username", "admin")


def test_create_access_token_uses_default_expiration(monkeypatch: pytest.MonkeyPatch):
    """Token created without custom delta should use the default short expiry."""
    _set_test_auth_settings(monkeypatch)

    before = datetime.now(timezone.utc)
    token = AuthService.create_access_token({"sub": "admin"})
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    after = datetime.now(timezone.utc)

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    assert payload["sub"] == "admin"
    assert before + timedelta(minutes=14) <= exp <= after + timedelta(minutes=16)


def test_create_access_token_respects_custom_expiration(monkeypatch: pytest.MonkeyPatch):
    """Token should respect explicitly supplied expiration delta."""
    _set_test_auth_settings(monkeypatch)

    custom_delta = timedelta(minutes=60)
    before = datetime.now(timezone.utc)
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=custom_delta)
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    after = datetime.now(timezone.utc)

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    assert before + timedelta(minutes=59) <= exp <= after + timedelta(minutes=61)


def test_create_access_token_with_negative_expiration_delta(monkeypatch: pytest.MonkeyPatch):
    """Token with negative delta should have expiration in the past (immediately expired)."""
    _set_test_auth_settings(monkeypatch)

    negative_delta = timedelta(minutes=-5)
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=negative_delta)
    payload = jwt.decode(
        jwt=token,
        key=settings.jwt_secret_key,
        algorithms=[ALGORITHM],
        options={"verify_exp": False},
    )

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    now = datetime.now(timezone.utc)

    # Token should be expired
    assert exp < now


def test_create_access_token_with_far_future_expiration(monkeypatch: pytest.MonkeyPatch):
    """Token with large delta should have far-future expiration."""
    _set_test_auth_settings(monkeypatch)

    far_future_delta = timedelta(days=365)
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=far_future_delta)
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    now = datetime.now(timezone.utc)

    # Token should be expired in approximately 365 days
    assert (exp - now).days >= 364


def test_create_access_token_generates_unique_jti_per_call(monkeypatch: pytest.MonkeyPatch):
    """Each call to create_access_token should generate a unique jti."""
    _set_test_auth_settings(monkeypatch)

    token1 = AuthService.create_access_token({"sub": "admin"})
    token2 = AuthService.create_access_token({"sub": "admin"})

    payload1 = jwt.decode(token1, settings.jwt_secret_key, algorithms=[ALGORITHM])
    payload2 = jwt.decode(token2, settings.jwt_secret_key, algorithms=[ALGORITHM])

    # JTI values should be different
    assert payload1["jti"] != payload2["jti"]


def test_create_access_token_structure_has_required_claims(monkeypatch: pytest.MonkeyPatch):
    """Token should have all required claims: sub, exp, type, jti."""
    _set_test_auth_settings(monkeypatch)

    token = AuthService.create_access_token({"sub": "admin", "custom": "data"})
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])

    assert "sub" in payload
    assert "exp" in payload
    assert "type" in payload
    assert "jti" in payload
    assert payload["type"] == "access"
    assert payload["sub"] == "admin"


def test_get_current_user_returns_username_for_valid_token(monkeypatch: pytest.MonkeyPatch):
    """Valid token with admin subject should resolve to current username."""
    _set_test_auth_settings(monkeypatch)

    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=5))
    username = asyncio.run(AuthService.get_current_user(token))

    assert username == "admin"


def test_get_current_user_rejects_token_with_wrong_signature(monkeypatch: pytest.MonkeyPatch):
    """Invalid token signature must raise unauthorized credentials error."""
    _set_test_auth_settings(monkeypatch)

    bad_token = jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "wrong-secret-key-32-bytes-long-test",
        algorithm=ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(bad_token))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"


def test_get_current_user_rejects_non_admin_subject(monkeypatch: pytest.MonkeyPatch):
    """Non-admin subject should be rejected by current-user validator."""
    _set_test_auth_settings(monkeypatch)

    token = AuthService.create_access_token(
        {"sub": "other-user"},
        expires_delta=timedelta(minutes=5),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(token))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"


def test_get_current_user_rejects_expired_token(monkeypatch: pytest.MonkeyPatch):
    """Expired token should be rejected with 401 unauthorized."""
    _set_test_auth_settings(monkeypatch)

    # Create token that's already expired
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(seconds=-10))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(token))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"


def test_get_current_user_rejects_token_with_missing_jti(monkeypatch: pytest.MonkeyPatch):
    """Token without jti claim should be rejected."""
    _set_test_auth_settings(monkeypatch)

    # Manually craft token without jti
    payload = {
        "sub": "admin",
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        # Missing "jti"
    }
    bad_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(bad_token))

    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_token_with_wrong_type(monkeypatch: pytest.MonkeyPatch):
    """Token with wrong type should be rejected."""
    _set_test_auth_settings(monkeypatch)

    # Manually craft token with wrong type
    payload = {
        "sub": "admin",
        "type": "refresh",  # Wrong type
        "jti": "test-jti",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    bad_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(bad_token))

    assert exc_info.value.status_code == 401


def test_revoke_token_adds_jti_to_revoked_list(monkeypatch: pytest.MonkeyPatch):
    """Revoking a token should store its jti in the revoked set."""
    _set_test_auth_settings(monkeypatch)

    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    jti = payload["jti"]

    # Token should initially work
    username = asyncio.run(AuthService.get_current_user(token))
    assert username == "admin"

    # Revoke the token
    AuthService.revoke_token(token)
    assert jti in _revoked_token_ids

    # Token should now be rejected
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(token))

    assert exc_info.value.status_code == 401


def test_revoke_token_with_invalid_token_raises_error(monkeypatch: pytest.MonkeyPatch):
    """Revoking an invalid token should raise HTTPException."""
    _set_test_auth_settings(monkeypatch)

    bad_token = jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "wrong-secret-key-32-bytes-long-test",
        algorithm=ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        AuthService.revoke_token(bad_token)

    assert exc_info.value.status_code == 401


def test_revoke_token_double_revocation_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    """Revoking a token twice should not cause errors (idempotent)."""
    _set_test_auth_settings(monkeypatch)

    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=5))

    # Revoke twice - should not raise exception
    AuthService.revoke_token(token)
    AuthService.revoke_token(token)

    # Token should still be rejected
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(token))

    assert exc_info.value.status_code == 401


def test_auth_service_class_backward_compatibility(monkeypatch: pytest.MonkeyPatch):
    """AuthService class methods should behave consistently across calls."""
    _set_test_auth_settings(monkeypatch)

    # First class-method call
    token1 = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=5))
    username1 = asyncio.run(AuthService.get_current_user(token1))

    # Second class-method call
    token2 = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=5))
    username2 = asyncio.run(AuthService.get_current_user(token2))

    # Both should work the same way
    assert username1 == "admin"
    assert username2 == "admin"


def test_end_to_end_auth_flow(monkeypatch: pytest.MonkeyPatch):
    """End-to-end flow: create token → validate → revoke → reject."""
    _set_test_auth_settings(monkeypatch)

    # 1. Create token
    token = AuthService.create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=5))

    # 2. Validate token works
    username = asyncio.run(AuthService.get_current_user(token))
    assert username == "admin"

    # 3. Revoke token
    AuthService.revoke_token(token)

    # 4. Validate token is rejected
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(AuthService.get_current_user(token))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"
