"""Rate limiting configuration based on slowapi."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.security import decode_access_token

logger = logging.getLogger(__name__)
_EMPTY_CONFIG_FILE = Path(__file__).with_name("slowapi.empty")

# Default rate-limit strings. Override via environment variables.
GENERAL_LIMIT = "100/minute"
AUTH_LIMIT = "20/minute"
LOGIN_LIMIT = "5/minute"


def get_user_or_remote_address(request) -> str:
    """额度归属：带有效 JWT 的请求算到用户头上，匿名的仍算到 IP 上。

    原来一律 `get_remote_address`，于是同一个 NAT/共享出口下的一堆候选人共用同一份
    `RATE_LIMIT_GENERAL`（默认 100/分钟）——一个人开着频繁轮询的页面就能把同出口其他人的额度
    吃光，被 429 的人什么都没做。按用户分之后各算各的。

    匿名仍然按 IP 是有意的：登录/注册在拿到身份之前只能按地址限，改成别的就等于削弱
    爆破防护。`sub` 是 `get_current_user` 唯一采信的身份字段，这里与它保持一致。
    """
    header = request.headers.get("Authorization", "") if request is not None else ""
    if header.startswith("Bearer "):
        payload = decode_access_token(header[7:]) or {}
        subject = payload.get("sub")
        if subject:
            return f"user:{subject}"
    return get_remote_address(request)


def _build_storage_uri() -> str:
    """Return the configured storage URI, isolating test runs from Redis."""
    if settings.TESTING:
        logger.info("Rate limiting using in-memory backend for tests")
        return "memory://"

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
        key_func=get_user_or_remote_address,
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
