from fastapi.security import OAuth2PasswordRequestForm
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi import Request
from contextlib import asynccontextmanager

from datetime import timedelta
from time import perf_counter
from uuid import uuid4

from app.logger import logger, reset_request_id, set_request_id
from app.config import settings
from app.auth import (
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application starting...")
    logger.info(f"Connecting to API: {settings.api_url}")
    yield
    # Shutdown
    logger.info("Application shutting down...")

app = FastAPI(
    title="Exchange Rate API Backend",
    description="Semestral project - Backend for exchange rate application",
    version="1.0.0",
    lifespan=lifespan
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    start = perf_counter()
    token = set_request_id(request_id)
    try:
        with logger.contextualize(request_id=request_id):
            response = await call_next(request)
            duration_ms = (perf_counter() - start) * 1000
            logger.info(
                f'{request.client.host if request.client else "-"} '
                f'- "{request.method} {request.url.path}" {response.status_code} '
                f'({duration_ms:.2f} ms)'
            )
    finally:
        reset_request_id(token)
    response.headers["X-Request-ID"] = request_id
    return response

@app.get("/")
async def root():
    logger.info("User visited the root endpoint.")
    return {"message": "Welcome to the Exchange Rate API Backend. Documentation is available at /docs"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/token", tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    This endpoint handles user login and token generation.
    It validates the provided username and password.
    If the credentials are valid, it generates a JWT access token and returns it to the client.
    If the credentials are invalid, it raises an HTTP 401 Unauthorized exception.
    """
    if form_data.username != settings.admin_username or form_data.password != settings.admin_password:
        logger.warning(f"Failed login attempt for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )

    logger.info(f"User {form_data.username} logged in successfully.")
    return {"access_token": access_token, "token_type": "bearer"}
