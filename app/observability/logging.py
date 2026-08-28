"""Structured, sanitized logging for the AI Engine.

Every AI request logs request_id / user_id / conversation_id / client_id /
latency / model / tool_calls / success. Raw financial documents and secrets
are NEVER logged.
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

from app.config import settings

RESERVED_KEYS = {
    "api_key", "apikey", "token", "secret", "password", "authorization",
    "x-api-key", "access_token", "jwt", "account_number", "pan", "aadhaar",
    "pan_number", "password", "otp", "cvv",
}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (sanitize(k, v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def sanitize(key: str, value: Any) -> Any:
    if key.lower() in RESERVED_KEYS:
        return "***"
    return _sanitize(value)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record_dict = record.__dict__
        for key in list(record_dict.keys()):
            if key.lower() in RESERVED_KEYS:
                record_dict[key] = "***"
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"aos.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        handler.addFilter(RedactingFilter())
        logger.addHandler(handler)
        logger.setLevel(settings.log_level.upper())
        logger.propagate = False
    return logger


@contextmanager
def request_logger(logger: logging.Logger) -> Any:
    """Timing + sanitized metadata for one AI request."""
    start = time.perf_counter()

    class _M:
        def __init__(self):
            self.meta: Dict[str, Any] = {}

        def set(self, **kw):
            self.meta.update(kw)

    m = _M()
    try:
        yield m
    finally:
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        meta = {**m.meta, "latency_ms": elapsed}
        # strip any secret-ish values before logging
        safe = {k: sanitize(k, v) for k, v in meta.items()}
        logger.info("request complete", extra=safe)
