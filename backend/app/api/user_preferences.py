# -*- coding: utf-8 -*-
"""用户偏好设置 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.c_end import NotificationPrefsUpdate, PrivacyUpdate, DefaultsUpdate
from app.utils.response import ERR_PARAM, ok, fail

router = APIRouter()


@router.get("/preferences", summary="获取用户偏好设置")
async def get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的所有偏好设置。"""
    db.refresh(current_user)

    return ok({
        "default_resume_id": current_user.default_resume_id,
        "default_target_id": current_user.default_target_id,
        "notification": current_user.get_notification_preferences(),
        "privacy": current_user.get_privacy_settings(),
        "language": current_user.language or "zh-CN",
        "theme": current_user.theme or "light",
    })


@router.put("/preferences/notification", summary="更新通知偏好")
async def update_notification_preferences(
    payload: NotificationPrefsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新通知偏好设置。"""
    current = current_user.get_notification_preferences()

    update_data = payload.model_dump(exclude_unset=True)
    current.update(update_data)

    current_user.notification_preferences = current
    db.add(current_user)
    db.commit()

    return ok(current, message="通知偏好已更新")


@router.put("/preferences/privacy", summary="更新隐私设置")
async def update_privacy_settings(
    payload: PrivacyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新隐私设置。"""
    current = current_user.get_privacy_settings()

    update_data = payload.model_dump(exclude_unset=True)
    current.update(update_data)

    current_user.privacy_settings = current
    db.add(current_user)
    db.commit()

    return ok(current, message="隐私设置已更新")


@router.put("/preferences/defaults", summary="更新默认设置")
async def update_defaults(
    payload: DefaultsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新默认设置。"""
    if payload.default_resume_id is not None:
        rid = payload.default_resume_id
        from app.models.history import Resume
        resume = db.query(Resume).filter(
            Resume.id == rid,
            Resume.user_id == current_user.id,
            Resume.is_deleted == 0,
        ).first()
        if not resume:
            return fail(message="简历不存在或无权限", code=ERR_PARAM)
        current_user.default_resume_id = rid

    if payload.default_target_id is not None:
        tid = payload.default_target_id
        from app.models.job_target import JobTarget
        target = db.query(JobTarget).filter(
            JobTarget.id == tid,
            JobTarget.user_id == current_user.id,
        ).first()
        if not target:
            return fail(message="求职目标不存在或无权限", code=ERR_PARAM)
        current_user.default_target_id = tid

    if payload.language is not None:
        current_user.language = payload.language

    if payload.theme is not None:
        current_user.theme = payload.theme

    db.add(current_user)
    db.commit()

    return ok({
        "default_resume_id": current_user.default_resume_id,
        "default_target_id": current_user.default_target_id,
        "language": current_user.language,
        "theme": current_user.theme,
    }, message="默认设置已更新")
