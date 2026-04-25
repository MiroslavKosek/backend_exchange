"""Client log data model and API endpoint for receiving logs from the frontend."""

from typing import Any, List, Optional
from pydantic import BaseModel

class ClientLog(BaseModel):
    """Data model for client log messages."""
    level: int
    timestamp: str
    fileName: Optional[str] = None
    lineNumber: Optional[int] = None
    message: str
    additional: Optional[List[Any]] = []
