"""套餐/价格配置化测试（两级：平台配置行 → 内置矩阵）。

2026-10-06 真删企业侧第六增量（D136，§10.32 他点「整族拆到底」）之前，这一族是"按租户覆盖"：
验收原话是「为租户 A 配置自定义 Pro 套餐后，A 域名下显示新价格，默认域名不受影响」。
`POST /subscription/admin/plans` 是 `subscription_plan` 表唯一的写入端，而且它要求请求体带
`tenant_id`（所以历史上只能造"租户自定义"行），它随租户那一级一起出树。于是本文件少了三条：
"其他租户不受影响"、"普通用户不得调后台配置"（端点没了）、"支付回调激活订阅继承订单租户"
（那是企业侧的账；单租户下订阅只按 user_id 归属）。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import subscription as subscription_api
from app.api.auth import get_current_user
from app.core.database import Base, get_db
from app.core.user_roles import CANDIDATE_ROLE
from app.models.user import User
from app.services.subscription_service import get_plan_price, get_plans

_normal_user = User(id=2, username="candidate", email="c@example.com", role=CANDIDATE_ROLE)


@pytest.fixture
def plan_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def plan_session(plan_engine):
    return sessionmaker(bind=plan_engine)


def _seed_platform_plan(factory, *, tier: str, name: str, price_monthly: int, price_yearly: int):
    """平台级套餐行（`tenant_id IS NULL`）——租户级出树后唯一的覆盖来源。"""
    session = factory()
    from app.models.subscription import SubscriptionPlan

    session.add(
        SubscriptionPlan(
            tenant_id=None,
            tier=tier,
            is_custom=1,
            name=name,
            price_monthly=price_monthly,
            price_yearly=price_yearly,
        )
    )
    session.commit()
    session.close()


def _build_app(factory, *, user: User):
    app = FastAPI()

    def _get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.include_router(subscription_api.router, prefix="/subscription")
    return app


def _plans_by_tier(items) -> dict:
    return {p["tier"]: p for p in items}


# ===== 服务层 =====


def test_get_plans_builtin_matrix_when_no_platform_rows(plan_session):
    db = plan_session()
    try:
        plans = get_plans(db)
    finally:
        db.close()

    by_tier = _plans_by_tier(plans)
    assert set(by_tier) == {"free", "pro", "enterprise"}
    assert by_tier["pro"]["name"] == "Pro 版"
    assert by_tier["pro"]["price_monthly"] == 9900
    assert by_tier["pro"]["price_yearly"] == 99900
    # `is_custom` 这个回显字段随"租户自定义"那一档一起出树（前端从未读它）
    assert "is_custom" not in by_tier["pro"]


def test_get_plans_platform_row_overrides_builtin(plan_session):
    _seed_platform_plan(plan_session, tier="pro", name="高级版", price_monthly=12800, price_yearly=128000)

    db = plan_session()
    try:
        by_tier = _plans_by_tier(get_plans(db))
    finally:
        db.close()

    assert by_tier["pro"]["name"] == "高级版"
    assert by_tier["pro"]["price_monthly"] == 12800
    assert by_tier["pro"]["price_yearly"] == 128000
    # 没有平台行的 tier 回落内置
    assert by_tier["free"]["name"] == "免费版"
    assert by_tier["enterprise"]["name"] == "企业版"


def test_get_plan_price_platform_override_and_fallback(plan_session):
    _seed_platform_plan(plan_session, tier="pro", name="高级版", price_monthly=12800, price_yearly=128000)

    db = plan_session()
    try:
        assert get_plan_price(db, "pro", "monthly") == 12800
        assert get_plan_price(db, "pro", "yearly") == 128000
        assert get_plan_price(db, "enterprise", "monthly") == 0
    finally:
        db.close()


# ===== 支付回调安全加固 =====


def test_get_user_plan_tier_no_naive_aware_crash(plan_session):
    """付费订阅读取不应因 DB naive DateTime 与 aware now 比较抛 TypeError。"""
    from datetime import datetime, timedelta, timezone

    from app.models.subscription import UserSubscription
    from app.services.subscription_service import get_user_plan_tier

    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    session = plan_session()
    try:
        session.add(
            UserSubscription(
                user_id=7,
                plan_tier="pro",
                status="active",
                start_at=naive_now - timedelta(days=1),
                end_at=naive_now + timedelta(days=29),
                quota_usage={},
            )
        )
        session.commit()
        assert get_user_plan_tier(session, 7) == "pro"
    finally:
        session.close()


def test_payment_callback_rejects_zero_amount_order(plan_session):
    """0 元订单（如未定价的企业套餐）不能通过支付回调开通，防止免费白嫖。"""
    from app.models.subscription import SubscriptionOrder
    from app.services.subscription_service import process_payment_callback

    session = plan_session()
    try:
        order = SubscriptionOrder(user_id=7, plan_tier="enterprise", amount=0, status="pending")
        session.add(order)
        session.commit()
        ok, msg = process_payment_callback(session, order.id, "tx_zero", "mock", paid_amount=0)
        assert ok is False
        assert "0 元" in msg
    finally:
        session.close()


def test_payment_callback_requires_paid_amount(plan_session):
    """回调必须携带实付金额，省略金额不得通过。"""
    from app.models.subscription import SubscriptionOrder
    from app.services.subscription_service import process_payment_callback

    session = plan_session()
    try:
        order = SubscriptionOrder(user_id=7, plan_tier="pro", amount=9900, status="pending")
        session.add(order)
        session.commit()
        ok, msg = process_payment_callback(session, order.id, "tx_pro", "mock")
        assert ok is False
        assert "缺少支付金额" in msg
    finally:
        session.close()


def test_pay_callback_requires_configured_secret(plan_session, monkeypatch):
    """未配置 PAYMENT_WEBHOOK_SECRET 时支付回调拒绝处理（fail-closed）。"""

    from app.models.subscription import SubscriptionOrder

    monkeypatch.delenv("PAYMENT_WEBHOOK_SECRET", raising=False)
    session = plan_session()
    try:
        order = SubscriptionOrder(user_id=7, plan_tier="pro", amount=9900, status="pending")
        session.add(order)
        session.commit()
        order_id = order.id
    finally:
        session.close()

    app = _build_app(plan_session, user=_normal_user)
    with TestClient(app) as client:
        resp = client.post(
            "/subscription/pay-callback",
            json={"order_id": order_id, "transaction_id": "tx", "amount": 9900, "sign": "x"},
        )
    body = resp.json()
    assert body["code"] != 0
    assert "PAYMENT_WEBHOOK_SECRET" in body["message"]


def test_daily_quota_reset_across_day_then_consumable(plan_session):
    """跨天后额度应重置，且原子扣减读到清零后的值（#5）。"""
    from datetime import datetime, timedelta, timezone

    from app.models.subscription import UserSubscription
    from app.services.subscription_service import check_quota

    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    session = plan_session()
    try:
        session.add(
            UserSubscription(
                user_id=8,
                plan_tier="free",
                status="active",
                start_at=naive_now - timedelta(days=2),
                end_at=None,
                quota_usage={"daily_analysis": 3, "daily_interview": 5, "daily_recommendation": 10},
                quota_reset_at=naive_now - timedelta(days=1),
            )
        )
        session.commit()
        allowed, msg, _ = check_quota(session, 8, "daily_analysis", consume=True)
        assert allowed, f"跨天重置后首笔请求应放行: {msg}"
    finally:
        session.close()


def test_payment_activation_keys_subscription_by_user_only(plan_session):
    """支付回调开通的订阅按 user_id 归属；订单上那一列保留但不再参与匹配。

    这条取代原来的「激活订阅继承订单租户」：那次改动的全部理由是"订单属租户 A 而订阅记到租户 1
    会让付费在真实租户下不生效"。企业侧出树后没有第二个租户，那句话没有对象了；留下的判据是
    **同一个用户再付费必须延长自己那条订阅**，而不是又开一条。
    """
    from app.models.subscription import SubscriptionOrder, UserSubscription
    from app.services.subscription_service import process_payment_callback

    session = plan_session()
    try:
        user = User(id=9, username="pay_user", email="pay@example.com", password="hashed")
        session.add(user)
        session.commit()
        order = SubscriptionOrder(user_id=9, plan_tier="pro", amount=9900, status="pending", tenant_id=42)
        session.add(order)
        session.commit()
        ok_flag, _ = process_payment_callback(session, order.id, "tx_first", "mock", paid_amount=9900)
        assert ok_flag

        second = SubscriptionOrder(user_id=9, plan_tier="pro", amount=9900, status="pending", tenant_id=42)
        session.add(second)
        session.commit()
        ok_second, _ = process_payment_callback(session, second.id, "tx_second", "mock", paid_amount=9900)
        assert ok_second

        subs = session.query(UserSubscription).filter(UserSubscription.user_id == 9).all()
        assert len(subs) == 1, f"再付费应延长同一条订阅，实际 {len(subs)} 条"
    finally:
        session.close()
