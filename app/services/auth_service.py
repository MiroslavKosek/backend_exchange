"""Authentication service layer."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import settings
from app.logger import logger

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
TOKEN_TYPE_ACCESS = "access"

# In-memory set of revoked token IDs (cleared on server restart)
_revoked_token_ids: set[str] = set()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class AuthenticationError(Exception):
    """Custom exception for authentication errors."""


class AuthService:
    """JWT token lifecycle management (create, validate, revoke) with HS256 signing."""

    @staticmethod
    def _credentials_exception() -> HTTPException:
        """Create the shared unauthorized exception for credential failures."""
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @staticmethod
    def decode_and_validate_token_payload(token: str) -> dict[str, Any]:
        """Decode JWT payload and validate token type, subject, and revocation state."""
        credentials_exception = AuthService._credentials_exception()
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        except jwt.InvalidTokenError as exc:
            logger.error(f"Invalid token signature or format: {str(exc)}")
            raise credentials_exception from exc

        username_raw = payload.get("sub")
        token_type = payload.get("type")
        token_id = payload.get("jti")

        # Validate required claims
        if username_raw is None:
            logger.error("Token validation failed: missing 'sub' claim")
            raise credentials_exception
        if token_type != TOKEN_TYPE_ACCESS:
            logger.error(f"Token validation failed: invalid token type '{token_type}'")
            raise credentials_exception
        if not isinstance(token_id, str):
            logger.error("Token validation failed: 'jti' claim is not a string")
            raise credentials_exception

        # Check revocation status
        if token_id in _revoked_token_ids:
            logger.warning(f"Token validation failed: token {token_id[:8]}... has been revoked")
            raise credentials_exception

        username = str(username_raw)
        # Validate admin username matches
        if username != settings.admin_username:
            logger.warning(f"Token validation failed: username '{username}' is not admin")
            raise credentials_exception

        logger.info(f"Token validated successfully for user: {username}")
        return payload

    @staticmethod
    def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        """Create a JWT access token with optional custom expiration (default 15 minutes)."""
        to_encode = data.copy()

        # Calculate token expiration
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
        logger.info(f"Access token created for subject: {data.get('sub')}")
        return encoded_jwt

    @staticmethod
    async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
        """Validate token and return authenticated username."""
        payload = AuthService.decode_and_validate_token_payload(token)
        return str(payload["sub"])

    @staticmethod
    def revoke_token(token: str) -> None:
        """Revoke a valid access token by storing its unique token ID (jti) in-memory."""
        try:
            # Try to decode and validate the token
            payload = AuthService.decode_and_validate_token_payload(token)
        except HTTPException:
            try:
                payload = jwt.decode(
                    token,
                    settings.jwt_secret_key,
                    algorithms=[ALGORITHM],
                    options={"verify_exp": False},
                )
            except jwt.InvalidTokenError as exc:
                raise AuthService._credentials_exception() from exc

        jti = str(payload.get("jti", ""))
        if jti:
            _revoked_token_ids.add(jti)
            logger.info(f"Token revoked for user: {payload.get('sub')}")

    @staticmethod
    def clear_revoked_tokens() -> None:
        """Clear in-memory revoked token IDs for test isolation and reset operations."""
        _revoked_token_ids.clear()
