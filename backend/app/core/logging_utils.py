"""Logging helpers with request-scoped context."""

from __future__ import annotations

import logging
import sys
from typing import Any

from app.core.request_context import get_request_id


def _get_logging_context() -> dict[str, Any]:
    """Return current request-scoped logging context."""
    return getattr(_LOGGING_CONTEXT, "data", {}) or {}


class RequestContextFilter(logging.Filter):
    """Inject request_id and user_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        ctx = _get_logging_context()
        record.user_id = ctx.get("user_id") or "-"
        return True


def _text_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s user_id=%(user_id)s %(message)s"
    )


def _json_formatter() -> logging.Formatter:
    try:
        from pythonjsonlogger import jsonlogger
    except ImportError:
        return _text_formatter()

    formatter = jsonlogger.JsonFormatter(
        "%(timestamp)s %(level)s %(logger)s %(message)s %(request_id)s %(user_id)s",
        rename_fields={"levelname": "level", "name": "logger", "asctime": "timestamp"},
    )
    return formatter


class _LoggingContext:
    """Thread-local logging context."""

    def __init__(self):
        import threading

        self._local = threading.local()

    @property
    def data(self) -> dict[str, Any]:
        return getattr(self._local, "data", {}) or {}

    def set(self, key: str, value: Any) -> None:
        if not hasattr(self._local, "data"):
            self._local.data = {}
        self._local.data[key] = value

    def clear(self) -> None:
        self._local.data = {}


_LOGGING_CONTEXT = _LoggingContext()


def set_logging_context(key: str, value: Any) -> None:
    _LOGGING_CONTEXT.set(key, value)


def clear_logging_context() -> None:
    _LOGGING_CONTEXT.clear()


def configure_logging(*, debug: bool = False, level_name: str | None = None, structured: bool = False) -> None:
    """Configure root logging once for the whole app process."""
    level = (level_name or ("DEBUG" if debug else "INFO")).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(RequestContextFilter())
    formatter = _json_formatter() if structured else _text_formatter()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
