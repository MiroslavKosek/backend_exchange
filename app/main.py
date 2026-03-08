"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from datetime import timedelta
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
)
from app.config import settings
from app.logger import logger, reset_request_id, set_request_id
from app.services.exchange import ExchangeService, ExchangeRateError

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Log startup and shutdown lifecycle events."""
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
    lifespan=lifespan,
)

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Attach request id to logs and response headers for traceability."""
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
    """Return a simple welcome message and docs hint."""
    logger.info("User visited the root endpoint.")
    return {
        "message": (
            "Welcome to the Exchange Rate API Backend. "
            "Documentation is available at /docs"
        )
    }

@app.get("/health")
async def health_check():
    """Healthcheck endpoint used by monitors and orchestrators."""
    return {"status": "ok"}

@app.post("/token", tags=["Auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    This endpoint handles user login and token generation.
    It validates the provided username and password.
    If the credentials are valid, it generates a JWT access token
    and returns it to the client.
    If the credentials are invalid, it raises
    an HTTP 401 Unauthorized exception.
    """
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
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )

    logger.info(f"User {form_data.username} logged in successfully.")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/rates/latest", tags=["Exchange Rates"])
async def get_current_rates(
    base: str = Query("EUR", description="Base currency (e.g., EUR, CZK)"),
    _current_user: str = Depends(get_current_user),
):
    """
    FR1: Getting current exchange rates.
    """
    try:
        data = await ExchangeService.get_latest_rates(base)
        return {"base": data["base"], "date": data["date"], "rates": data["rates"]}
    except ExchangeRateError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

@app.get("/api/rates/analytics/extremes", tags=["Exchange Rates"])
async def get_strongest_and_weakest(
    base: str = Query("EUR", description="Base currency (e.g., EUR, CZK)"),
    _current_user: str = Depends(get_current_user),
):
    """
    FR2 & FR3: Getting the strongest and weakest currency
    compared to the base currency.
    """
    try:
        data = await ExchangeService.get_latest_rates(base)
        rates = data.get("rates", {})

        if not rates:
            raise HTTPException(
                status_code=404,
                detail="No exchange rates available for the specified base currency."
            )

        # Find the strongest and weakest currency based on the exchange rates
        strongest_currency = max(rates.items(), key=lambda x: x[1])
        weakest_currency = min(rates.items(), key=lambda x: x[1])

        return {
            "base": base,
            "date": data["date"],
            "strongest": {
                "currency": strongest_currency[0],
                "value": strongest_currency[1],
            },
            "weakest": {
                "currency": weakest_currency[0],
                "value": weakest_currency[1],
            },
        }
    except ExchangeRateError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

@app.get("/api/rates/analytics/average", tags=["Exchange Rates"])
async def get_average_rates(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    symbols: list[str] = Query(
        ..., description="List of currencies for averaging (e.g., USD, CZK)"
    ),
    base: str = Query("EUR", description="Base currency (e.g., EUR, CZK)"),
    _current_user: str = Depends(get_current_user),
):
    """
    FR4: Average of selected currencies for a defined period.
    Calculates the arithmetic mean from available daily values
    (ignores days without data, e.g., weekends).
    """
    try:
        data = await ExchangeService.get_historical_rates(base, start_date, end_date, symbols)
        rates_history = data.get("rates", {})

        if not rates_history:
            return {"message": "No data available for the specified period."}

        # Initialization of structures for sums and counts of days
        sums = {symbol: 0.0 for symbol in symbols}
        counts = {symbol: 0 for symbol in symbols}

        # Browsing history and counting (solves the problem of missing data on certain days)
        for _date, daily_rates in rates_history.items():
            for symbol in symbols:
                if symbol in daily_rates:
                    sums[symbol] += daily_rates[symbol]
                    counts[symbol] += 1

        # Calculation of the average
        averages = {}
        for symbol in symbols:
            if counts[symbol] > 0:
                averages[symbol] = round(sums[symbol] / counts[symbol], 4)
            else:
                # No data available for this currency in the specified period.
                averages[symbol] = None

        return {
            "base": base,
            "period": {"start": start_date, "end": end_date},
            "averages": averages
        }
    except ExchangeRateError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
