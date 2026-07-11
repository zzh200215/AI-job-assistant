# -*- coding: utf-8 -*-
"""Rate limiting configuration based on slowapi."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)
_EMPTY_CONFIG_FILE = Path(__file__).with_name("slowapi.empty")

# Default rate-limit strings. Override via environment variables.
GENERAL_LIMIT = "100/minute"
AUTH_LIMIT = "20/minute"
LOGIN_LIMIT = "5/minute"


def _build_storage_uri() -> str:
    """Return Redis URI if configured, otherwise in-memory storage."""
    redis_url = (settings.REDIS_URL or "").strip()
    if redis_url:
        logger.info("Rate limiting using Redis backend")
        # slowapi/limits accepts redis://... or rediss://...
        return redis_url
    logger.info("Rate limiting using in-memory backend")
    return "memory://"


@lru_cache(maxsize=1)
def get_limiter() -> Limiter:
    """Return the shared slowapi Limiter instance."""
    return Limiter(
        key_func=get_remote_address,
        storage_uri=_build_storage_uri(),
        default_limits=[(settings.RATE_LIMIT_GENERAL or GENERAL_LIMIT)],
        headers_enabled=True,
        # Avoid slowapi/starlette reading the project .env with a locale-specific
        # encoding on Windows. App settings are already loaded via pydantic.
        config_filename=str(_EMPTY_CONFIG_FILE),
    )


def default_limit() -> str:
    """Return the configured global default limit."""
    return settings.RATE_LIMIT_GENERAL or GENERAL_LIMIT


def auth_limit() -> str:
    """Return the configured auth-endpoint limit."""
    return settings.RATE_LIMIT_AUTH or AUTH_LIMIT


def login_limit() -> str:
    """Return the configured login/register/reset limit."""
    return settings.RATE_LIMIT_LOGIN or LOGIN_LIMIT
