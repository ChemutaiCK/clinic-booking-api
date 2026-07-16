"""
Structured logging configuration.

Emits JSON log lines in production/staging (machine-parseable, suitable for
log aggregators such as CloudWatch, Datadog, or Render's log stream) and
human-readable lines in local development. Every log line includes the
request_id when available, so requests can be traced end-to-end.
"""

import logging
import sys
from datetime import datetime, timezone

from app.config.settings import get_settings
from app.middleware.request_context import get_request_id

settings = get_settings()


class JsonFormatter(logging.Formatter):
    """Renders log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class HumanFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = get_request_id() or "-"
        base = f"[{self.formatTime(record)}] {record.levelname:<8} {record.name} ({request_id}): {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging() -> None:
    """Configure the root logger once at application startup."""
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)

    # Avoid duplicate handlers on reload.
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.LOG_JSON else HumanFormatter())
    root_logger.addHandler(handler)

    # Quiet down noisy third-party loggers.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DATABASE_ECHO else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
