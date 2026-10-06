"""订阅与权益服务层：套餐定义、权益矩阵、额度校验/消耗/重置。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.subscription import (
    OrderStatus,
    SubscriptionOrder,
    SubscriptionPlan,
    UserSubscription,
)
from app.models.user import User
from app.services.audit_service import write_audit_log
from app.utils.time_helper import utc_now, utc_now_naive

# ============================================================
# 权益矩阵（硬编码，与 DB  SubscriptionPlan.features 镜像）
# 字段说明：
#   resume_limit: -1=不限, N=上限
#   daily_analysis_limit: 每日分析次数
#   daily_interview_limit: 每日模拟面试次数
#   daily_recommendation_limit: 每日推荐次数
#   can_export_full_report: 是否可导出完整报告
#   can_use_deep_analysis: 是否可用深度 AI 分析
#   can_use_ats_check: 是否可用 ATS 检测
#   can_use_offer_decision: 是否可用 Offer 决策
#   can_use_salary_negotiation: 是否可用谈薪建议
# ============================================================

TIER_FEATURES = {
    "free": {
        "resume_limit": 1,
        "daily_analysis_limit": 3,
        "daily_interview_limit": 5,
        "daily_recommendation_limit": 10,
        "can_export_full_report": False,
        "can_use_deep_analysis": False,
        "can_use_ats_check": False,
        "can_use_offer_decision": False,
        "can_use_salary_negotiation": False,
    },
    "pro": {
        "resume_limit": -1,
        "daily_analysis_limit": 50,
        "daily_interview_limit": 100,
        "daily_recommendation_limit": 200,
        "can_export_full_report": True,
        "can_use_deep_analysis": True,
        "can_use_ats_check": True,
        "can_use_offer_decision": True,
        "can_use_salary_negotiation": True,
    },
    "enterprise": {
        "resume_limit": -1,
        "daily_analysis_limit": -1,
        "daily_interview_limit": -1,
        "daily_recommendation_limit": -1,
        "can_export_full_report": True,
        "can_use_deep_analysis": True,
        "can_use_ats_check": True,
        "can_use_offer_decision": True,
        "can_use_salary_negotiation": True,
    },
}

# 按天重置的额度 key 列表
DAILY_QUOTA_KEYS = ["daily_analysis", "daily_interview", "daily_recommendation"]

# 平台默认套餐价格（分），与 SubscriptionPlan 表（tenant_id IS NULL）互为数据源；
# get_plans 优先读 DB，DB 无平台默认行时回落本常量。
DEFAULT_PLAN_PRICES = {
    "free": (0, 0),  # (monthly, yearly)
    "pro": (9900, 99900),
    "enterprise": (0, 0),
}

DEFAULT_PLAN_NAMES = {"free": "免费版", "pro": "Pro 版", "enterprise": "企业版"}

DEFAULT_PLAN_SORT = {"free": 0, "pro": 1, "enterprise": 2}


def get_plans(db: Session) -> list[dict]:
    """套餐列表：平台配置行（`tenant_id IS NULL`）覆盖内置矩阵。

    2026-10-06 真删企业侧第六增量（D136）之前这里是两级来源："这个租户自定义的 tier" 优先、
    再回落平台默认。租户那一级随 `POST /subscription/admin/plans`（它要求请求体带 `tenant_id`，
    所以历史上只能造"租户自定义"行）一起出树，现在只剩平台 → 内置。

    规则（按 tier 粒度合并）：
    1. 平台默认行（DB 中 `tenant_id IS NULL` 且 is_active）覆盖名称/价格/排序；
    2. 没有平台行就用硬编码 `TIER_FEATURES` + `DEFAULT_PLAN_PRICES`；
    3. 平台行的 features 与默认权益矩阵做浅合并（缺省键保留默认权益，避免配置不全丢权益）。
    """
    platform = {
        p.tier: p
        for p in db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.tenant_id.is_(None), SubscriptionPlan.is_active == 1)
        .all()
    }

    plans: list[dict] = []
    for tier, default_features in TIER_FEATURES.items():
        monthly, yearly = DEFAULT_PLAN_PRICES.get(tier, (0, 0))
        name = DEFAULT_PLAN_NAMES.get(tier, tier)
        sort_order = DEFAULT_PLAN_SORT.get(tier, 0)

        source = platform.get(tier)
        if source is not None:
            name = source.name
            monthly = source.price_monthly if source.price_monthly is not None else monthly
            yearly = source.price_yearly if source.price_yearly is not None else yearly
            sort_order = source.sort_order if source.sort_order is not None else sort_order
            if source.features:
                default_features = {**default_features, **source.features}

        plans.append(
            {
                "tier": tier,
                "name": name,
                "price_monthly": float(monthly),
                "price_yearly": float(yearly),
                "features": default_features,
                "sort_order": sort_order,
            }
        )

    plans.sort(key=lambda p: p["sort_order"])
    return plans


def get_plan_price(db: Session, tier: str, period: str = "monthly") -> int:
    """指定 tier 的套餐价格（分）；找不到回落平台默认价。"""
    for plan in get_plans(db):
        if plan["tier"] == tier:
            return int(plan["price_yearly" if period == "yearly" else "price_monthly"])
    monthly, yearly = DEFAULT_PLAN_PRICES.get(tier, (0, 0))
    return yearly if period == "yearly" else monthly


def get_user_plan_tier(db: Session, user_id: int) -> str:
    """获取用户当前套餐 tier，默认 free。"""
    sub = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == user_id,
            UserSubscription.status == "active",
        )
        .order_by(UserSubscription.id.desc())
        .first()
    )
    # DB DateTime 列无时区，读回为 naive，必须与 naive 当前时间比较，否则抛 TypeError
    if sub and sub.end_at and sub.end_at > utc_now_naive():
        return sub.plan_tier
    return "free"


def _effective_features(db: Session, tier: str) -> dict:
    """用户视角的有效权益：平台自定义套餐的 features 覆盖硬编码默认矩阵。

    get_plans 已把平台行 features 与 TIER_FEATURES 做浅合并（缺省键保留默认权益），
    因此直接取 get_plans 结果即得自定义套餐真实权益（修复自定义套餐权益读硬编码不生效）。
    """
    for plan in get_plans(db):
        if plan["tier"] == tier:
            return dict(plan["features"])
    return dict(TIER_FEATURES.get(tier, TIER_FEATURES["free"]))


def get_user_features(db: Session, user_id: int) -> dict:
    """获取用户当前套餐的完整权益配置（含租户/平台自定义覆盖）。"""
    tier = get_user_plan_tier(db, user_id)
    return _effective_features(db, tier)


def get_or_create_subscription(db: Session, user_id: int) -> UserSubscription:
    """获取或创建用户订阅记录。"""
    sub = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == user_id,
        )
        .order_by(UserSubscription.id.desc())
        .first()
    )
    if not sub:
        sub = UserSubscription(
            user_id=user_id,
            plan_tier="free",
            status="active",
            start_at=utc_now_naive(),
            quota_usage=dict.fromkeys(DAILY_QUOTA_KEYS, 0),
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return sub


def reset_daily_quota_if_needed(sub: UserSubscription) -> bool:
    """检查是否需要重置每日额度（跨天），返回是否重置过。"""
    now = utc_now_naive()  # 与 DB 读回的 naive quota_reset_at 对齐
    if sub.quota_reset_at is None:
        sub.quota_reset_at = now
        sub.quota_usage = dict.fromkeys(DAILY_QUOTA_KEYS, 0)
        return True
    last_reset = sub.quota_reset_at
    if last_reset.date() < now.date():
        sub.quota_reset_at = now
        sub.quota_usage = dict.fromkeys(DAILY_QUOTA_KEYS, 0)
        return True
    return False


# ============================================================
# 公开校验函数 — 供各业务路由调用
# ============================================================


def check_quota(
    db: Session,
    user_id: int,
    resource: str,
    consume: bool = False,
) -> tuple[bool, str, dict]:
    """
    校验用户是否有权限使用指定资源。

    参数:
        resource: 资源类型，对应 TIER_FEATURES 中的 key
                  'daily_analysis' / 'daily_interview' / 'daily_recommendation'
                  'resume_count' / 'deep_analysis' / 'ats_check' 等

    返回:
        (allowed: bool, message: str, 剩余额度信息: dict)
    """
    tier = get_user_plan_tier(db, user_id)
    # 自定义套餐权益：租户/平台自定义 features 覆盖硬编码默认矩阵（修复自定义套餐不生效）
    features = _effective_features(db, tier)

    # 1. 布尔权限类资源（非额度类）
    bool_features = {
        "deep_analysis": "can_use_deep_analysis",
        "ats_check": "can_use_ats_check",
        "offer_decision": "can_use_offer_decision",
        "salary_negotiation": "can_use_salary_negotiation",
        "export_full_report": "can_export_full_report",
    }
    if resource in bool_features:
        allowed = features.get(bool_features[resource], False)
        if not allowed:
            return (False, "当前套餐不支持此功能，请升级 Pro 版", _quota_info(tier, features, resource))
        return (True, "", _quota_info(tier, features, resource))

    # 2. 数量限制类资源
    if resource in DAILY_QUOTA_KEYS:
        feature_key = resource + "_limit"
        limit = features.get(feature_key, 0)
        if limit == -1:
            return (True, "", _quota_info(tier, features, resource, remaining=-1))

        sub = get_or_create_subscription(db, user_id)
        if reset_daily_quota_if_needed(sub):
            # 跨天重置已修改内存中的 quota_usage/quota_reset_at，必须立即 flush，
            # 否则下方原子 UPDATE 读到的还是 DB 旧值（昨日已用满 → 今日第一笔被误拒）。
            db.flush()

        if consume:
            # 原子扣减：使用 SQL JSON 操作，避免并发超扣
            json_path = f"'$.{resource}'"
            stmt = text(f"""
                UPDATE user_subscription
                SET quota_usage = JSON_SET(
                    quota_usage,
                    {json_path},
                    COALESCE(JSON_EXTRACT(quota_usage, {json_path}), 0) + 1
                )
                WHERE id = :sub_id
                  AND COALESCE(JSON_EXTRACT(quota_usage, {json_path}), 0) < :limit
            """)
            result = db.execute(stmt, {"sub_id": sub.id, "limit": limit})
            affected = result.rowcount
            db.commit()

            if affected == 0:
                # 没有行被更新 = 配额已满
                used = sub.quota_usage.get(resource, 0)
                return (
                    False,
                    f"今日 {resource} 额度已用完，请升级 Pro 版或明天再试",
                    _quota_info(tier, features, resource, remaining=0),
                )

            # 重新读取最新值
            db.refresh(sub)
            used = sub.quota_usage.get(resource, 0)
            remaining = max(0, limit - used)
            return (True, "", _quota_info(tier, features, resource, remaining=remaining))

        used = sub.quota_usage.get(resource, 0)
        remaining = max(0, limit - used)
        return (True, "", _quota_info(tier, features, resource, remaining=remaining))

    # 3. 简历数量限制
    if resource == "resume_count":
        limit = features.get("resume_limit", 1)
        if limit == -1:
            return (True, "", _quota_info(tier, features, resource, remaining=-1))
        from app.models.history import Resume

        # 只统计当前租户下未软删的简历，避免跨租户/已删简历占满免费额度
        current = (
            db.query(Resume)
            .filter(
                Resume.user_id == user_id,
                Resume.is_deleted == 0,
            )
            .count()
        )
        remaining = max(0, limit - current)
        if remaining <= 0:
            return (
                False,
                f"免费版最多管理 {limit} 份简历，请升级 Pro 版以管理多份简历",
                _quota_info(tier, features, resource, remaining=0),
            )
        return (True, "", _quota_info(tier, features, resource, remaining=remaining))

    # 未知资源，默认放行
    return (True, "", {})


def _quota_info(tier: str, features: dict, resource: str, remaining: int = None) -> dict:
    """构造额度信息返回。"""
    info = {"tier": tier}
    if resource in DAILY_QUOTA_KEYS:
        limit = features.get(resource + "_limit", 0)
        if remaining is not None:
            info["limit"] = limit
            info["remaining"] = remaining
        else:
            info["limit"] = limit
    return info


def get_user_quota_summary(db: Session, user_id: int) -> dict:
    """获取用户完整的权益摘要（供前端展示）。"""
    tier = get_user_plan_tier(db, user_id)
    # 自定义套餐权益：租户/平台自定义 features 覆盖硬编码默认矩阵
    features = _effective_features(db, tier)
    sub = get_or_create_subscription(db, user_id)
    if reset_daily_quota_if_needed(sub):
        # 查询接口也持久化跨天重置，避免展示与 DB 不一致
        db.commit()
        db.refresh(sub)

    quota_items = []
    for k in DAILY_QUOTA_KEYS:
        limit = features.get(k + "_limit", 0)
        used = sub.quota_usage.get(k, 0)
        remaining = max(0, limit - used) if limit > 0 else -1
        quota_items.append(
            {
                "key": k,
                "limit": limit,
                "used": used,
                "remaining": remaining,
            }
        )

    return {
        "tier": tier,
        "tier_label": {"free": "免费版", "pro": "Pro 版", "enterprise": "企业版"}.get(tier, tier),
        "status": sub.status,
        "start_at": sub.start_at.isoformat() if sub.start_at else None,
        "end_at": sub.end_at.isoformat() if sub.end_at else None,
        "quota": quota_items,
        "features": dict(features.items()),
    }


# ============================================================
# 支付处理
# ============================================================


def process_payment_callback(
    db: Session,
    order_id: int,
    transaction_id: str,
    payment_method: str = "mock",
    paid_amount: float = None,
) -> tuple[bool, str]:
    """
    处理支付回调。
    - 行锁：使用 SELECT ... FOR UPDATE 防止并发
    - 幂等：同一订单已处理过则直接返回成功
    - 金额校验：回调金额必须 >= 订单金额
    - 状态流转：pending → paid
    - 成功后自动激活订阅
    """

    # 使用行锁防止并发回调
    order = db.query(SubscriptionOrder).filter(SubscriptionOrder.id == order_id).with_for_update().first()
    if not order:
        return False, "订单不存在"

    # 幂等检查：已支付的订单不重复处理
    if order.status == OrderStatus.PAID.value:
        return True, "订单已处理"

    # 校验状态必须是 pending
    if order.status != OrderStatus.PENDING.value:
        return False, f"订单状态异常: {order.status}，无法完成支付"

    # 金额校验（必填）：回调必须携带实付金额，且不得小于订单金额。
    # 0 元订单（如未定价的企业套餐）拒绝通过支付回调开通，防止免费白嫖付费权益。
    if paid_amount is None:
        return False, "缺少支付金额"
    if float(order.amount) <= 0:
        return False, "订单金额无效（0 元订单不能通过支付回调开通，请联系管理员）"
    if paid_amount < float(order.amount):
        return False, f"支付金额不足: 需 {order.amount}，实付 {paid_amount}"

    try:
        # 更新订单状态
        order.status = OrderStatus.PAID.value
        order.transaction_id = transaction_id
        order.payment_method = payment_method
        order.paid_at = utc_now()
        db.flush()

        # 激活订阅（单租户产品：订阅只按 user_id 归属，订单上的那一列保留但不读）
        _activate_subscription(db, order.user_id, order.plan_tier)

        db.commit()
        write_audit_log(
            db,
            user=db.query(User).filter(User.id == order.user_id).first(),
            action="subscription.payment",
            resource_type="subscription",
            resource_id=str(order.id),
            status="success",
        )
        return True, "支付成功，订阅已开通"
    except Exception as e:
        db.rollback()
        return False, f"支付处理失败: {str(e)}"


def _activate_subscription(db: Session, user_id: int, plan_tier: str) -> UserSubscription:
    """
    激活用户订阅。如果已有有效订阅则延长，否则创建新订阅。

    2026-10-06 真删企业侧第六增量（D136）之前这里还带一个 `tenant_id`：查现有订阅时按订单归属租户
    过滤、新建时显式打标，理由写在原 docstring 里——"订单属租户 A 而订阅记到租户 1，付费在真实租户下
    不生效"。那是企业侧的账，随 organization 出树；行仍落在保留列的默认租户 1 上（`TenantScopedMixin`
    的 default），而查询本来就同时按 `user_id` 收窄，所以去掉那一层过滤在单租户下等价。
    """
    # DB DateTime 列无时区，读写统一 naive，避免 existing.end_at（naive）与 now 比较抛 TypeError
    now = utc_now_naive()
    duration_days = {"pro": 30, "enterprise": 30}.get(plan_tier, 30)

    existing = (
        db.query(UserSubscription)
        .filter(
            UserSubscription.user_id == user_id,
            UserSubscription.status == "active",
        )
        .order_by(UserSubscription.id.desc())
        .first()
    )

    if existing and existing.end_at and existing.end_at > now:
        # 延长现有订阅
        existing.end_at = existing.end_at + timedelta(days=duration_days)
        existing.plan_tier = plan_tier
        existing.updated_at = now
        # 重置额度
        existing.quota_usage = dict.fromkeys(DAILY_QUOTA_KEYS, 0)
        existing.quota_reset_at = now
        db.flush()
        return existing
    else:
        # 创建新订阅（显式归属订单租户）
        new_sub = UserSubscription(
            user_id=user_id,
            plan_tier=plan_tier,
            status="active",
            start_at=now,
            end_at=now + timedelta(days=duration_days),
            quota_usage=dict.fromkeys(DAILY_QUOTA_KEYS, 0),
            quota_reset_at=now,
        )
        db.add(new_sub)
        db.flush()
        return new_sub
