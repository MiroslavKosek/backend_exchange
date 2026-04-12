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
    if (
        form_data.username != settings.admin_username
        or form_data.password != settings.admin_password
    ):
        logger.warning(f"Failed login attempt for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = AuthService.create_access_token(
        data={"sub": form_data.username},
        expires_delta=access_token_expires,
    )

    logger.info(f"User {form_data.username} logged in successfully.")
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/token/renew")
async def renew_token(
    token: str = Depends(oauth2_scheme),
    current_user: str = Depends(AuthService.get_current_user),
):
    """Revoke current token and issue a new access token for the same user."""
    AuthService.revoke_token(token)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = AuthService.create_access_token(
        data={"sub": current_user},
        expires_delta=access_token_expires,
    )
    logger.info(f"User {current_user} renewed access token.")
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    current_user: str = Depends(AuthService.get_current_user),
):
    """Revoke current token to effectively log the user out."""
    AuthService.revoke_token(token)
    logger.info(f"User {current_user} logged out.")
    return {"message": "Logged out successfully"}
