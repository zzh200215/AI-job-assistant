# -*- coding: utf-8 -*-
"""Logging helpers with request-scoped context."""

from __future__ import annotations

import logging
import sys
from typing import Optional

from app.core.request_context import get_request_id


class RequestContextFilter(logging.Filter):
    """Inject request_id into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def configure_logging(*, debug: bool = False, level_name: Optional[str] = None) -> None:
    """Configure root logging once for the whole app process."""
    level = (level_name or ("DEBUG" if debug else "INFO")).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
