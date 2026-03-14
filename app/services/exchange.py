import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from cachetools import TTLCache
from app.config import settings
from app.logger import logger

# Cache for exchange rates with a TTL of 15 minutes (900 seconds) and a maximum size of 100 entries
rates_cache = TTLCache(maxsize=100, ttl=900)

class ExchangeRateError(Exception):
    """Custom exception for exchange rate errors."""
    pass

class ExchangeService:
    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True
    )
    async def get_latest_rates(base: str) -> dict:
        """FR1 - Getting current exchange rates."""
        cache_key = f"latest_{base}"
        
        # Check cache first
        if cache_key in rates_cache:
            logger.info(f"Retrieving data from cache for base currency: {base}")
            return rates_cache[cache_key]

        logger.info(f"Fetching fresh data for {base} from {settings.api_url}")
        async with httpx.AsyncClient() as client:
            try:
                # Timeout set to 5 seconds to prevent hanging requests
                response = await client.get(f"{settings.api_url}/latest?base={base}", timeout=5.0)
                response.raise_for_status()
                data = response.json()
                
                # Cache the result
                rates_cache[cache_key] = data
                return data
            except httpx.HTTPError as e:
                logger.error(f"Error occurred while communicating with API: {str(e)}")
                raise ExchangeRateError("Failed to retrieve current exchange rates") from e

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True
    )
    async def get_available_currencies() -> dict:
        """Get supported currency symbols and full names."""
        cache_key = "currencies"

        if cache_key in rates_cache:
            logger.info("Retrieving supported currencies from cache")
            return rates_cache[cache_key]

        logger.info(f"Fetching supported currencies from {settings.api_url}")
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{settings.api_url}/currencies", timeout=5.0)
                response.raise_for_status()
                data = response.json()

                rates_cache[cache_key] = data
                return data
            except httpx.HTTPError as e:
                logger.error(f"Error occurred while fetching supported currencies: {str(e)}")
                raise ExchangeRateError("Failed to retrieve supported currencies") from e

    @staticmethod
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_historical_rates(base: str, start_date: str, end_date: str, symbols: list[str]) -> dict:
        """Auxiliary method for FR4 - Obtaining history for a period."""
        symbols_str = ",".join(symbols)
        url = f"{settings.api_url}/{start_date}..{end_date}?base={base}&symbols={symbols_str}"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, timeout=5.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Error occurred while fetching historical data: {str(e)}")
                raise ExchangeRateError("Failed to retrieve historical exchange rates") from e
