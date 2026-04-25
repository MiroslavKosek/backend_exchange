"""Authentication API endpoints."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.services.auth_service import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    AuthService,
    oauth2_scheme,
)
from app.config import settings
from app.logger import logger

router = APIRouter(tags=["Auth"])


@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Validate credentials and issue a bearer JWT token."""
    logger.info(f"Login attempt initiated for username: '{form_data.username}'")

    logger.debug("Validating user credentials against application settings.")
    if (
        form_data.username != settings.admin_username
        or form_data.password != settings.admin_password
    ):
        logger.warning(
            f"Failed login attempt for username: '{form_data.username}' - Invalid credentials."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug("Credentials validated. Generating JWT access token.")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = AuthService.create_access_token(
        data={"sub": form_data.username},
        expires_delta=access_token_expires,
    )

    logger.info(f"User '{form_data.username}' logged in successfully.")
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/token/renew")
async def renew_token(
    token: str = Depends(oauth2_scheme),
    current_user: str = Depends(AuthService.get_current_user),
):
    """Revoke current token and issue a new access token for the same user."""
    logger.info(f"Token renewal initiated for user: '{current_user}'")
    logger.debug("Revoking current token.")

    AuthService.revoke_token(token)

    logger.debug("Generating new access token.")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = AuthService.create_access_token(
        data={"sub": current_user},
        expires_delta=access_token_expires,
    )

    logger.info(f"User '{current_user}' successfully renewed access token.")
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    current_user: str = Depends(AuthService.get_current_user),
):
    """Revoke current token to effectively log the user out."""
    logger.info(f"Logout initiated for user: '{current_user}'")
    AuthService.revoke_token(token)
    logger.info(f"User '{current_user}' logged out successfully. Token revoked.")
    return {"message": "Logged out successfully"}
