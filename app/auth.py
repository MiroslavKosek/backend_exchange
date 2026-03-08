"""JWT authentication helpers for FastAPI endpoints."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
TOKEN_TYPE_ACCESS = "access"

_revoked_token_ids: set[str] = set()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def _credentials_exception() -> HTTPException:
    """Create the shared unauthorized exception for credential failures."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_and_validate_token_payload(token: str) -> dict:
    """Decode JWT payload and validate token type, subject and revocation state."""
    credentials_exception = _credentials_exception()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise credentials_exception from exc

    username_raw = payload.get("sub")
    token_type = payload.get("type")
    token_id = payload.get("jti")

    if username_raw is None:
        raise credentials_exception
    if token_type != TOKEN_TYPE_ACCESS:
        raise credentials_exception
    if not isinstance(token_id, str):
        raise credentials_exception
    if token_id in _revoked_token_ids:
        raise credentials_exception

    username = str(username_raw)
    if username != settings.admin_username:
        raise credentials_exception

    return payload


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """
    This function creates a JWT access token.
    It takes a dictionary of data to encode in the token and an optional expiration time.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)

    to_encode.update(
        {
            "exp": expire,
            "type": TOKEN_TYPE_ACCESS,
            "jti": str(uuid4()),
        }
    )

    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    This function decodes the JWT token and validates it.
    It checks if the token is valid and if the username in the token
    matches the hardcoded admin username.
    If the token is invalid or the username does not match,
    it raises an HTTP 401 Unauthorized exception.
    """
    payload = _decode_and_validate_token_payload(token)
    return str(payload["sub"])


def revoke_token(token: str) -> None:
    """Revoke a valid access token by storing its unique token id (jti)."""
    payload = _decode_and_validate_token_payload(token)
    _revoked_token_ids.add(str(payload["jti"]))
