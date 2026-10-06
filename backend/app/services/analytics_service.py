"""数据分析服务：转化漏斗、留存、关键指标、收入汇总（T4-2 起，2026-10-06 起平台单口径）。

2026-10-06 真删企业侧第六增量（D136，§10.32 他点「整族拆到底」）之前，这四个函数都带一个
可选的 `tenant_id`：给定时走"租户口径"那一条岔路——`tb_user` 没有 `tenant_id`，所以租户的
"注册用户数"是用四张业务表的 `distinct user_id` 并集**近似**出来的（那个近似本身就是二手口径）。
租户那一级随 organization 一起出树，现在只有平台一条路：`User` 直接计数，业务表直接过滤时间窗。

响应里也拿掉了 `tenant_id` 回声键与"按租户分组"的 `items` 列表——全仓（后端与前端）没有任何读者，
`Overview.vue` 只读 `summary.{pro_users,total_users,paid_orders}`、`revenue.total_amount`、
`funnel.steps[]`。收入那格换成按套餐的 `by_tier`：它是同一条查询本来就有的另一维分解，而且不租户。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.history import AnalysisRecord, Resume
from app.models.interview_session import InterviewSession
from app.models.subscription import SubscriptionOrder, UserSubscription
from app.models.user import User


def get_conversion_funnel(db: Session, days: int = 30) -> dict:
    """核心转化漏斗：每一步是"做过该动作的独立用户数"。"""
    since = datetime.utcnow() - timedelta(days=days)

    registered = db.query(func.count(User.id)).filter(User.created_at >= since).scalar() or 0
    total_users = db.query(func.count(User.id)).scalar() or 1
    uploaded = db.query(func.count(func.distinct(Resume.user_id))).filter(Resume.create_time >= since).scalar() or 0
    analyzed = (
        db.query(func.count(func.distinct(AnalysisRecord.user_id))).filter(AnalysisRecord.create_time >= since).scalar()
        or 0
    )
    interviewed = (
        db.query(func.count(func.distinct(InterviewSession.user_id)))
        .filter(InterviewSession.created_at >= since)
        .scalar()
        or 0
    )
    subscribed = (
        db.query(func.count(func.distinct(SubscriptionOrder.user_id)))
        .filter(SubscriptionOrder.created_at >= since, SubscriptionOrder.status == "paid")
        .scalar()
        or 0
    )

    steps = [
        {"key": "registered", "label": "注册", "count": registered},
        {"key": "uploaded", "label": "上传简历", "count": uploaded},
        {"key": "analyzed", "label": "生成分析", "count": analyzed},
        {"key": "interviewed", "label": "模拟面试", "count": interviewed},
        {"key": "subscribed", "label": "订阅付费", "count": subscribed},
    ]

    # 转化率相对上一步；第一步相对总用户数
    for i, step in enumerate(steps):
        prev_count = steps[i - 1]["count"] if i > 0 else total_users
        step["rate"] = round(step["count"] / max(prev_count, 1) * 100, 1)

    return {
        "total_users": total_users,
        "period_days": days,
        "steps": steps,
    }


def get_retention(db: Session, days: int = 30) -> dict:
    """每日活跃用户数与 7/14/30 日留存率。

    留存口径（修复原「近30天活跃/近30天新增→必然单调、d30≈100%」的定义错误）：
    每个周期 P 取两段独立窗口——
      - 队列窗口 [now-2P, now-P]：该窗口内注册的用户为新队列；
      - 活跃窗口 [now-P, now]：队列中在最近 P 天仍有分析行为的用户为「留存」。
    队列与活跃窗口错开，d7/d14/d30 各有独立队列，不再恒等于 ~100%。

    每日活跃按北京时区（UTC+8）分桶：DB 存 naive UTC，先把北京日界换算成 UTC 边界再比较。
    """
    bj_tz = timezone(timedelta(hours=8))
    now_bj = datetime.now(bj_tz)
    now = datetime.utcnow()  # naive UTC，与 DB DateTime 比较对齐

    daily_active = []
    for i in range(days):
        day_start_bj = (now_bj - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start_bj.astimezone(timezone.utc).replace(tzinfo=None)
        day_end_utc = day_start_utc + timedelta(days=1)

        active = (
            db.query(func.count(func.distinct(AnalysisRecord.user_id)))
            .filter(AnalysisRecord.create_time >= day_start_utc, AnalysisRecord.create_time < day_end_utc)
            .scalar()
            or 0
        )

        daily_active.append(
            {
                "date": day_start_bj.strftime("%Y-%m-%d"),
                "active_users": active,
            }
        )

    daily_active.reverse()

    retention: dict[str, float | int] = {}
    for period in (7, 14, 30):
        active_since = now - timedelta(days=period)
        cohort_start = now - timedelta(days=2 * period)
        cohort_ids = {
            row[0]
            for row in db.query(func.distinct(User.id))
            .filter(User.created_at >= cohort_start, User.created_at < active_since)
            .all()
        }
        if cohort_ids:
            retained = (
                db.query(func.count(func.distinct(AnalysisRecord.user_id)))
                .filter(
                    AnalysisRecord.create_time >= active_since,
                    AnalysisRecord.user_id.in_(cohort_ids),
                )
                .scalar()
                or 0
            )
        else:
            retained = 0
        retention[f"d{period}"] = round(retained / len(cohort_ids) * 100, 1) if cohort_ids else 0.0
        retention[f"d{period}_cohort_size"] = len(cohort_ids)
    retention["cohort_size"] = retention["d30_cohort_size"]

    return {
        "daily_active": daily_active,
        "retention": retention,
    }


def get_summary_metrics(db: Session) -> dict:
    """关键业务指标汇总（平台口径）。"""
    return {
        "total_users": db.query(func.count(User.id)).scalar() or 0,
        "total_resumes": db.query(func.count(Resume.id)).scalar() or 0,
        "total_analyses": db.query(func.count(AnalysisRecord.id)).scalar() or 0,
        "total_interviews": db.query(func.count(InterviewSession.id)).scalar() or 0,
        "pro_users": db.query(func.count(func.distinct(UserSubscription.user_id)))
        .filter(UserSubscription.plan_tier == "pro", UserSubscription.status == "active")
        .scalar()
        or 0,
        "paid_orders": db.query(func.count(SubscriptionOrder.id)).filter(SubscriptionOrder.status == "paid").scalar()
        or 0,
    }


def get_revenue_summary(db: Session, days: int | None = None) -> dict:
    """收入汇总（status=paid；订阅与单次支付同表口径），按套餐给一维分解。"""
    base = [SubscriptionOrder.status == "paid"]
    if days:
        since = datetime.utcnow() - timedelta(days=days)
        base.append(SubscriptionOrder.created_at >= since)

    total = db.query(func.coalesce(func.sum(SubscriptionOrder.amount), 0)).filter(*base).scalar() or 0
    count = db.query(func.count(SubscriptionOrder.id)).filter(*base).scalar() or 0
    by_tier_rows = (
        db.query(
            SubscriptionOrder.plan_tier,
            func.coalesce(func.sum(SubscriptionOrder.amount), 0),
            func.count(SubscriptionOrder.id),
        )
        .filter(*base)
        .group_by(SubscriptionOrder.plan_tier)
        .all()
    )
    return {
        "total_amount": float(total),
        "order_count": count,
        "by_tier": {tier: float(amount) for tier, amount, _ in by_tier_rows},
    }
