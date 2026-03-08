import os
import sys
import logging
from contextvars import ContextVar, Token
from uuid import uuid4
from loguru import logger
from app.config import settings

_cfg = settings.logging
_level = _cfg.level.upper()
_is_production = settings.environment.lower() == "production"

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

def set_request_id(request_id: str) -> Token:
    return _request_id_ctx.set(request_id)

def reset_request_id(token: Token) -> None:
    _request_id_ctx.reset(token)

def get_request_id() -> str:
    return _request_id_ctx.get()

def get_or_create_request_id() -> str:
    request_id = get_request_id()
    if request_id == "-":
        return str(uuid4())
    return request_id

logger = logger.patch(
    lambda record: record["extra"].setdefault("request_id", get_or_create_request_id())
)

log_dir = os.path.dirname(_cfg.filename)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)

logger.remove()

if _is_production:
    logger.add(sys.stdout, level=_level, serialize=True)
    logger.add(
        _cfg.filename,
        level=_level,
        serialize=True,
        rotation=_cfg.max_bytes,
        retention=_cfg.backup_count,
    )
else:
    _fmt = "{time:DD.MM.YYYY HH:mm:ss} | {level:<8} | {extra[request_id]} | {message}"
    logger.add(sys.stdout, format=_fmt, level=_level, colorize=True)
    logger.add(
        _cfg.filename,
        format=_fmt,
        level=_level,
        rotation=_cfg.max_bytes,
        retention=_cfg.backup_count,
    )

class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.bind(request_id=get_or_create_request_id()).opt(
            depth=depth,
            exception=record.exc_info,
        ).log(level, record.getMessage())

intercept_handler = InterceptHandler()

root_logger = logging.getLogger()
root_logger.setLevel(_level)
root_logger.handlers.clear()
root_logger.addHandler(intercept_handler)

for name in ("uvicorn", "uvicorn.error", "fastapi"):
    std_logger = logging.getLogger(name)
    std_logger.setLevel(_level)
    std_logger.handlers.clear()
    std_logger.addHandler(intercept_handler)
    std_logger.propagate = False

uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.handlers.clear()
uvicorn_access_logger.addHandler(logging.NullHandler())
uvicorn_access_logger.propagate = False