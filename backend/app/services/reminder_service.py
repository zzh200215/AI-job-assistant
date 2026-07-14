"""
智能订阅与提醒服务

1. 基于求职目标匹配新JD并推送通知
2. 投递超时提醒（7天无进展）
3. 面试时间提醒（提前1天/2小时）
4. Offer截止提醒（提前3天/1天）
"""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.api.notification import create_notification
from app.models.job_pipeline import JobApplicationPipeline
from app.models.job_target import JobTarget
from app.models.user import User
from app.utils.time_helper import utc_now


def check_and_send_reminders(db: Session) -> dict:
    """
    定时任务入口：检查所有用户的提醒并发送通知。
    返回发送统计。
    """
    stats = {
        "interview_reminders": 0,
        "offer_deadline_reminders": 0,
        "follow_up_reminders": 0,
        "new_jd_notifications": 0,
    }

    now = utc_now()
    today_str = now.strftime("%Y-%m-%d")

    # 1. 面试提醒
    stats["interview_reminders"] = _check_interview_reminders(db, now, today_str)

    # 2. Offer截止提醒
    stats["offer_deadline_reminders"] = _check_offer_deadlines(db, now, today_str)

    # 3. 投递跟进提醒
    stats["follow_up_reminders"] = _check_follow_ups(db, now, today_str)

    return stats


def _has_reminder_today(db: Session, user_id: int, reminder_key: str, today_str: str) -> bool:
    """检查今天是否已经发送过相同key的提醒，防重复"""
    from app.models.notification import Notification

    return (
        db.query(Notification)
        .filter(
            Notification.user_id == user_id,
            Notification.type.in_(["interview_reminder", "offer_reminder", "application_update"]),
            Notification.ext_data.op("->>")("reminder_key") == reminder_key,
            Notification.ext_data.op("->>")("reminder_date") == today_str,
        )
        .first()
        is not None
    )


def _check_interview_reminders(db: Session, now, today_str: str) -> int:
    """面试时间提醒：提前1天和2小时"""
    count = 0

    # 查找有即将到来面试的投递
    pipelines = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.stage == "interview",
            JobApplicationPipeline.interview_at.isnot(None),
            JobApplicationPipeline.interview_at > now,
        )
        .all()
    )

    # 预加载用户通知偏好
    user_prefs_cache = {}

    for p in pipelines:
        # 检查用户是否关闭了面试提醒
        prefs = _get_user_notification_prefs(db, p.user_id, user_prefs_cache)
        if not prefs.get("interview_reminder", True):
            continue

        hours_until = (p.interview_at - now).total_seconds() / 3600

        # 提前1天提醒（22-26小时之间）
        if 22 <= hours_until <= 26:
            reminder_key = f"interview_1d_{p.id}"
            if _has_reminder_today(db, p.user_id, reminder_key, today_str):
                continue
            create_notification(
                db,
                user_id=p.user_id,
                type="interview_reminder",
                title=f"面试提醒：明天 {p.interview_at.strftime('%H:%M')} 面试",
                content=f"你明天有一场 {p.company or ''} - {p.title or ''} 的面试"
                f"（第{p.interview_round or 1}轮），请提前准备。",
                link=f"/jobs/{p.id}",
                metadata={
                    "pipeline_id": p.id,
                    "company": p.company,
                    "title": p.title,
                    "interview_at": p.interview_at.isoformat(),
                    "hours_until": round(hours_until, 1),
                    "reminder_key": reminder_key,
                    "reminder_date": today_str,
                },
                auto_commit=False,
            )
            count += 1

        # 提前2小时提醒（1.5-2.5小时之间）
        elif 1.5 <= hours_until <= 2.5:
            reminder_key = f"interview_2h_{p.id}"
            if _has_reminder_today(db, p.user_id, reminder_key, today_str):
                continue
            create_notification(
                db,
                user_id=p.user_id,
                type="interview_reminder",
                title=f"面试即将开始：2小时后 {p.company or ''} 面试",
                content=f"你的 {p.company or ''} - {p.title or ''} 面试将在约2小时后开始，请检查网络/路线准备。",
                link=f"/jobs/{p.id}",
                metadata={
                    "pipeline_id": p.id,
                    "company": p.company,
                    "interview_at": p.interview_at.isoformat(),
                    "hours_until": round(hours_until, 1),
                    "reminder_key": reminder_key,
                    "reminder_date": today_str,
                },
                auto_commit=False,
            )
            count += 1

    if count > 0:
        db.commit()
    return count


def _check_offer_deadlines(db: Session, now, today_str: str) -> int:
    """Offer截止提醒：提前3天和1天"""
    count = 0

    pipelines = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.stage == "offer",
            JobApplicationPipeline.offer_deadline.isnot(None),
            JobApplicationPipeline.offer_deadline > now,
        )
        .all()
    )

    user_prefs_cache = {}

    for p in pipelines:
        prefs = _get_user_notification_prefs(db, p.user_id, user_prefs_cache)
        if not prefs.get("offer_reminder", True):
            continue

        days_until = (p.offer_deadline - now).days

        if 2 <= days_until <= 3:
            reminder_key = f"offer_3d_{p.id}"
            if _has_reminder_today(db, p.user_id, reminder_key, today_str):
                continue
            create_notification(
                db,
                user_id=p.user_id,
                type="offer_reminder",
                title=f"Offer即将到期：{p.company or ''} 还有3天",
                content=f"你来自 {p.company or ''} 的Offer将在 {p.offer_deadline.strftime('%m月%d日')} 到期，"
                f"请尽快决定是否接受。",
                link=f"/jobs/{p.id}",
                metadata={
                    "pipeline_id": p.id,
                    "company": p.company,
                    "offer_deadline": p.offer_deadline.isoformat(),
                    "days_until": days_until,
                    "reminder_key": reminder_key,
                    "reminder_date": today_str,
                },
                auto_commit=False,
            )
            count += 1
        elif 0 < days_until <= 1:
            reminder_key = f"offer_1d_{p.id}"
            if _has_reminder_today(db, p.user_id, reminder_key, today_str):
                continue
            create_notification(
                db,
                user_id=p.user_id,
                type="offer_reminder",
                title=f"Offer明天到期！{p.company or ''}",
                content=f"你来自 {p.company or ''} 的Offer明天就到期了，请务必今天做出决定！",
                link=f"/jobs/{p.id}",
                metadata={
                    "pipeline_id": p.id,
                    "company": p.company,
                    "offer_deadline": p.offer_deadline.isoformat(),
                    "days_until": days_until,
                    "reminder_key": reminder_key,
                    "reminder_date": today_str,
                },
                auto_commit=False,
            )
            count += 1

    if count > 0:
        db.commit()
    return count


def _check_follow_ups(db: Session, now, today_str: str) -> int:
    """投递跟进提醒：7天无进展"""
    week_ago = now - timedelta(days=7)
    count = 0

    # 查找7天前投递但仍停留在 applied 阶段的
    pipelines = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.stage == "applied",
            JobApplicationPipeline.update_time <= week_ago,
        )
        .all()
    )

    user_prefs_cache = {}

    for p in pipelines:
        prefs = _get_user_notification_prefs(db, p.user_id, user_prefs_cache)
        if not prefs.get("follow_up", True):
            continue

        days_since = (now - p.update_time).days if p.update_time else 0
        # 每个投递每周最多提醒一次
        reminder_key = f"followup_{p.id}_w{(now.isocalendar()[1])}"
        if _has_reminder_today(db, p.user_id, reminder_key, today_str):
            continue
        create_notification(
            db,
            user_id=p.user_id,
            type="application_update",
            title=f"投递已 {days_since} 天无回复：{p.company or ''}",
            content=f"你投递的 {p.company or ''} - {p.title or ''} 已经过去 {days_since} 天"
            f"没有进展，建议：\n1. 检查邮件是否在垃圾箱\n2. 考虑跟进联系HR\n3. 继续投递其他机会",
            link=f"/jobs/{p.id}",
            metadata={
                "pipeline_id": p.id,
                "company": p.company,
                "stage": p.stage,
                "days_since_update": days_since,
                "reminder_key": reminder_key,
                "reminder_date": today_str,
            },
            auto_commit=False,
        )
        count += 1

    if count > 0:
        db.commit()
    return count


def match_new_jds_for_target(db: Session, target: JobTarget, limit: int = 10) -> list:
    """
    根据求职目标匹配新JD。
    简单关键词匹配，后续可接入向量检索。
    """
    from sqlalchemy import or_

    from app.models.history import JobDescription
    from app.models.job_recommend import JobBookmark

    q = db.query(JobDescription)

    # 按岗位关键词匹配
    position = target.position or target.name
    if position:
        q = q.filter(JobDescription.title.contains(position))

    # 按城市过滤
    if target.cities:
        city_filters = [JobDescription.location.contains(c) for c in target.cities[:3]]
        q = q.filter(or_(*city_filters))

    # 按行业过滤
    if target.industry:
        q = q.filter(JobDescription.industry.contains(target.industry))

    # 排除已收藏/不感兴趣的
    bookmarked_jd_ids = {
        row.jd_id for row in db.query(JobBookmark.jd_id).filter(JobBookmark.user_id == target.user_id).all()
    }

    # 排除已投递的
    applied_jd_ids = {
        row.jd_id
        for row in db.query(JobApplicationPipeline.jd_id)
        .filter(
            JobApplicationPipeline.user_id == target.user_id,
        )
        .all()
    }

    exclude_ids = bookmarked_jd_ids | applied_jd_ids

    results = q.order_by(JobDescription.create_time.desc()).limit(limit * 3).all()
    matched = [jd for jd in results if jd.id not in exclude_ids][:limit]

    return matched


def send_new_jd_notifications(db: Session, user_id: int, target_id: int = None) -> int:
    """为用户发送新JD推送通知"""
    # 检查用户是否开启了JD推送
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return 0
    prefs = user.get_notification_preferences()
    if prefs.get("jd_push_frequency", "daily") == "never" or not prefs.get("jd_push", True):
        return 0

    q = db.query(JobTarget).filter(
        JobTarget.user_id == user_id,
        JobTarget.status == "active",
    )
    if target_id:
        q = q.filter(JobTarget.id == target_id)

    targets = q.all()
    count = 0

    for target in targets:
        matched_jds = match_new_jds_for_target(db, target, limit=5)
        if not matched_jds:
            continue

        jd_summaries = []
        for jd in matched_jds:
            jd_summaries.append(f"- {jd.title} @ {jd.company} ({jd.location})")

        create_notification(
            db,
            user_id=user_id,
            type="recommendation",
            title=f"新职位推荐：{target.name}",
            content=f"根据你的求职目标「{target.name}」，发现 {len(matched_jds)} 个新机会：\n"
            + "\n".join(jd_summaries),
            link="/jobs/bookmarks/list",
            metadata={
                "target_id": target.id,
                "jd_ids": [jd.id for jd in matched_jds],
                "match_count": len(matched_jds),
            },
        )
        count += 1

    return count


def _get_user_notification_prefs(db: Session, user_id: int, cache: dict) -> dict:
    """获取用户通知偏好，带缓存"""
    if user_id not in cache:
        user = db.query(User).filter(User.id == user_id).first()
        cache[user_id] = user.get_notification_preferences() if user else {}
    return cache[user_id]
