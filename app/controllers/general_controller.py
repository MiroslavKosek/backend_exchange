"""General-purpose API endpoints."""

from fastapi import APIRouter

from app.client_log import ClientLog
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

@router.post("/api/logs")
async def log_message(log_data: ClientLog):
    """Endpoint to receive log messages from the Angular frontend."""

    frontend_msg = (
        f"[Frontend -> {log_data.fileName}:{log_data.lineNumber}] "
        f"{log_data.message} | Extras: {log_data.additional}"
    )

    if log_data.level >= 5:
        logger.error(frontend_msg)
    elif log_data.level == 4:
        logger.warning(frontend_msg)
    elif log_data.level in [2, 3]:
        logger.info(frontend_msg)
    else:
        logger.debug(frontend_msg)

    return {"status": "logged"}

@router.get("/health")
async def health_check():
    """Healthcheck endpoint used by monitors and orchestrators."""
    logger.debug("Health check endpoint pinged. System is healthy.")
    return {"status": "ok"}
