"""General-purpose API endpoints."""

from fastapi import APIRouter

from app.logger import logger

router = APIRouter(tags=["General"])


@router.get("/")
async def root():
    """Return a simple welcome message and docs hint."""
    logger.info("Accessing root welcome endpoint.")
    response_payload = {
        "message": (
            "Welcome to the Exchange Rate API Backend. "
            "Documentation is available at /docs"
        )
    }
    logger.debug(f"Root endpoint returning payload: {response_payload}")
    return response_payload


@router.get("/health")
async def health_check():
    """Healthcheck endpoint used by monitors and orchestrators."""
    logger.debug("Health check endpoint pinged. System is healthy.")
    return {"status": "ok"}
