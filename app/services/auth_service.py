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
        logger.debug("Starting token decoding and validation.")
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
            logger.trace("Token signature verified successfully.")
        except jwt.InvalidTokenError as exc:
            logger.error(f"Invalid token signature or format: {str(exc)}")
            raise credentials_exception from exc

        username_raw = payload.get("sub")
        token_type = payload.get("type")
        token_id = payload.get("jti")

        logger.debug(
            f"Extracted payload claims - sub: '{username_raw}', "
            f"type: '{token_type}', jti: '{token_id}'"
        )

        # Validate required claims
        if username_raw is None:
            logger.warning("Token validation failed: missing 'sub' claim")
            raise credentials_exception
        if token_type != TOKEN_TYPE_ACCESS:
            logger.warning(f"Token validation failed: invalid token type '{token_type}'")
            raise credentials_exception
        if not isinstance(token_id, str):
            logger.warning("Token validation failed: 'jti' claim is not a string")
            raise credentials_exception

        # Check revocation status
        if token_id in _revoked_token_ids:
            logger.warning(f"Token validation failed: token jti '{token_id}' has been revoked")
            raise credentials_exception

        username = str(username_raw)
        # Validate admin username matches
        if username != settings.admin_username:
            logger.warning(f"Token validation failed: username '{username}' is not the configured admin")
            raise credentials_exception

        logger.info(f"Token validated successfully for user: '{username}'")
        return payload

    @staticmethod
    def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        """Create a JWT access token with optional custom expiration (default 15 minutes)."""
        to_encode = data.copy()

        logger.debug(f"Creating access token for payload: {data}")

        # Calculate token expiration
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
            logger.trace(f"Using custom token expiration delta: {expires_delta}")
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=15)
            logger.trace("Using default token expiration delta (15 minutes).")

        token_id = str(uuid4())
        to_encode.update(
            {
                "exp": expire,
                "type": TOKEN_TYPE_ACCESS,
                "jti": token_id,
            }
        )

        encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=ALGORITHM)
        logger.info(f"Access token created successfully for subject: '{data.get('sub')}' (jti: {token_id})")
        return encoded_jwt

    @staticmethod
    async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
        """Validate token and return authenticated username."""
        logger.debug("Extracting current user from provided token.")
        payload = AuthService.decode_and_validate_token_payload(token)
        return str(payload["sub"])

    @staticmethod
    def revoke_token(token: str) -> None:
        """Revoke a valid access token by storing its unique token ID (jti) in-memory."""
        logger.debug("Attempting to revoke token.")
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
                logger.error(f"Failed to decode token for revocation: {str(exc)}")
                raise AuthService._credentials_exception() from exc

        jti = str(payload.get("jti", ""))
        if jti:
            _revoked_token_ids.add(jti)
            logger.info(f"Successfully revoked token jti '{jti}' for user: '{payload.get('sub')}'")
        else:
            logger.warning("Attempted to revoke a token without a valid 'jti' claim.")

    @staticmethod
    def clear_revoked_tokens() -> None:
        """Clear in-memory revoked token IDs for test isolation and reset operations."""
        cleared_count = len(_revoked_token_ids)
        _revoked_token_ids.clear()
        logger.warning(f"Revoked tokens cache cleared. Removed {cleared_count} records.")
