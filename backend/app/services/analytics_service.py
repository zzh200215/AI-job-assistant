# -*- coding: utf-8 -*-
"""数据分析服务：转化漏斗、留存、关键指标。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.history import AnalysisRecord, Resume
from app.models.interview_session import InterviewSession
from app.models.user import User
from app.models.subscription import SubscriptionOrder, UserSubscription


def get_conversion_funnel(
    db: Session,
    days: int = 30,
) -> dict:
    """
    计算核心转化漏斗。
    每个步骤的值是"做过该动作的独立用户数"。
    """
    since = datetime.utcnow() - timedelta(days=days)

    # 注册用户数
    registered = db.query(func.count(User.id)).filter(
        User.created_at >= since
    ).scalar() or 0

    # 上传过简历的用户数
    uploaded = db.query(func.count(func.distinct(Resume.user_id))).filter(
        Resume.create_time >= since
    ).scalar() or 0

    # 生成过分析的用户数
    analyzed = db.query(func.count(func.distinct(AnalysisRecord.user_id))).filter(
        AnalysisRecord.create_time >= since
    ).scalar() or 0

    # 有过面试会话的用户数
    interviewed = db.query(func.count(func.distinct(InterviewSession.user_id))).filter(
        InterviewSession.created_at >= since
    ).scalar() or 0

    # 有订阅订单的用户数
    subscribed = db.query(func.count(func.distinct(SubscriptionOrder.user_id))).filter(
        SubscriptionOrder.created_at >= since,
        SubscriptionOrder.status == "paid",
    ).scalar() or 0

    total_users = db.query(func.count(User.id)).scalar() or 1

    steps = [
        {"key": "registered", "label": "注册", "count": registered},
        {"key": "uploaded", "label": "上传简历", "count": uploaded},
        {"key": "analyzed", "label": "生成分析", "count": analyzed},
        {"key": "interviewed", "label": "模拟面试", "count": interviewed},
        {"key": "subscribed", "label": "订阅付费", "count": subscribed},
    ]

    # 计算转化率（相对于上一步）
    for i, step in enumerate(steps):
        prev_count = steps[i - 1]["count"] if i > 0 else total_users
        step["rate"] = round(step["count"] / max(prev_count, 1) * 100, 1)

    return {
        "total_users": total_users,
        "period_days": days,
        "steps": steps,
    }


def get_retention(
    db: Session,
    days: int = 30,
) -> dict:
    """
    计算用户留存。
    返回每日活跃用户数和7日/14日/30日留存率。
    """
    now = datetime.utcnow()

    # 每日活跃用户（当天有任意操作的用户）
    # 用注册时间近似估算
    daily_active = []
    for i in range(days):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        active = db.query(func.count(func.distinct(AnalysisRecord.user_id))).filter(
            AnalysisRecord.create_time >= day_start,
            AnalysisRecord.create_time < day_end,
        ).scalar() or 0

        daily_active.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "active_users": active,
        })

    daily_active.reverse()

    # 计算7日/14日/30日留存
    # 以30天前注册的用户为基数，看他们在最近7/14/30天是否有活动
    cohort_start = now - timedelta(days=30)
    cohort = db.query(func.count(User.id)).filter(
        User.created_at >= cohort_start,
        User.created_at < now,
    ).scalar() or 1

    # 7日留存：最近7天活跃的 cohort 用户
    d7_start = now - timedelta(days=7)
    retained_7 = db.query(func.count(func.distinct(AnalysisRecord.user_id))).filter(
        AnalysisRecord.create_time >= d7_start,
    ).scalar() or 0

    # 14日留存
    d14_start = now - timedelta(days=14)
    retained_14 = db.query(func.count(func.distinct(AnalysisRecord.user_id))).filter(
        AnalysisRecord.create_time >= d14_start,
    ).scalar() or 0

    # 30日留存
    d30_start = now - timedelta(days=30)
    retained_30 = db.query(func.count(func.distinct(AnalysisRecord.user_id))).filter(
        AnalysisRecord.create_time >= d30_start,
    ).scalar() or 0

    return {
        "daily_active": daily_active,
        "retention": {
            "d7": round(retained_7 / max(cohort, 1) * 100, 1),
            "d14": round(retained_14 / max(cohort, 1) * 100, 1),
            "d30": round(retained_30 / max(cohort, 1) * 100, 1),
            "cohort_size": cohort,
        },
    }


def get_summary_metrics(db: Session) -> dict:
    """获取关键业务指标汇总。"""
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_resumes = db.query(func.count(Resume.id)).scalar() or 0
    total_analyses = db.query(func.count(AnalysisRecord.id)).scalar() or 0
    total_interviews = db.query(func.count(InterviewSession.id)).scalar() or 0

    pro_users = db.query(func.count(func.distinct(UserSubscription.user_id))).filter(
        UserSubscription.plan_tier == "pro",
        UserSubscription.status == "active",
    ).scalar() or 0

    paid_orders = db.query(func.count(SubscriptionOrder.id)).filter(
        SubscriptionOrder.status == "paid",
    ).scalar() or 0

    return {
        "total_users": total_users,
        "total_resumes": total_resumes,
        "total_analyses": total_analyses,
        "total_interviews": total_interviews,
        "pro_users": pro_users,
        "paid_orders": paid_orders,
    }
