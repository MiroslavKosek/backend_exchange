"""Exchange-rate API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.services.exchange import ExchangeRateError, ExchangeService

router = APIRouter(prefix="/api/rates", tags=["Exchange Rates"])


@router.get("/latest")
async def get_current_rates(
    base: str = Query("EUR", description="Base currency (e.g., EUR, CZK)"),
    _current_user: str = Depends(get_current_user),
):
    """FR1: Get current exchange rates."""
    try:
        data = await ExchangeService.get_latest_rates(base)
        return {"base": data["base"], "date": data["date"], "rates": data["rates"]}
    except ExchangeRateError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/analytics/extremes")
async def get_strongest_and_weakest_rates(
    base: str = Query("EUR", description="Base currency (e.g., EUR, CZK)"),
    _current_user: str = Depends(get_current_user),
):
    """FR2/FR3: Return the strongest and weakest currency for a base."""
    try:
        data = await ExchangeService.get_latest_rates(base)
        rates = data.get("rates", {})

        if not rates:
            raise HTTPException(
                status_code=404,
                detail="No exchange rates available for the specified base currency.",
            )

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


@router.get("/analytics/average")
async def get_average_rates(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    symbols: list[str] = Query(
        ..., description="List of currencies for averaging (e.g., USD, CZK)"
    ),
    base: str = Query("EUR", description="Base currency (e.g., EUR, CZK)"),
    _current_user: str = Depends(get_current_user),
):
    """FR4: Calculate average exchange rates for selected symbols and period."""
    try:
        data = await ExchangeService.get_historical_rates(
            base,
            start_date,
            end_date,
            symbols,
        )
        rates_history = data.get("rates", {})

        if not rates_history:
            return {"message": "No data available for the specified period."}

        sums = {symbol: 0.0 for symbol in symbols}
        counts = {symbol: 0 for symbol in symbols}

        for _date, daily_rates in rates_history.items():
            for symbol in symbols:
                if symbol in daily_rates:
                    sums[symbol] += daily_rates[symbol]
                    counts[symbol] += 1

        averages = {}
        for symbol in symbols:
            if counts[symbol] > 0:
                averages[symbol] = round(sums[symbol] / counts[symbol], 4)
            else:
                averages[symbol] = None

        return {
            "base": base,
            "period": {"start": start_date, "end": end_date},
            "averages": averages,
        }
    except ExchangeRateError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
