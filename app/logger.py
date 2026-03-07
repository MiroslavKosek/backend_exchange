import logging
from logging.handlers import RotatingFileHandler
import os
from app.config import settings

log_dir = os.path.dirname(settings.LOG_FILENAME)
if log_dir and not os.path.exists(log_dir):
    os.makedirs(log_dir)

logger = logging.getLogger("exchange_backend")

log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logger.setLevel(log_level)

file_handler = RotatingFileHandler(
    settings.LOG_FILENAME, 
    maxBytes=settings.LOG_MAX_BYTES, 
    backupCount=settings.LOG_BACKUP_COUNT
)
file_handler.setLevel(log_level)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%d.%m.%Y %H:%M:%S')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)