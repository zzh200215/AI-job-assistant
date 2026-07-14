"""智能提醒 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.job_target import JobTarget
from app.models.user import User
from app.schemas.c_end import MatchJdsRequest
from app.services.reminder_service import (
    check_and_send_reminders,
    match_new_jds_for_target,
    send_new_jd_notifications,
)
from app.utils.job_access import is_admin
from app.utils.response import ERR_AUTH, ERR_PARAM, fail, ok

router = APIRouter()


@router.post("/trigger", summary="手动触发提醒检查（管理员）")
async def trigger_reminders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动触发一次提醒检查，仅管理员可用。"""
    if not is_admin(current_user):
        return fail(message="无权限，仅管理员可触发", code=ERR_AUTH)
    stats = check_and_send_reminders(db)
    return ok(stats, message="提醒检查完成")


@router.get("/upcoming", summary="获取即将到来的提醒列表")
async def upcoming_reminders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户即将到来的面试、Offer截止等提醒。"""
    from datetime import timedelta, timezone

    from app.models.job_pipeline import JobApplicationPipeline
    from app.utils.time_helper import utc_now

    now = utc_now()
    reminders = []

    def make_aware(dt):
        if dt and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    # 即将面试（7天内）
    interviews = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.stage == "interview",
            JobApplicationPipeline.interview_at.isnot(None),
            JobApplicationPipeline.interview_at >= now,
            JobApplicationPipeline.interview_at <= now + timedelta(days=7),
        )
        .order_by(JobApplicationPipeline.interview_at.asc())
        .all()
    )
    for p in interviews:
        interview_at = make_aware(p.interview_at)
        hours_until = (interview_at - now).total_seconds() / 3600
        reminders.append(
            {
                "type": "interview",
                "title": f"面试：{p.company or ''} - {p.title or ''}",
                "time": p.interview_at.isoformat(),
                "hours_until": round(hours_until, 1),
                "urgency": "high" if hours_until < 24 else "medium",
                "pipeline_id": p.id,
                "details": {
                    "round": p.interview_round,
                    "location": p.interview_location,
                    "contact": p.interview_contact,
                },
            }
        )

    # Offer即将到期（7天内）
    offers = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.stage == "offer",
            JobApplicationPipeline.offer_deadline.isnot(None),
            JobApplicationPipeline.offer_deadline >= now,
            JobApplicationPipeline.offer_deadline <= now + timedelta(days=7),
        )
        .order_by(JobApplicationPipeline.offer_deadline.asc())
        .all()
    )
    for p in offers:
        deadline = make_aware(p.offer_deadline)
        days_until = (deadline - now).days
        reminders.append(
            {
                "type": "offer_deadline",
                "title": f"Offer到期：{p.company or ''} - {p.title or ''}",
                "time": p.offer_deadline.isoformat(),
                "days_until": days_until,
                "urgency": "high" if days_until <= 1 else "medium",
                "pipeline_id": p.id,
                "details": {
                    "salary": p.offer_salary,
                },
            }
        )

    # 投递超5天无回复
    stalled = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.stage == "applied",
            JobApplicationPipeline.update_time <= now - timedelta(days=5),
        )
        .order_by(JobApplicationPipeline.update_time.asc())
        .all()
    )
    for p in stalled:
        update_time = make_aware(p.update_time)
        days = (now - update_time).days if update_time else 0
        reminders.append(
            {
                "type": "follow_up",
                "title": f"投递 {days} 天无回复：{p.company or ''} - {p.title or ''}",
                "time": p.update_time.isoformat(),
                "days_stalled": days,
                "urgency": "low",
                "pipeline_id": p.id,
            }
        )

    # 按紧急度排序
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    reminders.sort(key=lambda r: (urgency_order.get(r["urgency"], 3), r.get("hours_until", 999) or 999))

    return ok(
        {
            "total": len(reminders),
            "high_urgency": sum(1 for r in reminders if r["urgency"] == "high"),
            "reminders": reminders,
        }
    )


@router.post("/match-jds", summary="为求职目标匹配新JD")
async def match_jds_for_target(
    payload: MatchJdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据指定求职目标匹配新的JD，并推送通知。"""
    target_id = payload.target_id

    if target_id:
        target = (
            db.query(JobTarget)
            .filter(
                JobTarget.id == target_id,
                JobTarget.user_id == current_user.id,
            )
            .first()
        )
        if not target:
            return fail(message="目标不存在", code=ERR_PARAM)
        count = send_new_jd_notifications(db, current_user.id, target_id)
    else:
        count = send_new_jd_notifications(db, current_user.id)

    return ok({"notifications_sent": count}, message=f"已推送 {count} 条新职位通知")


@router.get("/preview-matches/{target_id}", summary="预览目标匹配的JD（不发通知）")
async def preview_matches(
    target_id: int,
    limit: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """预览某个求职目标匹配的新JD，不发送通知。"""
    target = (
        db.query(JobTarget)
        .filter(
            JobTarget.id == target_id,
            JobTarget.user_id == current_user.id,
        )
        .first()
    )
    if not target:
        return fail(message="目标不存在", code=ERR_PARAM)

    matched = match_new_jds_for_target(db, target, limit=limit)
    return ok(
        {
            "target": target.to_dict(),
            "matched_count": len(matched),
            "matched_jds": [
                {
                    "id": jd.id,
                    "title": jd.title,
                    "company": jd.company,
                    "location": jd.location,
                    "salary_range": jd.salary_range,
                    "industry": jd.industry,
                    "create_time": jd.create_time.isoformat() if jd.create_time else None,
                }
                for jd in matched
            ],
        }
    )
