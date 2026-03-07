from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.logger import logger
from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application starting...")
    logger.info(f"Connecting to API: {settings.API_URL}")
    yield
    # Shutdown
    logger.info("Application shutting down...")

app = FastAPI(
    title="Exchange Rate API Backend",
    description="Semestral project - Backend for exchange rate application",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    logger.info("User visited the root endpoint.")
    return {"message": "Welcome to the Exchange Rate API Backend. Documentation is available at /docs"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}