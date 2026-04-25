"""Exchange service layer for external rates API access."""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from cachetools import TTLCache
from app.config import settings
from app.logger import logger

# Cache for exchange rates with a TTL of 15 minutes (900 seconds) and a maximum size of 100 entries
rates_cache = TTLCache(maxsize=100, ttl=900)


class ExchangeRateError(Exception):
    """Custom exception for exchange rate errors."""


class ExchangeService:
    """Service for retrieving and caching currency exchange data."""

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def get_latest_rates(base: str) -> dict:
        """FR1 - Getting current exchange rates."""
        cache_key = f"latest_{base}"

        # Check cache first
        if cache_key in rates_cache:
            logger.debug(f"Cache HIT for latest rates with base currency: '{base}'")
            return rates_cache[cache_key]

        logger.debug(f"Cache MISS for latest rates with base currency: '{base}'.")
        target_url = f"{settings.api_url}/latest?base={base}"
        logger.info(f"Fetching fresh data for '{base}' from external API: {target_url}")

        async with httpx.AsyncClient() as client:
            try:
                # Timeout set to 5 seconds to prevent hanging requests
                response = await client.get(target_url, timeout=5.0)
                response.raise_for_status()
                data = response.json()

                # Cache the result
                rates_cache[cache_key] = data
                logger.debug(
                    f"Successfully cached latest rates for '{base}'. "
                    f"Total keys in payload: {len(data.get('rates', {}))}"
                )
                return data
            except httpx.HTTPError as e:
                logger.error(f"HTTPError communicating with external API at {target_url}: {str(e)}")
                raise ExchangeRateError(
                    f"Failed to retrieve current exchange rates for base '{base}'"
                ) from e

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def get_available_currencies() -> dict:
        """Get supported currency symbols and full names."""
        cache_key = "currencies"

        if cache_key in rates_cache:
            logger.debug("Cache HIT for available currencies.")
            return rates_cache[cache_key]

        target_url = f"{settings.api_url}/currencies"
        logger.info(f"Cache MISS. Fetching supported currencies from external API: {target_url}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(target_url, timeout=5.0)
                response.raise_for_status()
                data = response.json()

                rates_cache[cache_key] = data
                logger.debug(f"Successfully cached available currencies. Total items: {len(data)}")
                return data
            except httpx.HTTPError as e:
                logger.error(f"HTTPError fetching available currencies from {target_url}: {str(e)}")
                raise ExchangeRateError("Failed to retrieve supported currencies") from e

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_historical_rates(
        base: str,
        start_date: str,
        end_date: str,
        symbols: list[str],
    ) -> dict:
        """Auxiliary method for FR4 - Obtaining history for a period."""
        symbols_str = ",".join(symbols)
        target_url = f"{settings.api_url}/{start_date}..{end_date}"
        target_url += f"?base={base}&symbols={symbols_str}"

        logger.info(f"Fetching historical rates for '{base}' from {start_date} to {end_date}.")
        logger.debug(f"Historical rates external API request: {target_url}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(target_url, timeout=5.0)
                response.raise_for_status()
                data = response.json()

                logger.debug(
                    "Successfully retrieved historical rates. "
                    f"Days fetched: {len(data.get('rates', {}))}"
                )
                return data
            except httpx.HTTPError as e:
                logger.error(f"HTTPError fetching historical data from {target_url}: {str(e)}")
                raise ExchangeRateError(
                    "Failed to retrieve historical exchange rates "
                    f"between {start_date} and {end_date}"
                ) from e
