"""Structured logging setup.

Dev builds emit human-readable console logs; production emits JSON lines for
log aggregators (Datadog, CloudWatch, etc.). Extend the formatter selection
here rather than scattering logging config around the codebase.
"""
import json
import logging
import sys
from logging.handlers import RotatingFileHandler

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter for production."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging() -> logging.Logger:
    """Configure the root logger and return it."""
    level = logging.DEBUG if settings.APP_DEBUG else logging.INFO
    formatter = JsonFormatter() if settings.APP_ENV != "development" else logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Optional file output for local debugging.
    file_handler = RotatingFileHandler(
        "../storage/logs/backend.log", maxBytes=5_000_000, backupCount=3
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    return logging.getLogger("agencyos")
