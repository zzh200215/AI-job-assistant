"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

import app.models  # noqa: F401
from app.api.interview_ws import router as interview_ws_router
from app.api.router import api_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.logging_utils import clear_logging_context, configure_logging, set_logging_context
from app.core.prometheus_metrics import record_http_request, record_rate_limited
from app.core.rate_limiter import get_limiter
from app.core.request_context import set_request_id
from app.core.runtime_metrics import record_request
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.core.schema_drift import log_drift
from app.core.tenant_context import tenant_context_middleware
from app.services.interview_evaluation_service import shutdown_interview_evaluation_executor
from app.services.orchestration_runner import mark_stale_running_tasks_failed, shutdown_orchestration_executor
from app.utils.response import ERR_AUTH, ERR_COMMON, ERR_PARAM, fail, ok

configure_logging(
    debug=settings.APP_DEBUG,
    level_name=settings.LOG_LEVEL,
    structured=settings.STRUCTURED_LOGS,
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.AUTO_CREATE_TABLES:
        Base.metadata.create_all(bind=engine)
    # 两种模式都体检：开发态能发现"模型改了但表没建全"，生产态（AUTO_CREATE_TABLES=false）
    # 第一次能在启动日志里看到"忘了跑 alembic upgrade head"，而不是等第一条查询报 no such column。
    log_drift(engine)
    mark_stale_running_tasks_failed()
    start_scheduler()
    yield
    shutdown_scheduler()
    shutdown_interview_evaluation_executor()
    shutdown_orchestration_executor()


app = FastAPI(
    title="Smart Recruitment and Career Planning API",
    description="Resume parsing, job matching, and career planning services powered by LLM workflows.",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.limiter = get_limiter()
app.add_middleware(SlowAPIMiddleware)

cors_kwargs = {
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
# 租户上下文中间件（T2-3）：先于 CORS 注册，使 CORS 在更外层执行，租户 403 也带上 CORS 头
app.middleware("http")(tenant_context_middleware)

if settings.cors_origins_list:
    cors_kwargs["allow_origins"] = settings.cors_origins_list
else:
    cors_kwargs["allow_origin_regex"] = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
app.add_middleware(CORSMiddleware, **cors_kwargs)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

app.include_router(api_router, prefix="/api")
app.include_router(interview_ws_router)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    set_request_id(request_id)
    start = perf_counter()

    authorization = request.headers.get("Authorization") or ""
    if authorization.startswith("Bearer "):
        try:
            from app.core.security import decode_access_token

            token = authorization[7:]
            payload = decode_access_token(token)
            if payload and payload.get("sub"):
                set_logging_context("user_id", str(payload["sub"]))
        except Exception:
            pass

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (perf_counter() - start) * 1000
        duration_seconds = duration_ms / 1000.0
        record_request(method=request.method, status_code=500, duration_ms=duration_ms)
        record_http_request(
            method=request.method,
            status_code=500,
            path=request.url.path,
            duration_seconds=duration_seconds,
        )
        set_request_id(None)
        clear_logging_context()
        raise

    duration_ms = (perf_counter() - start) * 1000
    duration_seconds = duration_ms / 1000.0
    response.headers["X-Request-ID"] = request_id
    record_request(
        method=request.method,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    record_http_request(
        method=request.method,
        status_code=response.status_code,
        path=request.url.path,
        duration_seconds=duration_seconds,
    )
    logger.info(
        "Request completed method=%s path=%s status=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    set_request_id(None)
    clear_logging_context()
    return response


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(
        "Rate limit exceeded method=%s path=%s client=%s",
        request.method,
        request.url.path,
        request.client.host if request.client else "-",
    )
    record_rate_limited(path=request.url.path)
    return JSONResponse(
        status_code=429,
        content=fail(message="请求过于频繁，请稍后再试", code=ERR_COMMON),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in (401, 403):
        err_code = ERR_AUTH
    elif exc.status_code == 404:
        err_code = ERR_PARAM
    else:
        err_code = ERR_COMMON

    detail = exc.detail
    if isinstance(detail, dict):
        message = detail.get("message", "error")
        err_code = detail.get("code", err_code)
        data = detail.get("data")
    else:
        message = detail
        data = None

    return JSONResponse(
        status_code=exc.status_code,
        content=fail(message=message, code=err_code, data=data),
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    logger.warning(
        "Validation failed path=%s errors=%s",
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content=fail(message="request validation failed", code=ERR_PARAM, data={"errors": exc.errors()}),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    detail = f"{type(exc).__name__}: {exc}" if settings.APP_DEBUG else "internal server error"
    logger.exception(
        "Unhandled exception path=%s method=%s error=%s",
        request.url.path,
        request.method,
        detail,
    )
    return JSONResponse(
        status_code=500,
        content=fail(message=detail, code=ERR_COMMON),
    )


@app.get("/", summary="Health check")
async def root():
    return ok(
        data={
            "service": "smart-recruitment-platform",
            "version": "0.1.0",
            "docs": "/docs",
        }
    )
