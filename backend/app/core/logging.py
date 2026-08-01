"""Structured logging setup.

- development: human-readable console output,
- production: JSON lines for aggregators (with request_id).

A record factory injects the current request id into every log record so both
formatters can render it. File output is opt-in (LOG_TO_FILE=true).
"""
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings
from app.core.contextvars import request_id_var


class JsonFormatter(logging.Formatter):
    """JSON log formatter for production aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class DevFormatter(logging.Formatter):
    """Compact, readable formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_var.get()
        return super().format(record)


DEV_FORMAT = "%(asctime)s | %(levelname)-7s | %(request_id)s | %(name)s | %(message)s"


def setup_logging() -> logging.Logger:
    """Configure the root logger and return the application logger."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    formatter = (
        DevFormatter(fmt=DEV_FORMAT)
        if settings.APP_ENV == "development"
        else JsonFormatter()
    )

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)

    if settings.LOG_TO_FILE:
        path = Path(settings.LOG_FILE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    return logging.getLogger("agencyos")
