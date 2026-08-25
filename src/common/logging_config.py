"""Structured logging configuration for the SLA prediction application."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging import Logger


class JsonFormatter(logging.Formatter):
    """Format operational logs as compact JSON for container log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id

        # Include exception details in server logs.
        # These details are NOT returned to API clients.
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> Logger:
    """Configure stdout logging once and return the application logger."""
    logger = logging.getLogger("sla_prediction")
    logger.setLevel(level.upper())
    logger.propagate = False

    if not logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(JsonFormatter())
        logger.addHandler(stream_handler)

    return logger
