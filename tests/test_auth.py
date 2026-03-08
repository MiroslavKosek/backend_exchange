import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.auth import ALGORITHM, create_access_token, get_current_user
from app.config import settings

def _set_test_auth_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret_key", "unit-test-secret-key-32-bytes-long")
    monkeypatch.setattr(settings, "admin_username", "admin")

def test_create_access_token_uses_default_expiration(monkeypatch: pytest.MonkeyPatch):
    _set_test_auth_settings(monkeypatch)

    before = datetime.now(timezone.utc)
    token = create_access_token({"sub": "admin"})
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    after = datetime.now(timezone.utc)

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    assert payload["sub"] == "admin"
    assert before + timedelta(minutes=14) <= exp <= after + timedelta(minutes=16)

def test_create_access_token_respects_custom_expiration(monkeypatch: pytest.MonkeyPatch):
    _set_test_auth_settings(monkeypatch)

    custom_delta = timedelta(minutes=60)
    before = datetime.now(timezone.utc)
    token = create_access_token({"sub": "admin"}, expires_delta=custom_delta)
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    after = datetime.now(timezone.utc)

    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

    assert before + timedelta(minutes=59) <= exp <= after + timedelta(minutes=61)

def test_get_current_user_returns_username_for_valid_token(monkeypatch: pytest.MonkeyPatch):
    _set_test_auth_settings(monkeypatch)

    token = create_access_token({"sub": "admin"}, expires_delta=timedelta(minutes=5))
    username = asyncio.run(get_current_user(token))

    assert username == "admin"

def test_get_current_user_rejects_token_with_wrong_signature(monkeypatch: pytest.MonkeyPatch):
    _set_test_auth_settings(monkeypatch)

    bad_token = jwt.encode(
        {"sub": "admin", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "wrong-secret-key-32-bytes-long-test",
        algorithm=ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(bad_token))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"

def test_get_current_user_rejects_non_admin_subject(monkeypatch: pytest.MonkeyPatch):
    _set_test_auth_settings(monkeypatch)

    token = create_access_token({"sub": "other-user"}, expires_delta=timedelta(minutes=5))

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(token))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"
