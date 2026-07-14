"""订阅与权益服务层：套餐定义、权益矩阵、额度校验/消耗/重置。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.subscription import (
    OrderStatus,
    SubscriptionOrder,
    UserSubscription,
)
from app.models.user import User
from app.services.audit_service import write_audit_log
from app.utils.time_helper import utc_now

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
    if sub and sub.end_at and sub.end_at > utc_now():
        return sub.plan_tier
    return "free"


def get_user_features(db: Session, user_id: int) -> dict:
    """获取用户当前套餐的完整权益配置。"""
    tier = get_user_plan_tier(db, user_id)
    return dict(TIER_FEATURES.get(tier, TIER_FEATURES["free"]))


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
            start_at=utc_now(),
            quota_usage=dict.fromkeys(DAILY_QUOTA_KEYS, 0),
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return sub


def reset_daily_quota_if_needed(sub: UserSubscription) -> bool:
    """检查是否需要重置每日额度（跨天），返回是否重置过。"""
    now = utc_now()
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
    features = TIER_FEATURES.get(tier, TIER_FEATURES["free"])

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
        reset_daily_quota_if_needed(sub)

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

        current = db.query(Resume).filter(Resume.user_id == user_id).count()
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
    features = TIER_FEATURES.get(tier, TIER_FEATURES["free"])
    sub = get_or_create_subscription(db, user_id)
    reset_daily_quota_if_needed(sub)

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

    # 金额校验（可选）：回调金额必须 >= 订单金额
    if paid_amount is not None:
        if paid_amount < float(order.amount):
            return False, f"支付金额不足: 需 {order.amount}，实付 {paid_amount}"

    try:
        # 更新订单状态
        order.status = OrderStatus.PAID.value
        order.transaction_id = transaction_id
        order.payment_method = payment_method
        order.paid_at = utc_now()
        db.flush()

        # 激活订阅
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
    """
    now = utc_now()
    duration_days = {"pro": 30, "enterprise": 30}.get(plan_tier, 30)

    # 查找现有有效订阅
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
        # 创建新订阅
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
