"""外部 Webhook 订阅端点（T6-3）：订阅 / 列表 / 停用。

鉴权用平台管理员（require_admin）——Webhook 属于平台运营配置，
与调用能力 API 的 X-API-Key 体系（capabilities.py）互补。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.database import get_db
from app.models.user import User
from app.models.webhook import WebhookSubscription
from app.services.webhook_service import VALID_EVENTS, subscribe_webhook

router = APIRouter(prefix="/admin/external/webhooks", tags=["external-webhook"])


@router.post("", summary="管理：订阅 Webhook 事件")
def admin_subscribe_webhook(
    payload: dict,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    api_key_id = int(payload.get("api_key_id") or 0)
    event = str(payload.get("event") or "").strip()
    url = str(payload.get("url") or "").strip()
    secret = str(payload.get("secret") or "").strip()
    if not api_key_id:
        raise HTTPException(status_code=400, detail="api_key_id 必填")
    try:
        sub = subscribe_webhook(
            db,
            api_key_id=api_key_id,
            tenant_id=1,
            event=event,
            url=url,
            secret=secret,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "id": sub.id,
        "api_key_id": sub.api_key_id,
        "event": sub.event,
        "url": sub.url,
        "status": sub.status,
    }


@router.get("", summary="管理：Webhook 订阅列表")
def admin_list_webhooks(
    api_key_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = db.query(WebhookSubscription)
    if api_key_id:
        query = query.filter(WebhookSubscription.api_key_id == api_key_id)
    total = query.count()
    subs = query.order_by(WebhookSubscription.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "id": s.id,
                "api_key_id": s.api_key_id,
                "event": s.event,
                "url": s.url,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in subs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{sub_id}/disable", summary="管理：停用 Webhook 订阅")
def admin_disable_webhook(
    sub_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    sub = db.get(WebhookSubscription, sub_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="订阅不存在")
    sub.status = "disabled"
    db.add(sub)
    db.commit()
    return {"id": sub.id, "status": sub.status}
