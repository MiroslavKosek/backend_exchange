"""Exchange-rate API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.auth_service import AuthService
from app.services.exchange_service import ExchangeRateError, ExchangeService
from app.logger import logger

router = APIRouter(prefix="/api/rates", tags=["Exchange Rates"])


@router.get("/currencies")
async def get_available_currencies(
    _current_user: str = Depends(AuthService.get_current_user),
):
    """Get supported currency symbols and their full names."""
    logger.info("Fetching available currencies.")
    try:
        currencies = await ExchangeService.get_available_currencies()
        logger.debug(f"Successfully retrieved {len(currencies)} currencies.")
        return {"currencies": currencies}
    except ExchangeRateError as e:
        logger.error(f"Failed to fetch currencies: {str(e)}")
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/latest")
async def get_current_rates(
    base: str = Query("EUR", description="Base currency (e.g., EUR, CZK)"),
    _current_user: str = Depends(AuthService.get_current_user),
):
    """FR1: Get current exchange rates."""
    logger.info(f"Fetching latest rates for base currency: '{base}'")
    try:
        data = await ExchangeService.get_latest_rates(base)
        logger.debug(f"Retrieved latest rates for '{base}' dated {data['date']}.")
        return {"base": data["base"], "date": data["date"], "rates": data["rates"]}
    except ExchangeRateError as e:
        logger.error(f"ExchangeService error while fetching latest rates for '{base}': {str(e)}")
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/analytics/extremes")
async def get_strongest_and_weakest_rates(
    base: str = Query("EUR", description="Base currency (e.g., EUR, CZK)"),
    _current_user: str = Depends(AuthService.get_current_user),
):
    """FR2/FR3: Return the strongest and weakest currency for a base."""
    logger.info(f"Calculating strongest and weakest currencies against base: '{base}'")
    try:
        logger.debug("Requesting latest rates for extreme calculation.")
        data = await ExchangeService.get_latest_rates(base)
        rates = data.get("rates", {})

        if not rates:
            logger.warning(f"No exchange rates returned for base '{base}'. Cannot calculate extremes.")
            raise HTTPException(
                status_code=404,
                detail="No exchange rates available for the specified base currency.",
            )

        logger.trace("Calculating max and min rates from the payload.")
        strongest_currency = max(rates.items(), key=lambda x: x[1])
        weakest_currency = min(rates.items(), key=lambda x: x[1])

        logger.debug(
            f"Extremes calculated. Strongest: {strongest_currency[0]} ({strongest_currency[1]}), "
            f"Weakest: {weakest_currency[0]} ({weakest_currency[1]})"
        )
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
        logger.error(f"Failed to calculate extremes for base '{base}': {str(e)}")
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/analytics/average")
async def get_average_rates(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    symbols: list[str] = Query(
        ..., description="List of currencies for averaging (e.g., USD, CZK)"
    ),
    base: str = Query("EUR", description="Base currency (e.g., EUR, CZK)"),
    _current_user: str = Depends(AuthService.get_current_user),
):
    """FR4: Calculate average exchange rates for selected symbols and period."""
    logger.info(
        f"Calculating average rates from {start_date} to {end_date} for base '{base}'. "
        f"Target symbols: {symbols}"
    )
    try:
        logger.debug("Fetching historical rates from ExchangeService.")
        data = await ExchangeService.get_historical_rates(
            base,
            start_date,
            end_date,
            symbols,
        )
        rates_history = data.get("rates", {})

        if not rates_history:
            logger.warning(f"No historical data found between {start_date} and {end_date}.")
            return {"message": "No data available for the specified period."}

        logger.trace(f"Iterating over {len(rates_history)} days of historical data.")
        sums = {symbol: 0.0 for symbol in symbols}
        counts = {symbol: 0 for symbol in symbols}

        for _date, daily_rates in rates_history.items():
            for symbol in symbols:
                if symbol in daily_rates:
                    sums[symbol] += daily_rates[symbol]
                    counts[symbol] += 1
                    logger.trace(f"Accumulated {symbol} for date {_date}")

        averages = {}
        for symbol in symbols:
            if counts[symbol] > 0:
                averages[symbol] = round(sums[symbol] / counts[symbol], 4)
            else:
                logger.warning(f"Symbol '{symbol}' was not found in any of the daily rates.")
                averages[symbol] = None

        logger.debug(f"Averages calculation complete: {averages}")
        return {
            "base": base,
            "period": {"start": start_date, "end": end_date},
            "averages": averages,
        }
    except ExchangeRateError as e:
        logger.error(f"Failed to calculate historical averages: {str(e)}")
        raise HTTPException(status_code=502, detail=str(e)) from e
