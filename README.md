# Exchange Rate API Backend

FastAPI backend for an exchange-rate application.

The service provides:
- JWT-based authentication for a single admin user
- Current exchange rates
- Exchange-rate analytics (strongest/weakest currency, average over a period)
- Structured logging with request IDs

## Tech Stack

- Python
- FastAPI
- Uvicorn / Gunicorn
- HTTPX
- Tenacity (retry logic)
- Cachetools (TTL cache)
- Loguru
- Pytest

## Project Structure

```text
app/
	main.py                  # FastAPI app, middleware, router registration
	auth.py                  # JWT auth, token validation, revocation
	config.py                # Settings loading from .env and config.json
	logger.py                # Loguru configuration and request-id support
	controllers/
		auth_controller.py     # /token, /token/renew, /logout
		exchange_controller.py # /api/rates/* endpoints
		general_controller.py  # / and /health
	services/
		exchange.py            # API integration
tests/
config.json               # default external API + logging settings
Dockerfile
requirements.txt
```

## Requirements

- Python 3.14 (recommended, matches Docker image)
- pip

## Quick Start (Local)

1. Create and activate a virtual environment.

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root with required secrets.

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=super-secret
JWT_SECRET_KEY=replace-with-a-long-random-secret
```

4. Run the API.

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. Open:
- Swagger UI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Configuration

Configuration comes from:
- `.env` (secrets and env overrides)
- `config.json` (defaults)

Default `config.json`:

```json
{
	"api_url": "https://api.frankfurter.dev/v1",
	"logging": {
		"level": "INFO",
		"filename": "logs/app.log",
		"max_bytes": 5242880,
		"backup_count": 3
	}
}
```

**Required settings:**
- `admin_username`
- `admin_password`
- `jwt_secret_key`
- `api_url`

**Optional settings:**
- `environment` (`development` or `production`)
- `logging.level`
- `logging.filename`
- `logging.max_bytes`
- `logging.backup_count`

## Authentication

The API uses OAuth2 password flow endpoint semantics (`/token`) and returns a bearer JWT.

- Token lifetime: 60 minutes
- Logout/renew revocation storage: in-memory set of revoked token IDs (`jti`)
- Note: revocations are reset after application restart

### Get access token

```bash
curl -X POST http://localhost:8000/token \
	-H "Content-Type: application/x-www-form-urlencoded" \
	-d "username=admin&password=super-secret"
```

Response:

```json
{
	"access_token": "<JWT>",
	"token_type": "bearer"
}
```

Use in protected endpoints:

```bash
Authorization: Bearer <JWT>
```

## API Endpoints

### General

- `GET /` - Welcome message
- `GET /health` - Service health check

### Auth

- `POST /token` - Login and get JWT
- `POST /token/renew` - Revoke current token and issue a new one
- `POST /logout` - Revoke current token

### Exchange Rates (protected)

- `GET /api/rates/latest?base=EUR`
	- Returns current rates for the base currency.

- `GET /api/rates/currencies`
	- Returns supported currency symbols with their full names.

- `GET /api/rates/analytics/extremes?base=EUR`
	- Returns strongest and weakest currency for current rates.

- `GET /api/rates/analytics/average?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&symbols=USD&symbols=CZK&base=EUR`
	- Returns average rates for selected symbols over a period.

### Example: latest rates

```bash
curl "http://localhost:8000/api/rates/latest?base=EUR" \
	-H "Authorization: Bearer <JWT>"
```

## Error Handling

- `401` for missing/invalid authentication
- `404` when analytics extremes have no available rates
- `502` when upstream exchange API calls fail
- `422` for invalid or missing request parameters

## Logging

- Every request gets an `X-Request-ID` (incoming value is reused, otherwise generated)
- `X-Request-ID` is also included in response headers
- Logs are written to stdout and `logs/app.log`
- Production mode enables JSON logs (`environment=production`)

## Running Tests

Run all tests:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=app --cov-report=xml --cov-report=html
```

## Docker

Build image:

```bash
docker build -t backend-exchange .
```

Run container:

```bash
docker run --rm -p 8000:8000 \
	-e ADMIN_USERNAME=admin \
	-e ADMIN_PASSWORD=super-secret \
	-e JWT_SECRET_KEY=replace-with-a-long-random-secret \
	backend-exchange
```

Container serves on port `8000` and starts with Gunicorn + Uvicorn workers.

## Notes

- Exchange data source is Frankfurter API (`https://api.frankfurter.dev/v1`)
- Latest-rate requests are cached for 15 minutes (TTL cache)
- Supported-currencies responses are cached for 15 minutes (TTL cache)
