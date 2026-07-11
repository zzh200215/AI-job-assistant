# -*- coding: utf-8 -*-
"""站内消息 API"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.utils.response import ERR_PARAM, ok, fail

router = APIRouter()

VALID_TYPES = {
    "interview_reminder", "offer_reminder", "system",
    "recommendation", "application_update",
}


@router.get("/list", summary="获取消息列表")
async def list_notifications(
    type: str = Query("", description="消息类型过滤"),
    is_read: Optional[int] = Query(None, description="已读状态: 0-未读 1-已读"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Notification).filter(Notification.user_id == current_user.id)
    if type:
        q = q.filter(Notification.type == type)
    if is_read is not None:
        q = q.filter(Notification.is_read == is_read)

    total = q.count()
    items = (
        q.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok({
        "total": total,
        "items": [item.to_dict() for item in items],
    })


@router.get("/unread-count", summary="获取未读消息数")
async def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == 0,
        )
        .scalar()
    )
    # 按类型统计
    type_counts = dict(
        db.query(Notification.type, func.count(Notification.id))
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == 0,
        )
        .group_by(Notification.type)
        .all()
    )
    return ok({"total": count, "by_type": type_counts})


@router.post("/{notification_id}/read", summary="标记消息已读")
async def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if not notification:
        return fail(message="消息不存在", code=ERR_PARAM)

    if notification.is_read == 0:
        notification.is_read = 1
        from app.utils.time_helper import utc_now
        notification.read_at = utc_now()
        db.add(notification)
        db.commit()

    return ok(message="已标记已读")


@router.post("/read-all", summary="全部标记已读")
async def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == 0,
        )
        .update({"is_read": 1, "read_at": func.now()})
    )
    db.commit()
    return ok({"marked": result}, message=f"已标记 {result} 条消息为已读")


@router.delete("/{notification_id}", summary="删除消息")
async def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if not notification:
        return fail(message="消息不存在", code=ERR_PARAM)

    db.delete(notification)
    db.commit()
    return ok(message="消息已删除")


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    content: str = "",
    link: str = "",
    metadata: dict = None,
    auto_commit: bool = True,
) -> Notification:
    """创建站内消息的辅助函数，供其他服务调用。

    Args:
        auto_commit: 是否立即提交。批量场景下传 False，由调用方统一 commit。
    """
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        content=content,
        link=link,
        ext_data=metadata,
    )
    db.add(notification)
    if auto_commit:
        db.commit()
        db.refresh(notification)
    return notification
