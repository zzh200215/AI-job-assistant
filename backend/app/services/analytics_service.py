"""数据分析服务：转化漏斗、留存、关键指标、租户收入汇总（T4-2）。

T4-2 租户隔离口径：
- `tb_user` 无 `tenant_id`，租户的用户口径以该租户各业务表（简历/分析/面试/订单）
  的 `distinct user_id` 并集近似（这些表 T2-4 已带 `tenant_id`）；
- 其余计数直接按业务表 `tenant_id` 过滤；`tenant_id=None` 保持平台级原行为。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.history import AnalysisRecord, Resume
from app.models.interview_session import InterviewSession
from app.models.subscription import SubscriptionOrder, UserSubscription
from app.models.user import User

# 参与租户用户口径的业务表（均含 tenant_id 与 user_id）
_TENANT_USER_MODELS = [Resume, AnalysisRecord, InterviewSession, SubscriptionOrder]


def _tenant_cond(model, tenant_id: int | None):
    """租户过滤条件；tenant_id=None 返回 None（平台级不过滤）。"""
    if tenant_id is None:
        return None
    return model.tenant_id == tenant_id


def _append_cond(filters: list, cond) -> list:
    if cond is not None:
        filters.append(cond)
    return filters


def _tenant_active_user_ids(
    db: Session,
    tenant_id: int,
    since: datetime | None = None,
    until: datetime | None = None,
) -> set:
    """租户活跃用户 id 集合：跨该租户业务表（简历/分析/面试/订单）的 distinct user_id 并集。

    `tb_user` 无 tenant_id，故用业务表 user_id 并集近似租户用户口径；
    `since`/`until` 限定业务时间窗口（半开区间 [since, until)）。
    """
    queries = []
    for model in _TENANT_USER_MODELS:
        q = db.query(func.distinct(model.user_id).label("uid")).filter(model.tenant_id == tenant_id)
        time_col = getattr(model, "create_time", None) or getattr(model, "created_at", None)
        if since is not None and time_col is not None:
            q = q.filter(time_col >= since)
        if until is not None and time_col is not None:
            q = q.filter(time_col < until)
        queries.append(q)
    if not queries:
        return set()
    compound = queries[0].union(*queries[1:]).subquery()
    return {row[0] for row in db.query(compound.c.uid).all()}


def _tenant_active_user_count(db: Session, tenant_id: int, since: datetime | None = None) -> int:
    """租户活跃用户数：跨该租户业务表 distinct user_id 并集；`since` 限定业务时间。"""
    return len(_tenant_active_user_ids(db, tenant_id, since=since))


def get_conversion_funnel(
    db: Session,
    days: int = 30,
    tenant_id: int | None = None,
) -> dict:
    """
    计算核心转化漏斗。
    每个步骤的值是"做过该动作的独立用户数"；tenant_id 给定时按该租户隔离。
    """
    since = datetime.utcnow() - timedelta(days=days)

    if tenant_id is None:
        registered = db.query(func.count(User.id)).filter(User.created_at >= since).scalar() or 0
        total_users = db.query(func.count(User.id)).scalar() or 1
    else:
        registered = _tenant_active_user_count(db, tenant_id, since=since)
        total_users = _tenant_active_user_count(db, tenant_id) or 1

    # 上传过简历的用户数
    uploaded_f = _append_cond([Resume.create_time >= since], _tenant_cond(Resume, tenant_id))
    uploaded = db.query(func.count(func.distinct(Resume.user_id))).filter(*uploaded_f).scalar() or 0

    # 生成过分析的用户数
    analyzed_f = _append_cond([AnalysisRecord.create_time >= since], _tenant_cond(AnalysisRecord, tenant_id))
    analyzed = db.query(func.count(func.distinct(AnalysisRecord.user_id))).filter(*analyzed_f).scalar() or 0

    # 有过面试会话的用户数
    interviewed_f = _append_cond([InterviewSession.created_at >= since], _tenant_cond(InterviewSession, tenant_id))
    interviewed = db.query(func.count(func.distinct(InterviewSession.user_id))).filter(*interviewed_f).scalar() or 0

    # 有订阅订单的用户数
    subscribed_f = _append_cond(
        [SubscriptionOrder.created_at >= since, SubscriptionOrder.status == "paid"],
        _tenant_cond(SubscriptionOrder, tenant_id),
    )
    subscribed = db.query(func.count(func.distinct(SubscriptionOrder.user_id))).filter(*subscribed_f).scalar() or 0

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
        "tenant_id": tenant_id,
        "steps": steps,
    }


def get_retention(
    db: Session,
    days: int = 30,
    tenant_id: int | None = None,
) -> dict:
    """
    计算用户留存。
    返回每日活跃用户数和7日/14日/30日留存率；tenant_id 给定时按该租户隔离。

    留存口径（修复原「近30天活跃/近30天新增→必然单调、d30≈100%」的定义错误）：
    每个周期 P 取两段独立窗口——
      - 队列窗口 [now-2P, now-P]：该窗口内注册（平台级）或产生业务行为（租户级）的用户为新队列；
      - 活跃窗口 [now-P, now]：队列中在最近 P 天仍有分析行为的用户为「留存」。
    队列与活跃窗口错开，d7/d14/d30 各有独立队列，不再恒等于 ~100%。

    每日活跃按北京时区（UTC+8）分桶：DB 存 naive UTC，先把北京日界换算成 UTC 边界再比较。
    """
    bj_tz = timezone(timedelta(hours=8))
    now_bj = datetime.now(bj_tz)
    now = datetime.utcnow()  # naive UTC，与 DB DateTime 比较对齐

    # 每日活跃用户（当天有分析动作的用户），按北京时区日界分桶
    daily_active = []
    for i in range(days):
        day_start_bj = (now_bj - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_utc = day_start_bj.astimezone(timezone.utc).replace(tzinfo=None)
        day_end_utc = day_start_utc + timedelta(days=1)

        active_f = _append_cond(
            [AnalysisRecord.create_time >= day_start_utc, AnalysisRecord.create_time < day_end_utc],
            _tenant_cond(AnalysisRecord, tenant_id),
        )
        active = db.query(func.count(func.distinct(AnalysisRecord.user_id))).filter(*active_f).scalar() or 0

        daily_active.append(
            {
                "date": day_start_bj.strftime("%Y-%m-%d"),
                "active_users": active,
            }
        )

    daily_active.reverse()

    def _cohort_user_ids(start: datetime, end: datetime) -> set:
        """队列用户 id 集合：平台级按注册时间；租户级按业务表活跃时间。"""
        if tenant_id is None:
            rows = db.query(func.distinct(User.id)).filter(User.created_at >= start, User.created_at < end).all()
            return {row[0] for row in rows}
        return _tenant_active_user_ids(db, tenant_id, since=start, until=end)

    def _retained_count(cohort_ids: set, active_since: datetime) -> int:
        """队列中在 [active_since, now) 有分析行为的用户数。"""
        if not cohort_ids:
            return 0
        f = [
            AnalysisRecord.create_time >= active_since,
            AnalysisRecord.user_id.in_(cohort_ids),
        ]
        f = _append_cond(f, _tenant_cond(AnalysisRecord, tenant_id))
        return db.query(func.count(func.distinct(AnalysisRecord.user_id))).filter(*f).scalar() or 0

    retention: dict[str, float | int] = {}
    for period in (7, 14, 30):
        active_since = now - timedelta(days=period)
        cohort_start = now - timedelta(days=2 * period)
        cohort_ids = _cohort_user_ids(cohort_start, active_since)
        retained = _retained_count(cohort_ids, active_since)
        retention[f"d{period}"] = round(retained / len(cohort_ids) * 100, 1) if cohort_ids else 0.0
        retention[f"d{period}_cohort_size"] = len(cohort_ids)
    retention["cohort_size"] = retention["d30_cohort_size"]

    return {
        "daily_active": daily_active,
        "retention": retention,
        "tenant_id": tenant_id,
    }


def get_summary_metrics(db: Session, tenant_id: int | None = None) -> dict:
    """获取关键业务指标汇总；tenant_id 给定时按该租户隔离。"""
    if tenant_id is None:
        total_users = db.query(func.count(User.id)).scalar() or 0
    else:
        total_users = _tenant_active_user_count(db, tenant_id)

    total_resumes_f = _append_cond([], _tenant_cond(Resume, tenant_id))
    total_resumes = db.query(func.count(Resume.id)).filter(*total_resumes_f).scalar() or 0

    total_analyses_f = _append_cond([], _tenant_cond(AnalysisRecord, tenant_id))
    total_analyses = db.query(func.count(AnalysisRecord.id)).filter(*total_analyses_f).scalar() or 0

    total_interviews_f = _append_cond([], _tenant_cond(InterviewSession, tenant_id))
    total_interviews = db.query(func.count(InterviewSession.id)).filter(*total_interviews_f).scalar() or 0

    pro_users_f = _append_cond(
        [UserSubscription.plan_tier == "pro", UserSubscription.status == "active"],
        _tenant_cond(UserSubscription, tenant_id),
    )
    pro_users = db.query(func.count(func.distinct(UserSubscription.user_id))).filter(*pro_users_f).scalar() or 0

    paid_orders_f = _append_cond(
        [SubscriptionOrder.status == "paid"],
        _tenant_cond(SubscriptionOrder, tenant_id),
    )
    paid_orders = db.query(func.count(SubscriptionOrder.id)).filter(*paid_orders_f).scalar() or 0

    return {
        "total_users": total_users,
        "total_resumes": total_resumes,
        "total_analyses": total_analyses,
        "total_interviews": total_interviews,
        "pro_users": pro_users,
        "paid_orders": paid_orders,
        "tenant_id": tenant_id,
    }


def get_revenue_summary(db: Session, tenant_id: int | None = None, days: int | None = None) -> dict:
    """按租户汇总订单金额（status=paid；订阅与单次支付同表口径）。

    - tenant_id=None → 平台级，按租户分组（items）；
    - tenant_id 给定 → 该租户明细（总收入 + 分套餐）。
    """
    base = [SubscriptionOrder.status == "paid"]
    if days:
        since = datetime.utcnow() - timedelta(days=days)
        base.append(SubscriptionOrder.created_at >= since)

    if tenant_id is not None:
        conds = base + [SubscriptionOrder.tenant_id == tenant_id]
        total = db.query(func.coalesce(func.sum(SubscriptionOrder.amount), 0)).filter(*conds).scalar() or 0
        count = db.query(func.count(SubscriptionOrder.id)).filter(*conds).scalar() or 0
        by_tier_rows = (
            db.query(
                SubscriptionOrder.plan_tier,
                func.coalesce(func.sum(SubscriptionOrder.amount), 0),
                func.count(SubscriptionOrder.id),
            )
            .filter(*conds)
            .group_by(SubscriptionOrder.plan_tier)
            .all()
        )
        return {
            "tenant_id": tenant_id,
            "total_amount": float(total),
            "order_count": count,
            "by_tier": {tier: float(amount) for tier, amount, _ in by_tier_rows},
        }

    rows = (
        db.query(
            SubscriptionOrder.tenant_id,
            func.coalesce(func.sum(SubscriptionOrder.amount), 0),
            func.count(SubscriptionOrder.id),
        )
        .filter(*base)
        .group_by(SubscriptionOrder.tenant_id)
        .all()
    )
    items = [{"tenant_id": tid, "amount": float(amount), "order_count": cnt} for tid, amount, cnt in rows]
    return {
        "items": items,
        "total_amount": sum(item["amount"] for item in items),
        "order_count": sum(item["order_count"] for item in items),
    }
