# -*- coding: utf-8 -*-
"""用户仪表盘 API — 求职数据统计汇总"""
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.interview_session import InterviewSession
from app.models.job_pipeline import JobApplicationPipeline, ACTIVE_STAGES
from app.models.notification import Notification
from app.models.user import User
from app.utils.response import ok
from app.utils.time_helper import utc_now

router = APIRouter()


@router.get("/overview", summary="求职仪表盘总览")
async def dashboard_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.id
    now = utc_now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # --- 投递数据 ---
    pipeline_base = db.query(JobApplicationPipeline).filter(JobApplicationPipeline.user_id == uid)
    total_applications = pipeline_base.count()
    active_applications = pipeline_base.filter(
        JobApplicationPipeline.stage.in_(ACTIVE_STAGES)
    ).count()

    # 按阶段统计
    stage_rows = (
        db.query(JobApplicationPipeline.stage, func.count(JobApplicationPipeline.id))
        .filter(JobApplicationPipeline.user_id == uid)
        .group_by(JobApplicationPipeline.stage)
        .all()
    )
    stage_counts = {stage: count for stage, count in stage_rows}

    # 本周新增
    weekly_new = pipeline_base.filter(
        JobApplicationPipeline.create_time >= week_ago
    ).count()

    # 本月新增
    monthly_new = pipeline_base.filter(
        JobApplicationPipeline.create_time >= month_ago
    ).count()

    # --- 面试数据 ---
    upcoming_interviews = (
        db.query(func.count(JobApplicationPipeline.id))
        .filter(
            JobApplicationPipeline.user_id == uid,
            JobApplicationPipeline.stage == "interview",
            JobApplicationPipeline.interview_at.isnot(None),
            JobApplicationPipeline.interview_at >= now,
        )
        .scalar()
    )

    total_interview_sessions = (
        db.query(func.count(InterviewSession.id))
        .filter(InterviewSession.user_id == uid)
        .scalar()
    )

    # --- 简历数据 ---
    total_resumes = (
        db.query(func.count(Resume.id))
        .filter(Resume.user_id == uid, Resume.is_deleted == 0)
        .scalar()
    )

    # --- 匹配分析数据 ---
    avg_match_score = (
        db.query(func.avg(AnalysisRecord.match_score))
        .filter(
            AnalysisRecord.user_id == uid,
            AnalysisRecord.is_deleted == 0,
            AnalysisRecord.match_score.isnot(None),
        )
        .scalar()
    )

    # --- 收藏数据 ---
    from app.models.job_recommend import JobBookmark
    bookmarked_count = (
        db.query(func.count(JobBookmark.id))
        .filter(JobBookmark.user_id == uid, JobBookmark.action == "bookmark")
        .scalar()
    )

    # --- 未读消息 ---
    unread_notifications = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == uid, Notification.is_read == 0)
        .scalar()
    )

    # --- Offer 数据 ---
    offer_count = pipeline_base.filter(
        JobApplicationPipeline.stage.in_(["offer", "accepted"])
    ).count()

    pending_offers = pipeline_base.filter(
        JobApplicationPipeline.stage == "offer"
    ).count()

    # --- 最近活动（最近5条投递变化）---
    recent_activities = (
        db.query(JobApplicationPipeline)
        .filter(JobApplicationPipeline.user_id == uid)
        .order_by(JobApplicationPipeline.update_time.desc())
        .limit(5)
        .all()
    )

    # --- 投递趋势（最近7天每日新增）---
    trend = []
    for offset in range(6, -1, -1):
        day = (now - timedelta(days=offset)).date()
        next_day = day + timedelta(days=1)
        count = (
            db.query(func.count(JobApplicationPipeline.id))
            .filter(
                JobApplicationPipeline.user_id == uid,
                JobApplicationPipeline.create_time >= day,
                JobApplicationPipeline.create_time < next_day,
            )
            .scalar()
        )
        trend.append({"date": day.isoformat(), "count": count})

    # --- 转化漏斗 ---
    funnel = {
        "todo": stage_counts.get("todo", 0),
        "applied": stage_counts.get("applied", 0),
        "written_test": stage_counts.get("written_test", 0),
        "interview": stage_counts.get("interview", 0),
        "offer": stage_counts.get("offer", 0) + stage_counts.get("accepted", 0),
    }

    return ok({
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "nickname": getattr(current_user, "nickname", "") or "",
            "avatar_url": getattr(current_user, "avatar_url", "") or "",
            "job_seeking_status": getattr(current_user, "job_seeking_status", "") or "",
        },
        "summary": {
            "total_applications": total_applications,
            "active_applications": active_applications,
            "upcoming_interviews": upcoming_interviews,
            "pending_offers": pending_offers,
            "total_resumes": total_resumes,
            "bookmarked_jobs": bookmarked_count,
            "unread_notifications": unread_notifications,
            "avg_match_score": round(float(avg_match_score), 1) if avg_match_score else None,
        },
        "weekly_new": weekly_new,
        "monthly_new": monthly_new,
        "funnel": funnel,
        "stage_counts": stage_counts,
        "trend": trend,
        "recent_activities": [a.to_dict() for a in recent_activities],
    })


@router.get("/weekly-report", summary="求职周报")
async def weekly_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    uid = current_user.id
    now = utc_now()
    week_ago = now - timedelta(days=7)

    # 本周新增投递
    new_applications = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == uid,
            JobApplicationPipeline.create_time >= week_ago,
        )
        .order_by(JobApplicationPipeline.create_time.desc())
        .all()
    )

    # 本周阶段变化
    stage_changes = []
    for app in new_applications:
        history = app.stage_history or []
        for h in history:
            if h.get("at"):
                from datetime import datetime
                try:
                    at = datetime.fromisoformat(h["at"].replace("Z", "+00:00"))
                    if at >= week_ago:
                        stage_changes.append({
                            "application_id": app.id,
                            "title": app.title,
                            "company": app.company,
                            "from_stage": h.get("from_stage", ""),
                            "to_stage": h.get("stage", ""),
                            "at": h["at"],
                        })
                except (ValueError, TypeError):
                    pass

    # 本周面试
    weekly_interviews = [
        a.to_dict() for a in
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == uid,
            JobApplicationPipeline.stage == "interview",
            JobApplicationPipeline.interview_at.isnot(None),
            JobApplicationPipeline.interview_at >= week_ago,
        )
        .all()
    ]

    # 本周AI模拟面试
    weekly_mock_interviews = (
        db.query(func.count(InterviewSession.id))
        .filter(
            InterviewSession.user_id == uid,
            InterviewSession.created_at >= week_ago,
        )
        .scalar()
    )

    # 各阶段分布
    stage_rows = (
        db.query(JobApplicationPipeline.stage, func.count(JobApplicationPipeline.id))
        .filter(JobApplicationPipeline.user_id == uid)
        .group_by(JobApplicationPipeline.stage)
        .all()
    )

    return ok({
        "period": {
            "from": week_ago.isoformat(),
            "to": now.isoformat(),
        },
        "new_applications": len(new_applications),
        "new_application_list": [a.to_dict() for a in new_applications[:10]],
        "stage_changes": stage_changes[:20],
        "upcoming_interviews": weekly_interviews,
        "mock_interviews_completed": weekly_mock_interviews,
        "current_stage_distribution": dict(stage_rows),
        "suggestions": _generate_suggestions(new_applications, stage_changes, weekly_interviews),
    })


def _generate_suggestions(new_apps, stage_changes, interviews):
    """基于本周数据生成建议"""
    suggestions = []

    if len(new_apps) == 0:
        suggestions.append("本周还没有新增投递，建议每天浏览推荐职位并投递3-5个")

    if len(interviews) == 0 and len(new_apps) > 3:
        suggestions.append("投递较多但尚未收到面试邀请，建议优化简历匹配度或调整投递方向")

    rejected_count = sum(1 for c in stage_changes if c.get("to_stage") == "rejected")
    if rejected_count >= 3:
        suggestions.append(f"本周收到 {rejected_count} 次拒绝，建议复盘简历和面试表现")

    if len(interviews) > 0:
        suggestions.append("本周有面试安排，建议使用AI模拟面试提前准备")

    if not suggestions:
        suggestions.append("求职进展不错，继续保持节奏！")

    return suggestions


@router.get("/today-tasks", summary="今日待办")
async def today_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """聚合今日待办事项：面试、Offer截止、跟进投递、推荐岗位等"""
    uid = current_user.id
    now = utc_now()
    today_end = now + timedelta(days=1)

    tasks = []

    # 1. 今日面试
    today_interviews = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == uid,
            JobApplicationPipeline.stage == "interview",
            JobApplicationPipeline.interview_at.isnot(None),
            JobApplicationPipeline.interview_at >= now,
            JobApplicationPipeline.interview_at <= today_end,
        )
        .order_by(JobApplicationPipeline.interview_at.asc())
        .all()
    )
    for p in today_interviews:
        tasks.append({
            "type": "interview",
            "priority": "high",
            "title": f"面试 {p.company or ''} - {p.title or ''}",
            "subtitle": f"第{p.interview_round or 1}轮 {p.interview_at.strftime('%H:%M') if p.interview_at else ''}",
            "link": f"/jobs/pipeline/{p.id}",
            "pipeline_id": p.id,
        })

    # 2. Offer即将到期（3天内）
    offer_deadlines = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == uid,
            JobApplicationPipeline.stage == "offer",
            JobApplicationPipeline.offer_deadline.isnot(None),
            JobApplicationPipeline.offer_deadline >= now,
            JobApplicationPipeline.offer_deadline <= now + timedelta(days=3),
        )
        .all()
    )
    for p in offer_deadlines:
        days_left = (p.offer_deadline - now).days
        tasks.append({
            "type": "offer_deadline",
            "priority": "high" if days_left <= 1 else "medium",
            "title": f"Offer决策 {p.company or ''}",
            "subtitle": f"还剩 {days_left} 天到期",
            "link": f"/jobs/pipeline/{p.id}",
            "pipeline_id": p.id,
        })

    # 3. 投递跟进（5天无回复）
    stalled = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == uid,
            JobApplicationPipeline.stage == "applied",
            JobApplicationPipeline.update_time <= now - timedelta(days=5),
        )
        .order_by(JobApplicationPipeline.update_time.asc())
        .limit(5)
        .all()
    )
    for p in stalled:
        days = (now - p.update_time).days if p.update_time else 0
        tasks.append({
            "type": "follow_up",
            "priority": "medium",
            "title": f"跟进 {p.company or ''}",
            "subtitle": f"投递 {days} 天无回复",
            "link": f"/jobs/pipeline/{p.id}",
            "pipeline_id": p.id,
        })

    # 4. 待投递
    todo_count = (
        db.query(func.count(JobApplicationPipeline.id))
        .filter(JobApplicationPipeline.user_id == uid, JobApplicationPipeline.stage == "todo")
        .scalar()
    )
    if todo_count > 0:
        tasks.append({
            "type": "apply",
            "priority": "medium",
            "title": f"投递待办",
            "subtitle": f"{todo_count} 个岗位待投递",
            "link": "/jobs/pipeline/kanban?stage=todo",
        })

    # 5. 推荐岗位
    from app.models.job_recommend import JobBookmark
    bookmarked_count = (
        db.query(func.count(JobBookmark.id))
        .filter(JobBookmark.user_id == uid, JobBookmark.action == "bookmark")
        .scalar()
    )
    if bookmarked_count > 0:
        tasks.append({
            "type": "bookmark",
            "priority": "low",
            "title": "查看收藏岗位",
            "subtitle": f"{bookmarked_count} 个收藏待处理",
            "link": "/jobs/bookmarks/list",
        })

    # 按优先级排序
    priority_order = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda t: priority_order.get(t["priority"], 3))

    return ok({
        "total": len(tasks),
        "high_priority": sum(1 for t in tasks if t["priority"] == "high"),
        "tasks": tasks,
    })


@router.get("/ai-suggestions", summary="AI下一步建议")
async def ai_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基于用户求职数据，生成3条最该做的AI建议"""
    uid = current_user.id
    now = utc_now()
    week_ago = now - timedelta(days=7)

    # 收集上下文
    total_apps = db.query(func.count(JobApplicationPipeline.id)).filter(
        JobApplicationPipeline.user_id == uid,
    ).scalar()

    weekly_apps = db.query(func.count(JobApplicationPipeline.id)).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.create_time >= week_ago,
    ).scalar()

    interviews = db.query(func.count(JobApplicationPipeline.id)).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage.in_(["interview", "offer", "accepted"]),
    ).scalar()

    offers = db.query(func.count(JobApplicationPipeline.id)).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage.in_(["offer", "accepted"]),
    ).scalar()

    stalled = db.query(func.count(JobApplicationPipeline.id)).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage == "applied",
        JobApplicationPipeline.update_time <= now - timedelta(days=7),
    ).scalar()

    upcoming = db.query(func.count(JobApplicationPipeline.id)).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage == "interview",
        JobApplicationPipeline.interview_at >= now,
    ).scalar()

    resumes = db.query(func.count(Resume.id)).filter(
        Resume.user_id == uid, Resume.is_deleted == 0,
    ).scalar()

    response_rate = round(interviews / total_apps * 100, 1) if total_apps > 0 else 0

    suggestions = []

    # 规则引擎生成建议
    if offers > 0:
        suggestions.append({
            "action": "review_offers",
            "title": "处理Offer决策",
            "description": f"你有 {offers} 个Offer待处理，对比薪资和成长空间后尽快决定",
            "priority": "high",
            "link": "/jobs/pipeline/kanban?stage=offer",
        })

    if upcoming > 0:
        suggestions.append({
            "action": "prepare_interview",
            "title": "准备即将到来的面试",
            "description": f"你有 {upcoming} 场面试即将开始，建议用AI模拟面试提前热身",
            "priority": "high",
            "link": "/interview",
        })

    if stalled > 0:
        suggestions.append({
            "action": "follow_up",
            "title": "跟进沉默投递",
            "description": f"有 {stalled} 个投递超7天无回复，考虑发邮件跟进或寻找其他渠道",
            "priority": "medium",
            "link": "/jobs/pipeline/kanban?stage=applied",
        })

    if weekly_apps < 3 and total_apps < 30:
        suggestions.append({
            "action": "apply_more",
            "title": "增加投递量",
            "description": f"本周仅投递 {weekly_apps} 个岗位，建议每天投递3-5个保持活跃度",
            "priority": "medium",
            "link": "/jobs/recommend",
        })

    if response_rate < 20 and total_apps >= 5:
        suggestions.append({
            "action": "optimize_resume",
            "title": "优化简历提升回复率",
            "description": f"当前回复率 {response_rate}%，建议使用AI优化简历匹配度",
            "priority": "medium",
            "link": "/resume",
        })

    if resumes == 0:
        suggestions.append({
            "action": "upload_resume",
            "title": "上传简历",
            "description": "还没有简历，上传后可使用AI优化和匹配推荐",
            "priority": "high",
            "link": "/resume",
        })

    # 确保至少返回3条建议
    if len(suggestions) < 3:
        suggestions.append({
            "action": "browse_jobs",
            "title": "浏览推荐岗位",
            "description": "查看AI根据你的求职目标推荐的最新岗位",
            "priority": "low",
            "link": "/jobs/recommend",
        })

    return ok({
        "context": {
            "total_applications": total_apps,
            "weekly_applications": weekly_apps,
            "response_rate": response_rate,
            "upcoming_interviews": upcoming,
            "stalled_applications": stalled,
        },
        "suggestions": suggestions[:3],
    })
