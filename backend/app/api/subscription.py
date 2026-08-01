"""订阅与权益 API。"""

from __future__ import annotations

import hashlib
import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_admin
from app.core.config import settings
from app.core.database import get_db
from app.core.tenant_context import require_tenant, stamp_tenant, tenant_filter
from app.models.user import User
from app.services.subscription_service import (
    TIER_FEATURES,
    check_quota,
    get_plan_price,
    get_plans,
    get_user_quota_summary,
)
from app.utils.response import ERR_PARAM, fail, ok

router = APIRouter()


@router.get("/plans", summary="获取当前租户可见的套餐定义（T3-1 租户覆盖）")
def list_plans(
    db: Session = Depends(get_db),
    tenant=Depends(require_tenant),
):
    """返回当前租户的套餐列表：租户自定义套餐优先，未自定义的 tier 回落平台默认。"""
    plans = get_plans(db, tenant.tenant_id)
    return ok({"items": plans})


@router.get("/my", summary="获取当前用户订阅与权益状态")
def my_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回用户当前套餐、额度使用、有效期等。"""
    summary = get_user_quota_summary(db, current_user.id)
    return ok(summary)


@router.post("/check-quota", summary="检查某项资源额度")
def check_resource_quota(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检查指定资源是否可用，可选是否消耗额度。

    请求体: {"resource": "daily_analysis", "consume": false}
    资源类型: daily_analysis / daily_interview / daily_recommendation
              / deep_analysis / ats_check / offer_decision / resume_count
    """
    resource = payload.get("resource", "")
    consume = payload.get("consume", False)
    if not resource:
        return fail(message="resource 必填", code=ERR_PARAM)

    allowed, msg, quota_info = check_quota(db, current_user.id, resource, consume=consume)
    if allowed:
        return ok({"allowed": True, "quota": quota_info})
    return ok({"allowed": False, "message": msg, "quota": quota_info})


@router.post("/create-order", summary="创建订阅订单")
def create_order(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant=Depends(require_tenant),
):
    """创建订阅订单（支付接入后使用）。

    请求体: {"plan_tier": "pro", "period": "monthly"}
    价格取自当前租户可见套餐（T3-1：租户自定义价格优先）。
    """
    from app.models.subscription import SubscriptionOrder

    plan_tier = payload.get("plan_tier", "")
    period = payload.get("period", "monthly")

    if plan_tier not in TIER_FEATURES or plan_tier == "free":
        return fail(message="无效的套餐", code=ERR_PARAM)

    price = get_plan_price(db, tenant.tenant_id, plan_tier, period)

    import uuid

    order = stamp_tenant(
        SubscriptionOrder(
            user_id=current_user.id,
            plan_tier=plan_tier,
            amount=price,
            currency="cny",
            status="pending",
            payment_method="",
            idempotency_key=str(uuid.uuid4()),
        )
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return ok({"order_id": order.id, "amount": float(order.amount), "status": order.status})


@router.get("/orders", summary="获取用户订单历史")
def list_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.subscription import SubscriptionOrder

    orders = (
        db.query(SubscriptionOrder)
        .filter(
            tenant_filter(SubscriptionOrder),
            SubscriptionOrder.user_id == current_user.id,
        )
        .order_by(SubscriptionOrder.created_at.desc())
        .limit(20)
        .all()
    )
    return ok(
        [
            {
                "id": o.id,
                "plan_tier": o.plan_tier,
                "amount": float(o.amount),
                "status": o.status,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            }
            for o in orders
        ]
    )


@router.post("/pay-callback", summary="支付回调（Webhook）")
def payment_callback(
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    支付渠道回调端点。

    请求体: {"order_id": 1, "transaction_id": "tx_xxx", "payment_method": "alipay", "amount": 9900, "sign": "..."}

    安全措施：
    - 签名校验：使用渠道密钥验证回调真实性
    - 行锁：SELECT FOR UPDATE 防止并发
    - 金额校验：回调金额 >= 订单金额
    - 幂等：同一 order_id 多次调用不重复开通
    """
    from app.models.subscription import SubscriptionOrder
    from app.services.subscription_service import process_payment_callback

    order_id = payload.get("order_id")
    transaction_id = payload.get("transaction_id", "")
    payment_method = payload.get("payment_method", "unknown")
    paid_amount = payload.get("amount")
    sign = payload.get("sign", "")

    if not order_id:
        return fail(message="order_id 必填", code=ERR_PARAM)

    # 签名校验（强制）：未配置渠道密钥视为配置错误，拒绝回调，防止伪造支付成功开通订阅。
    payment_secret = os.getenv("PAYMENT_WEBHOOK_SECRET", "")
    if not payment_secret:
        return fail(message="服务端未配置 PAYMENT_WEBHOOK_SECRET，拒绝处理支付回调", code=ERR_PARAM)
    raw = f"{order_id}:{transaction_id}:{paid_amount or ''}:{payment_secret}"
    expected = hashlib.sha256(raw.encode()).hexdigest()
    if sign != expected:
        return fail(message="签名校验失败", code=ERR_PARAM)

    # 订单存在性预检
    order = db.query(SubscriptionOrder).filter(SubscriptionOrder.id == order_id).first()
    if not order:
        return fail(message="订单不存在", code=ERR_PARAM)

    success, msg = process_payment_callback(
        db,
        order_id,
        transaction_id,
        payment_method,
        paid_amount=paid_amount,
    )
    if success:
        return ok({"message": msg})
    return fail(message=msg, code=ERR_PARAM)


@router.post("/mock-pay", summary="模拟支付（测试用）")
def mock_pay(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    模拟支付成功（仅测试环境可用）。
    校验订单归属当前用户，防止越权操作。
    """
    from app.models.subscription import SubscriptionOrder
    from app.services.subscription_service import process_payment_callback

    # 生产环境禁用
    if settings.APP_ENV == "production":
        return fail(message="mock-pay 仅限测试环境使用", code=ERR_PARAM)

    order_id = payload.get("order_id")
    if not order_id:
        return fail(message="order_id 必填", code=ERR_PARAM)

    # 校验订单归属
    order = (
        db.query(SubscriptionOrder)
        .filter(tenant_filter(SubscriptionOrder), SubscriptionOrder.id == order_id)
        .first()
    )
    if not order:
        return fail(message="订单不存在", code=ERR_PARAM)
    if order.user_id != current_user.id:
        return fail(message="无权操作他人的订单", code=ERR_PARAM)

    import uuid

    success, msg = process_payment_callback(
        db,
        order_id,
        transaction_id=str(uuid.uuid4()),
        payment_method="mock",
        paid_amount=float(order.amount),
    )
    if success:
        return ok({"message": msg, "order_id": order_id})
    return fail(message=msg, code=ERR_PARAM)


@router.get("/admin/orders", summary="管理员：订单列表")
def admin_list_orders(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    from app.models.subscription import SubscriptionOrder

    query = db.query(SubscriptionOrder).order_by(SubscriptionOrder.created_at.desc())
    total = query.count()
    orders = query.offset((page - 1) * page_size).limit(page_size).all()
    return ok(
        data={
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": o.id,
                    "tenant_id": o.tenant_id,
                    "user_id": o.user_id,
                    "plan_tier": o.plan_tier,
                    "amount": float(o.amount),
                    "status": o.status,
                    "payment_method": o.payment_method,
                    "transaction_id": o.transaction_id,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                    "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                }
                for o in orders
            ],
        }
    )


@router.post("/admin/plans", summary="管理员：创建/更新租户自定义套餐（T3-1）")
def upsert_custom_plan(
    payload: dict,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """配置租户自定义套餐（按 tier 覆盖默认套餐）。

    请求体: {"tenant_id": 2, "tier": "pro", "name": "高级版", "price_monthly": 12800,
             "price_yearly": 128000, "features": {...可选，与默认权益浅合并}, "is_active": 1}
    """
    from app.models.subscription import SubscriptionPlan

    tenant_id = payload.get("tenant_id")
    tier = payload.get("tier", "")
    if not tenant_id or tier not in TIER_FEATURES or tier == "free":
        return fail(message="tenant_id 与 tier（pro/enterprise）必填", code=ERR_PARAM)

    plan = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.tenant_id == tenant_id, SubscriptionPlan.tier == tier)
        .first()
    )
    if plan is None:
        plan = SubscriptionPlan(tenant_id=tenant_id, tier=tier, is_custom=1)
        db.add(plan)

    if "name" in payload:
        plan.name = str(payload["name"])
    if "price_monthly" in payload:
        plan.price_monthly = payload["price_monthly"]
    if "price_yearly" in payload:
        plan.price_yearly = payload["price_yearly"]
    if "features" in payload and isinstance(payload["features"], dict):
        plan.features = payload["features"]
    if "sort_order" in payload:
        plan.sort_order = payload["sort_order"]
    if "is_active" in payload:
        plan.is_active = 1 if payload["is_active"] else 0
    if "is_custom" in payload:
        plan.is_custom = 1 if payload["is_custom"] else 0

    db.commit()
    db.refresh(plan)
    return ok(
        {
            "id": plan.id,
            "tenant_id": plan.tenant_id,
            "tier": plan.tier,
            "name": plan.name,
            "price_monthly": float(plan.price_monthly or 0),
            "price_yearly": float(plan.price_yearly or 0),
            "is_custom": bool(plan.is_custom),
        }
    )
