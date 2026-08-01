"""T3-1 套餐/价格按租户覆盖测试。

覆盖验收：「为租户 A 配置自定义 Pro 套餐后，A 域名下显示新价格，默认域名不受影响」。
- 服务层：get_plans 回落/覆盖/跨租户隔离；get_plan_price
- API 层：GET /plans 租户化、POST /admin/plans 配置、create-order 使用租户价
使用独立 StaticPool 内存库 + 真实租户中间件（同 test_tenant_api 模式）。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.auth import get_current_user
from app.api import subscription as subscription_api
from app.core.database import Base, get_db
from app.core.tenant_context import (
    reset_tenant_session_factory,
    set_tenant_session_factory,
    tenant_context_middleware,
)
from app.core.user_roles import ADMIN_ROLE, CANDIDATE_ROLE
from app.models.organization import Organization
from app.models.user import User
from app.services.subscription_service import get_plan_price, get_plans

_admin_user = User(id=1, username="admin", email="admin@example.com", role=ADMIN_ROLE)
_normal_user = User(id=2, username="candidate", email="c@example.com", role=CANDIDATE_ROLE)


@pytest.fixture
def tenant_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def tenant_session(tenant_engine):
    factory = sessionmaker(bind=tenant_engine)
    set_tenant_session_factory(factory)
    # 预置默认租户组织（占用 id=1）：保证后续创建的客户组织 id≠默认租户，
    # 使「无 X-Tenant-Id → 回落默认租户」的断言不被自增 id 撞车干扰
    _seed_org(factory, name="默认租户", slug="default-tenant")
    yield factory
    reset_tenant_session_factory()


def _seed_org(factory, *, name: str, slug: str) -> int:
    session = factory()
    org = Organization(name=name, slug=slug, owner_id=1, status="active")
    session.add(org)
    session.commit()
    session.refresh(org)
    org_id = org.id
    session.close()
    return org_id


def _seed_custom_plan(factory, *, tenant_id: int, tier: str, name: str, price_monthly: int, price_yearly: int):
    session = factory()
    from app.models.subscription import SubscriptionPlan

    session.add(
        SubscriptionPlan(
            tenant_id=tenant_id,
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
    app.middleware("http")(tenant_context_middleware)

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


def test_get_plans_default_fallback(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    db = tenant_session()
    try:
        plans = get_plans(db, org_a)
    finally:
        db.close()

    by_tier = _plans_by_tier(plans)
    assert set(by_tier) == {"free", "pro", "enterprise"}
    assert by_tier["pro"]["name"] == "Pro 版"
    assert by_tier["pro"]["price_monthly"] == 9900
    assert by_tier["pro"]["price_yearly"] == 99900
    assert by_tier["pro"]["is_custom"] is False


def test_get_plans_tenant_custom_overrides(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    _seed_custom_plan(tenant_session, tenant_id=org_a, tier="pro", name="高级版", price_monthly=12800, price_yearly=128000)

    db = tenant_session()
    try:
        plans = get_plans(db, org_a)
    finally:
        db.close()

    by_tier = _plans_by_tier(plans)
    assert by_tier["pro"]["name"] == "高级版"
    assert by_tier["pro"]["price_monthly"] == 12800
    assert by_tier["pro"]["price_yearly"] == 128000
    assert by_tier["pro"]["is_custom"] is True
    # 未自定义的 tier 回落默认
    assert by_tier["free"]["name"] == "免费版"
    assert by_tier["enterprise"]["name"] == "企业版"
    assert by_tier["enterprise"]["is_custom"] is False


def test_get_plans_other_tenant_untouched(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    org_b = _seed_org(tenant_session, name="客户B", slug="customer-b")
    _seed_custom_plan(tenant_session, tenant_id=org_a, tier="pro", name="高级版", price_monthly=12800, price_yearly=128000)

    db = tenant_session()
    try:
        plans_b = get_plans(db, org_b)
    finally:
        db.close()

    assert _plans_by_tier(plans_b)["pro"]["name"] == "Pro 版"
    assert _plans_by_tier(plans_b)["pro"]["price_monthly"] == 9900


def test_get_plan_price_custom_and_fallback(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    _seed_custom_plan(tenant_session, tenant_id=org_a, tier="pro", name="高级版", price_monthly=12800, price_yearly=128000)

    db = tenant_session()
    try:
        assert get_plan_price(db, org_a, "pro", "monthly") == 12800
        assert get_plan_price(db, org_a, "pro", "yearly") == 128000
        assert get_plan_price(db, org_a, "enterprise", "monthly") == 0
    finally:
        db.close()


# ===== API 层 =====


def test_api_plans_tenant_scoped(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    _seed_custom_plan(tenant_session, tenant_id=org_a, tier="pro", name="高级版", price_monthly=12800, price_yearly=128000)

    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        resp_a = client.get("/subscription/plans", headers={"X-Tenant-Id": str(org_a)})
        resp_default = client.get("/subscription/plans")  # 无租户头 → 默认租户 1

    assert resp_a.status_code == 200
    pro_a = _plans_by_tier(resp_a.json()["data"]["items"])["pro"]
    assert pro_a["name"] == "高级版"
    assert pro_a["price_monthly"] == 12800

    pro_default = _plans_by_tier(resp_default.json()["data"]["items"])["pro"]
    assert pro_default["name"] == "Pro 版"
    assert pro_default["price_monthly"] == 9900


def test_api_admin_upsert_plan_then_visible(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")

    app_admin = _build_app(tenant_session, user=_admin_user)
    with TestClient(app_admin) as client:
        resp = client.post(
            "/subscription/admin/plans",
            json={
                "tenant_id": org_a,
                "tier": "pro",
                "name": "企业尊享版",
                "price_monthly": 19900,
                "price_yearly": 199000,
            },
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "企业尊享版"
    assert data["price_monthly"] == 19900
    assert data["is_custom"] is True

    # 更新同一 tier → upsert 不重复建行
    with TestClient(app_admin) as client:
        resp2 = client.post(
            "/subscription/admin/plans",
            json={"tenant_id": org_a, "tier": "pro", "price_monthly": 20900},
        )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["price_monthly"] == 20900

    # 租户 A 的 /plans 展示新价格
    app_user = _build_app(tenant_session, user=_normal_user)
    with TestClient(app_user) as client:
        resp3 = client.get("/subscription/plans", headers={"X-Tenant-Id": str(org_a)})
    pro = _plans_by_tier(resp3.json()["data"]["items"])["pro"]
    assert pro["name"] == "企业尊享版"
    assert pro["price_monthly"] == 20900


def test_api_admin_upsert_forbidden_for_normal_user(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        resp = client.post(
            "/subscription/admin/plans",
            json={"tenant_id": org_a, "tier": "pro", "name": "X", "price_monthly": 1},
        )
    assert resp.status_code != 200  # 403


def test_api_create_order_uses_tenant_price(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    _seed_custom_plan(tenant_session, tenant_id=org_a, tier="pro", name="高级版", price_monthly=12800, price_yearly=128000)

    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        resp = client.post(
            "/subscription/create-order",
            headers={"X-Tenant-Id": str(org_a)},
            json={"plan_tier": "pro", "period": "monthly"},
        )
        resp_default = client.post(
            "/subscription/create-order",
            json={"plan_tier": "pro", "period": "monthly"},
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["amount"] == 12800  # 租户自定义价
    assert resp_default.json()["data"]["amount"] == 9900  # 默认价不受影响


# ===== 支付回调安全加固 =====


def test_get_user_plan_tier_no_naive_aware_crash(tenant_session):
    """付费订阅读取不应因 DB naive DateTime 与 aware now 比较抛 TypeError。"""
    from datetime import datetime, timedelta, timezone

    from app.models.subscription import UserSubscription
    from app.services.subscription_service import get_user_plan_tier

    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    session = tenant_session()
    try:
        session.add(
            UserSubscription(
                user_id=7,
                plan_tier="pro",
                status="active",
                start_at=naive_now - timedelta(days=1),
                end_at=naive_now + timedelta(days=29),
                quota_usage={},
                tenant_id=1,
            )
        )
        session.commit()
        assert get_user_plan_tier(session, 7) == "pro"
    finally:
        session.close()


def test_payment_callback_rejects_zero_amount_order(tenant_session):
    """0 元订单（如未定价的企业套餐）不能通过支付回调开通，防止免费白嫖。"""
    from app.models.subscription import SubscriptionOrder
    from app.services.subscription_service import process_payment_callback

    session = tenant_session()
    try:
        order = SubscriptionOrder(user_id=7, plan_tier="enterprise", amount=0, status="pending", tenant_id=1)
        session.add(order)
        session.commit()
        ok, msg = process_payment_callback(session, order.id, "tx_zero", "mock", paid_amount=0)
        assert ok is False
        assert "0 元" in msg
    finally:
        session.close()


def test_payment_callback_requires_paid_amount(tenant_session):
    """回调必须携带实付金额，省略金额不得通过。"""
    from app.models.subscription import SubscriptionOrder
    from app.services.subscription_service import process_payment_callback

    session = tenant_session()
    try:
        order = SubscriptionOrder(user_id=7, plan_tier="pro", amount=9900, status="pending", tenant_id=1)
        session.add(order)
        session.commit()
        ok, msg = process_payment_callback(session, order.id, "tx_pro", "mock")
        assert ok is False
        assert "缺少支付金额" in msg
    finally:
        session.close()


def test_pay_callback_requires_configured_secret(tenant_session, monkeypatch):
    """未配置 PAYMENT_WEBHOOK_SECRET 时支付回调拒绝处理（fail-closed）。"""
    import os

    from app.models.subscription import SubscriptionOrder

    monkeypatch.delenv("PAYMENT_WEBHOOK_SECRET", raising=False)
    session = tenant_session()
    try:
        order = SubscriptionOrder(user_id=7, plan_tier="pro", amount=9900, status="pending", tenant_id=1)
        session.add(order)
        session.commit()
        order_id = order.id
    finally:
        session.close()

    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        resp = client.post(
            "/subscription/pay-callback",
            json={"order_id": order_id, "transaction_id": "tx", "amount": 9900, "sign": "x"},
        )
    body = resp.json()
    assert body["code"] != 0
    assert "PAYMENT_WEBHOOK_SECRET" in body["message"]


def test_daily_quota_reset_across_day_then_consumable(tenant_session):
    """跨天后额度应重置，且原子扣减读到清零后的值（#5）。"""
    from datetime import datetime, timedelta, timezone

    from app.models.subscription import UserSubscription
    from app.services.subscription_service import check_quota

    naive_now = datetime.now(timezone.utc).replace(tzinfo=None)
    session = tenant_session()
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
                tenant_id=1,
            )
        )
        session.commit()
        allowed, msg, _ = check_quota(session, 8, "daily_analysis", consume=True)
        assert allowed, f"跨天重置后首笔请求应放行: {msg}"
    finally:
        session.close()


def test_payment_activation_inherits_order_tenant(tenant_session):
    """支付回调激活订阅应继承订单租户，而非回落默认租户 1（#6）。"""
    from app.models.subscription import SubscriptionOrder, UserSubscription
    from app.services.subscription_service import process_payment_callback

    session = tenant_session()
    try:
        user = User(id=9, username="pay_user", email="pay@example.com", password="hashed")
        session.add(user)
        session.commit()
        order = SubscriptionOrder(user_id=9, plan_tier="pro", amount=9900, status="pending", tenant_id=42)
        session.add(order)
        session.commit()
        ok_flag, msg = process_payment_callback(session, order.id, "tx_tenant", "mock", paid_amount=9900)
        assert ok_flag, msg
        sub = session.query(UserSubscription).filter(UserSubscription.user_id == 9).first()
        assert sub is not None
        assert sub.tenant_id == 42  # 继承订单租户，而非 ContextVar 回落默认租户
    finally:
        session.close()
