from fastapi import FastAPI
from fastapi import Request
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4
from app.logger import logger, reset_request_id, set_request_id
from app.config import settings

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