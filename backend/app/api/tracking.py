"""数据埋点 API。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.utils.response import ok

router = APIRouter()


@router.post("/events", summary="批量上报埋点事件")
def track_events(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    接收前端批量上报的埋点事件。

    请求体: {"events": [{"event": "upload_resume", "properties": {...}, "timestamp": "..."}]}

    当前为 stub 实现，存入日志文件。
    后续可接入 ClickHouse / Prometheus / 自建分析系统。
    """
    import json
    import logging

    logger = logging.getLogger("tracking")
    events = payload.get("events", [])

    for event in events:
        log_entry = {
            "user_id": current_user.id,
            "username": current_user.username,
            "event": event.get("event"),
            "properties": event.get("properties", {}),
            "timestamp": event.get("timestamp") or datetime.utcnow().isoformat(),
        }
        logger.info("TRACK: %s", json.dumps(log_entry, ensure_ascii=False))

    return ok({"received": len(events)})
