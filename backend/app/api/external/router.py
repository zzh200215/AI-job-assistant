"""外部 API 路由聚合。

对外路径（X-API-Key 鉴权）：
  POST /api/v1/external/resume/parse
  POST /api/v1/external/match/evaluate
  POST /api/v1/external/interview/simulate
管理路径（平台管理员）：
  /api/v1/admin/external/api-keys / billing / webhooks
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.external import billing, capabilities, webhook

external_router = APIRouter(prefix="/v1", tags=["external-api"])
external_router.include_router(capabilities.router)  # /v1/external/*
external_router.include_router(billing.router)  # /v1/admin/external/*
external_router.include_router(webhook.router)  # /v1/admin/external/webhooks
