# -*- coding: utf-8 -*-
"""求职时间线 API — 可视化求职历程"""
from datetime import timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import JobDescription
from app.models.interview_session import InterviewSession
from app.models.job_journal import JobJournal
from app.models.job_pipeline import JobApplicationPipeline
from app.models.notification import Notification
from app.models.user import User
from app.utils.response import ok
from app.utils.time_helper import utc_now

router = APIRouter()


@router.get("/events", summary="求职时间线事件列表")
async def timeline_events(
    start_date: str = Query("", description="开始日期 YYYY-MM-DD"),
    end_date: str = Query("", description="结束日期 YYYY-MM-DD"),
    event_types: str = Query("", description="事件类型过滤，逗号分隔: application/interview/offer/journal"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    按时间顺序聚合所有求职相关事件，形成时间线。
    事件来源：投递记录、面试、Offer、日记/笔记。
    """
    uid = current_user.id
    now = utc_now()
    events = []

    # 解析日期范围
    from datetime import datetime
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else now - timedelta(days=90)
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) if end_date else now + timedelta(days=1)
    except ValueError:
        start = now - timedelta(days=90)
        end = now + timedelta(days=1)

    type_filter = set(event_types.split(",")) if event_types else set()

    # 1. 投递事件
    if not type_filter or "application" in type_filter:
        pipelines = (
            db.query(JobApplicationPipeline)
            .filter(
                JobApplicationPipeline.user_id == uid,
                JobApplicationPipeline.create_time >= start,
                JobApplicationPipeline.create_time <= end,
            )
            .order_by(JobApplicationPipeline.create_time.desc())
            .all()
        )
        for p in pipelines:
            # 投递创建事件
            events.append({
                "date": p.create_time.isoformat() if p.create_time else None,
                "type": "application_created",
                "category": "application",
                "title": f"投递了 {p.company or ''} - {p.title or '未知岗位'}",
                "data": {
                    "pipeline_id": p.id,
                    "jd_id": p.jd_id,
                    "stage": p.stage,
                    "company": p.company,
                    "title": p.title,
                },
            })

            # 阶段变化事件
            for h in (p.stage_history or []):
                at_str = h.get("at", "")
                if not at_str:
                    continue
                try:
                    at = datetime.fromisoformat(at_str.replace("Z", "+00:00"))
                    if at < start or at > end:
                        continue
                except (ValueError, TypeError):
                    continue

                stage = h.get("stage", "")
                from_stage = h.get("from_stage", "")
                stage_labels = {
                    "applied": "已投递",
                    "written_test": "笔试",
                    "interview": "面试",
                    "offer": "收到Offer",
                    "accepted": "已接受",
                    "rejected": "未通过",
                    "withdrawn": "已撤回",
                }
                events.append({
                    "date": at_str,
                    "type": f"stage_{stage}",
                    "category": "application",
                    "title": f"{p.company or ''} - {p.title or ''} → {stage_labels.get(stage, stage)}",
                    "data": {
                        "pipeline_id": p.id,
                        "from_stage": from_stage,
                        "to_stage": stage,
                        "company": p.company,
                        "title": p.title,
                    },
                })

    # 2. 面试事件
    if not type_filter or "interview" in type_filter:
        # 即将到来的面试
        upcoming = (
            db.query(JobApplicationPipeline)
            .filter(
                JobApplicationPipeline.user_id == uid,
                JobApplicationPipeline.stage == "interview",
                JobApplicationPipeline.interview_at.isnot(None),
            )
            .order_by(JobApplicationPipeline.interview_at.desc())
            .all()
        )
        for p in upcoming:
            events.append({
                "date": p.interview_at.isoformat() if p.interview_at else None,
                "type": "interview_scheduled",
                "category": "interview",
                "title": f"面试 {p.company or ''} - {p.title or ''}",
                "data": {
                    "pipeline_id": p.id,
                    "company": p.company,
                    "title": p.title,
                    "interview_at": p.interview_at.isoformat() if p.interview_at else None,
                    "interview_round": p.interview_round,
                },
            })

        # AI模拟面试
        mock_sessions = (
            db.query(InterviewSession)
            .filter(
                InterviewSession.user_id == uid,
                InterviewSession.created_at >= start,
                InterviewSession.created_at <= end,
            )
            .order_by(InterviewSession.created_at.desc())
            .all()
        )
        for s in mock_sessions:
            score = (s.evaluation or {}).get("overall_score", 0)
            events.append({
                "date": s.created_at.isoformat() if s.created_at else None,
                "type": "mock_interview",
                "category": "interview",
                "title": f"AI模拟面试 {'得分 ' + str(score) if score else ''}",
                "data": {
                    "session_id": s.id,
                    "interview_type": s.interview_type,
                    "score": score,
                },
            })

    # 3. Offer事件
    if not type_filter or "offer" in type_filter:
        offers = (
            db.query(JobApplicationPipeline)
            .filter(
                JobApplicationPipeline.user_id == uid,
                JobApplicationPipeline.stage.in_(["offer", "accepted"]),
            )
            .order_by(JobApplicationPipeline.update_time.desc())
            .all()
        )
        for p in offers:
            events.append({
                "date": p.update_time.isoformat() if p.update_time else None,
                "type": "offer_received" if p.stage == "offer" else "offer_accepted",
                "category": "offer",
                "title": f"{'收到' if p.stage == 'offer' else '接受'}Offer: {p.company or ''} - {p.title or ''}",
                "data": {
                    "pipeline_id": p.id,
                    "company": p.company,
                    "title": p.title,
                    "salary_offered": p.salary_offered,
                    "deadline": p.offer_deadline.isoformat() if p.offer_deadline else None,
                },
            })

    # 4. 日记事件
    if not type_filter or "journal" in type_filter:
        journals = (
            db.query(JobJournal)
            .filter(
                JobJournal.user_id == uid,
                JobJournal.created_at >= start,
                JobJournal.created_at <= end,
            )
            .order_by(JobJournal.created_at.desc())
            .all()
        )
        type_labels = {
            "note": "笔记",
            "interview_log": "面试记录",
            "offer_review": "Offer复盘",
            "reflection": "反思",
        }
        for j in journals:
            events.append({
                "date": j.created_at.isoformat() if j.created_at else None,
                "type": f"journal_{j.entry_type}",
                "category": "journal",
                "title": f"{type_labels.get(j.entry_type, j.entry_type)}: {j.title}",
                "data": {
                    "journal_id": j.id,
                    "entry_type": j.entry_type,
                    "mood": j.mood,
                    "rating": j.rating,
                },
            })

    # 按日期排序
    events.sort(key=lambda e: e.get("date") or "", reverse=True)

    total = len(events)
    paged = events[(page - 1) * page_size: page * page_size]

    return ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "events": paged,
    })


@router.get("/by-date", summary="按日期聚合的时间线")
async def timeline_by_date(
    start_date: str = Query("", description="开始日期 YYYY-MM-DD"),
    end_date: str = Query("", description="结束日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按日期分组的时间线视图，每天聚合所有事件。"""
    uid = current_user.id
    now = utc_now()

    from datetime import datetime
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else now - timedelta(days=30)
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) if end_date else now + timedelta(days=1)
    except ValueError:
        start = now - timedelta(days=30)
        end = now + timedelta(days=1)

    # 复用事件查询逻辑（简化版，只取最近数据）
    events = []

    # 投递事件
    pipelines = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == uid,
            JobApplicationPipeline.create_time >= start,
            JobApplicationPipeline.create_time <= end,
        )
        .all()
    )
    for p in pipelines:
        events.append({
            "date": p.create_time.strftime("%Y-%m-%d") if p.create_time else "",
            "type": "application",
            "title": f"投递 {p.company or ''} - {p.title or ''}",
            "stage": p.stage,
        })
        for h in (p.stage_history or []):
            at_str = h.get("at", "")
            if at_str:
                try:
                    at = datetime.fromisoformat(at_str.replace("Z", "+00:00"))
                    if start <= at <= end:
                        stage = h.get("stage", "")
                        events.append({
                            "date": at.strftime("%Y-%m-%d"),
                            "type": "stage_change",
                            "title": f"{p.company or ''} → {stage}",
                            "stage": stage,
                        })
                except (ValueError, TypeError):
                    pass

    # 面试
    interviews = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.user_id == uid,
            JobApplicationPipeline.stage == "interview",
            JobApplicationPipeline.interview_at.isnot(None),
        )
        .all()
    )
    for p in interviews:
        if p.interview_at:
            events.append({
                "date": p.interview_at.strftime("%Y-%m-%d"),
                "type": "interview",
                "title": f"面试 {p.company or ''} - {p.title or ''}",
            })

    # 日记
    journals = (
        db.query(JobJournal)
        .filter(
            JobJournal.user_id == uid,
            JobJournal.created_at >= start,
            JobJournal.created_at <= end,
        )
        .all()
    )
    for j in journals:
        events.append({
            "date": j.created_at.strftime("%Y-%m-%d") if j.created_at else "",
            "type": "journal",
            "title": j.title,
            "mood": j.mood,
        })

    # 按日期分组
    by_date = defaultdict(list)
    for e in events:
        by_date[e["date"]].append(e)

    # 排序
    sorted_dates = sorted(by_date.keys(), reverse=True)

    # 统计
    total_events = len(events)
    unique_days = len(sorted_dates)

    return ok({
        "total_events": total_events,
        "unique_days": unique_days,
        "timeline": [
            {"date": date, "events": by_date[date], "count": len(by_date[date])}
            for date in sorted_dates
        ],
    })


@router.get("/story", summary="求职故事生成")
async def generate_story(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    基于求职历程自动生成一段求职故事/总结。
    适合分享或回顾。
    """
    uid = current_user.id

    # 统计
    total_applications = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
    ).count()

    active = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage.in_(["applied", "written_test", "interview"]),
    ).count()

    interviews = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage.in_(["interview", "offer", "accepted"]),
    ).count()

    offers = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage.in_(["offer", "accepted"]),
    ).count()

    rejected = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage == "rejected",
    ).count()

    accepted = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage == "accepted",
    ).count()

    # 日期范围
    first_app = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
    ).order_by(JobApplicationPipeline.create_time.asc()).first()

    latest_app = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
    ).order_by(JobApplicationPipeline.update_time.desc()).first()

    # 日记统计
    journal_count = db.query(JobJournal).filter(
        JobJournal.user_id == uid,
    ).count()

    # 模拟面试次数
    mock_count = db.query(InterviewSession).filter(
        InterviewSession.user_id == uid,
    ).count()

    # 生成故事
    duration_days = 0
    if first_app and latest_app and first_app.create_time and latest_app.update_time:
        duration_days = (latest_app.update_time - first_app.create_time).days

    story_parts = []
    story_parts.append(f"求职旅程已持续 {duration_days} 天")
    story_parts.append(f"共投递 {total_applications} 个岗位")
    if interviews > 0:
        story_parts.append(f"获得 {interviews} 次面试机会")
    if offers > 0:
        story_parts.append(f"收到 {offers} 个Offer")
    if accepted > 0:
        story_parts.append(f"最终接受 {accepted} 个Offer")
    if rejected > 0:
        story_parts.append(f"经历了 {rejected} 次拒绝")
    if mock_count > 0:
        story_parts.append(f"完成 {mock_count} 次AI模拟面试")
    if journal_count > 0:
        story_parts.append(f"记录了 {journal_count} 篇求职笔记")

    # 计算关键指标
    response_rate = round(interviews / total_applications * 100, 1) if total_applications > 0 else 0
    offer_rate = round(offers / total_applications * 100, 1) if total_applications > 0 else 0

    # 鼓励语
    if accepted > 0:
        encouragement = "恭喜！你的坚持得到了回报！"
    elif offers > 0:
        encouragement = "Offer在手，离成功只差一步！"
    elif interviews > 0:
        encouragement = "面试机会已来，全力以赴！"
    elif total_applications > 10:
        encouragement = "投递量大，保持耐心，回应终会来！"
    elif total_applications > 0:
        encouragement = "好的开始是成功的一半，继续加油！"
    else:
        encouragement = "旅程尚未开始，现在就行动吧！"

    return ok({
        "story": "，".join(story_parts) + "。",
        "encouragement": encouragement,
        "metrics": {
            "duration_days": duration_days,
            "total_applications": total_applications,
            "active_applications": active,
            "interviews": interviews,
            "offers": offers,
            "accepted": accepted,
            "rejected": rejected,
            "response_rate": response_rate,
            "offer_rate": offer_rate,
            "mock_interviews": mock_count,
            "journal_entries": journal_count,
        },
        "milestones": _extract_milestones(uid, db),
    })


def _extract_milestones(uid: int, db: Session) -> list:
    """提取关键里程碑"""
    milestones = []

    # 第一个投递
    first = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
    ).order_by(JobApplicationPipeline.create_time.asc()).first()
    if first and first.create_time:
        milestones.append({
            "date": first.create_time.isoformat(),
            "type": "first_application",
            "title": "开始求职",
            "description": f"投递了第一个岗位: {first.company or ''} - {first.title or ''}",
        })

    # 第一个面试
    first_interview = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage.in_(["interview", "offer", "accepted"]),
    ).order_by(JobApplicationPipeline.update_time.asc()).first()
    if first_interview and first_interview.update_time:
        milestones.append({
            "date": first_interview.update_time.isoformat(),
            "type": "first_interview",
            "title": "获得首个面试",
            "description": f"{first_interview.company or ''} - {first_interview.title or ''}",
        })

    # 第一个Offer
    first_offer = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == uid,
        JobApplicationPipeline.stage.in_(["offer", "accepted"]),
    ).order_by(JobApplicationPipeline.update_time.asc()).first()
    if first_offer and first_offer.update_time:
        milestones.append({
            "date": first_offer.update_time.isoformat(),
            "type": "first_offer",
            "title": "收到首个Offer",
            "description": f"{first_offer.company or ''} - {first_offer.title or ''}",
        })

    return milestones
