"""General-purpose API endpoints."""

from fastapi import APIRouter

from app.logger import logger

router = APIRouter(tags=["General"])


@router.get("/")
async def root():
    """Return a simple welcome message and docs hint."""
    logger.info("User visited the root endpoint.")
    return {
        "message": (
            "Welcome to the Exchange Rate API Backend. "
            "Documentation is available at /docs"
        )
    }


@router.get("/health")
async def health_check():
    """Healthcheck endpoint used by monitors and orchestrators."""
    return {"status": "ok"}
