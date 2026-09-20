"""T2-5 租户品牌与管理接口测试 + T4-1 租户管理页接口测试 + T4-3 计费自动化测试。

T2-5 验收：「未配置回落默认、配置读写、权限校验」+ 创建租户。
T4-1 验收：「创建租户 → 分配域名 → 停用 → 该域名请求 403；操作有审计日志」。
T4-3 验收：「把租户 expires_at 设为过去时间 → 1 个调度周期内自动停用；续费后立即恢复」。
使用独立 StaticPool 内存库 + 真实租户中间件，与 conftest 的 db_session 互不干扰。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import tenant as tenant_api
from app.api.auth import get_current_user
from app.core.database import Base, get_db
from app.core.tenant_context import (
    reset_tenant_session_factory,
    set_tenant_session_factory,
    tenant_context_middleware,
)
from app.core.user_roles import ADMIN_ROLE, CANDIDATE_ROLE
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.subscription import SubscriptionOrder, UserSubscription
from app.models.tenant import TenantConfig
from app.models.user import User
from app.services.subscription_service import run_tenant_billing_check
from app.utils.time_helper import utc_now_naive

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
    yield factory
    reset_tenant_session_factory()


def _seed(
    factory,
    *,
    name: str,
    slug: str,
    logo_url: str | None = None,
    primary_color: str | None = None,
    configs: dict | None = None,
) -> int:
    session = factory()
    org = Organization(name=name, slug=slug, owner_id=1, status="active")
    if logo_url is not None:
        org.logo_url = logo_url
    if primary_color is not None:
        org.primary_color = primary_color
    session.add(org)
    session.commit()
    session.refresh(org)
    for key, value in (configs or {}).items():
        session.add(TenantConfig(tenant_id=org.id, config_key=key, config_value=value))
    session.commit()
    org_id = org.id  # 关闭前读取，避免 detached 后 refresh 报错
    session.close()
    return org_id


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
    app.include_router(tenant_api.router, prefix="/tenant")
    app.include_router(tenant_api.admin_router, prefix="/admin/tenants")
    return app


# ---- 未配置 → 回落默认 ----


def test_brand_falls_back_to_default(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        resp = client.get("/tenant/brand", headers={"X-Tenant-Id": str(org_id)})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tenant_id"] == org_id
    assert data["name"] == "客户A"
    assert data["primary_color"] == "#2563eb"  # 默认主色
    assert data["logo_url"] == ""
    assert data["favicon"] == ""
    assert data["company"] == "客户A"  # 未配置 company → 回落组织名


# ---- 已配置 → 返回配置值 ----


def test_brand_returns_configured_values(tenant_session):
    org_id = _seed(
        tenant_session,
        name="客户A",
        slug="customer-a",
        logo_url="https://cdn.example.com/logo.png",
        primary_color="#16a879",
        configs={
            "brand.favicon": "https://cdn.example.com/fav.ico",
            "brand.login_bg": "https://cdn.example.com/bg.jpg",
            "brand.company": "客户A科技有限公司",
            "brand.contact": "support@customer-a.com",
        },
    )
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        resp = client.get("/tenant/brand", headers={"X-Tenant-Id": str(org_id)})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["logo_url"] == "https://cdn.example.com/logo.png"
    assert data["primary_color"] == "#16a879"
    assert data["favicon"] == "https://cdn.example.com/fav.ico"
    assert data["login_bg"] == "https://cdn.example.com/bg.jpg"
    assert data["company"] == "客户A科技有限公司"
    assert data["contact"] == "support@customer-a.com"


# ---- 管理员更新品牌 → 配置持久化 ----


def test_admin_update_brand_writes_config(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        resp = client.put(
            f"/admin/tenants/{org_id}/brand",
            json={
                "name": "客户A（新版）",
                "primary_color": "#ff6600",
                "logo_url": "https://cdn.example.com/new-logo.png",
                "favicon": "https://cdn.example.com/new-fav.ico",
                "company": "新公司名",
                "contact": "ops@customer-a.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "客户A（新版）"
        assert data["primary_color"] == "#ff6600"
        assert data["logo_url"] == "https://cdn.example.com/new-logo.png"
        assert data["favicon"] == "https://cdn.example.com/new-fav.ico"

        # 持久化后再读 brand 确认
        get_resp = client.get("/tenant/brand", headers={"X-Tenant-Id": str(org_id)})
        get_data = get_resp.json()["data"]
        assert get_data["primary_color"] == "#ff6600"
        assert get_data["company"] == "新公司名"
        assert get_data["contact"] == "ops@customer-a.com"


# ---- 管理员创建租户 ----


def test_admin_create_tenant(tenant_session):
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        resp = client.post("/admin/tenants", json={"name": "新租户", "slug": "new-tenant", "plan_tier": "pro"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "新租户"
        assert data["slug"] == "new-tenant"
        assert data["plan_tier"] == "pro"

        # 重复 slug → 409
        dup = client.post("/admin/tenants", json={"name": "重复", "slug": "new-tenant"})
        assert dup.status_code == 409


# ---- 权限校验：非管理员访问 admin 接口 → 403 ----


def test_admin_endpoints_require_admin_role(tenant_session):
    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        assert client.get("/admin/tenants").status_code == 403
        assert client.post("/admin/tenants", json={"name": "x", "slug": "x"}).status_code == 403


# ===================== T4-1 租户管理 =====================


def test_admin_update_tenant_status_and_expires(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        resp = client.put(
            f"/admin/tenants/{org_id}",
            json={
                "name": "客户A（改名）",
                "plan_tier": "enterprise",
                "status": "suspended",
                "expires_at": "2026-12-31T00:00:00+00:00",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "客户A（改名）"
        assert data["plan_tier"] == "enterprise"
        assert data["status"] == "suspended"
        assert data["expires_at"] is not None


def test_admin_update_tenant_validation(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        # 非法状态 → 400
        bad_status = client.put(f"/admin/tenants/{org_id}", json={"status": "hacked"})
        assert bad_status.status_code == 400

        # 非法套餐 → 400
        bad_plan = client.put(f"/admin/tenants/{org_id}", json={"plan_tier": "gold"})
        assert bad_plan.status_code == 400

        # 非法到期时间 → 400
        bad_expiry = client.put(f"/admin/tenants/{org_id}", json={"expires_at": "not-a-date"})
        assert bad_expiry.status_code == 400

        # 租户不存在 → 404
        missing = client.put("/admin/tenants/99999", json={"name": "x"})
        assert missing.status_code == 404


def test_admin_assign_tenant_admin(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    session = tenant_session()
    member = User(
        username="hr-manager",
        email="hr@customer-a.com",
        role=CANDIDATE_ROLE,
        password="hashed-placeholder",
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    member_id = member.id
    session.close()

    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        resp = client.post(f"/admin/tenants/{org_id}/admin", json={"user_id": member_id})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["admin_user_id"] == member_id
        assert data["username"] == "hr-manager"

    # 落库校验
    session = tenant_session()
    org = session.get(Organization, org_id)
    assert org.admin_user_id == member_id
    session.close()

    # 用户不存在 → 404；user_id 非法 → 400
    with TestClient(app) as client:
        assert client.post(f"/admin/tenants/{org_id}/admin", json={"user_id": 99999}).status_code == 404
        assert client.post(f"/admin/tenants/{org_id}/admin", json={"user_id": 0}).status_code == 400


def test_admin_bind_unbind_domain(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        # 绑定主域名
        bind = client.post(f"/admin/tenants/{org_id}/domains", json={"domain": "Customer-A.cn", "is_primary": True})
        assert bind.status_code == 200
        assert bind.json()["data"]["domain"] == "customer-a.cn"  # 归一化小写
        assert bind.json()["data"]["is_primary"] == 1

        # 域名格式非法 → 400
        bad = client.post(f"/admin/tenants/{org_id}/domains", json={"domain": "not a domain"})
        assert bad.status_code == 400

        # 重复绑定 → 409
        dup = client.post(f"/admin/tenants/{org_id}/domains", json={"domain": "customer-a.cn"})
        assert dup.status_code == 409

        # 列表
        listing = client.get(f"/admin/tenants/{org_id}/domains")
        assert listing.status_code == 200
        assert len(listing.json()["data"]) == 1

        # 解绑
        unbind = client.delete(f"/admin/tenants/{org_id}/domains/customer-a.cn")
        assert unbind.status_code == 200
        assert client.get(f"/admin/tenants/{org_id}/domains").json()["data"] == []

        # 未绑定域名解绑 → 404
        assert client.delete(f"/admin/tenants/{org_id}/domains/nonexistent.com").status_code == 404


def test_expired_tenant_request_403(tenant_session):
    """停用后，绑定域名的请求被租户中间件拦截 → 403（T4-1 验收）。"""
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        bind = client.post(f"/admin/tenants/{org_id}/domains", json={"domain": "customer-a.cn"})
        assert bind.status_code == 200

        # active 时经域名请求正常（解析到该租户）
        active = client.get("/tenant/brand", headers={"Host": "customer-a.cn"})
        assert active.status_code == 200
        assert active.json()["data"]["tenant_id"] == org_id

        # 停用 → expired
        deact = client.put(f"/admin/tenants/{org_id}", json={"status": "expired"})
        assert deact.status_code == 200
        assert deact.json()["data"]["status"] == "expired"

        # 域名请求 → 403
        blocked = client.get("/tenant/brand", headers={"Host": "customer-a.cn"})
        assert blocked.status_code == 403
        assert blocked.json()["code"] == -13


def test_tenant_operations_write_audit_log(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    session = tenant_session()
    member = User(
        username="audit-hr",
        email="audit@customer-a.com",
        role=CANDIDATE_ROLE,
        password="hashed-placeholder",
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    member_id = member.id
    session.close()

    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        client.put(f"/admin/tenants/{org_id}", json={"status": "suspended"})
        client.post(f"/admin/tenants/{org_id}/admin", json={"user_id": member_id})
        client.post(f"/admin/tenants/{org_id}/domains", json={"domain": "audit-a.cn"})

    session = tenant_session()
    actions = [row.action for row in session.query(AuditLog).order_by(AuditLog.id).all()]
    session.close()
    assert "tenant.update" in actions
    assert "tenant.assign_admin" in actions
    assert "tenant.bind_domain" in actions


def test_tenant_admin_endpoints_require_admin_role(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        assert client.put(f"/admin/tenants/{org_id}", json={"status": "expired"}).status_code == 403
        assert client.post(f"/admin/tenants/{org_id}/admin", json={"user_id": 1}).status_code == 403
        assert client.post(f"/admin/tenants/{org_id}/domains", json={"domain": "x.cn"}).status_code == 403
        assert client.delete(f"/admin/tenants/{org_id}/domains/x.cn").status_code == 403


# ===================== T4-3 计费与开通自动化 =====================


def _seed_expiring_org_and_sub(factory, *, org_id: int, past: bool) -> None:
    session = factory()
    session.add(
        UserSubscription(
            user_id=1,
            tenant_id=org_id,
            plan_tier="pro",
            status="active",
            end_at=utc_now_naive() + timedelta(days=30),
        )
    )
    session.query(Organization).filter(Organization.id == org_id).update(
        {
            Organization.status: "active",
            Organization.expires_at: utc_now_naive() - timedelta(days=1)
            if past
            else utc_now_naive() + timedelta(days=30),
        }
    )
    session.commit()
    session.close()


def test_billing_scan_expires_and_suspends(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    _seed_expiring_org_and_sub(tenant_session, org_id=org_id, past=True)

    session = tenant_session()
    stats = run_tenant_billing_check(session)
    org = session.get(Organization, org_id)
    sub = session.query(UserSubscription).filter(UserSubscription.tenant_id == org_id).first()
    session.close()

    assert stats == {"expired": 1, "restored": 0}
    assert org.status == "expired"
    assert sub.status == "suspended"  # 权益即时失效


def test_billing_scan_restores_renewed(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    _seed_expiring_org_and_sub(tenant_session, org_id=org_id, past=False)

    session = tenant_session()
    # 模拟：已续费（expires_at 在未来）但状态仍是 expired
    session.query(Organization).filter(Organization.id == org_id).update({Organization.status: "expired"})
    session.query(UserSubscription).filter(UserSubscription.tenant_id == org_id).update(
        {UserSubscription.status: "suspended"}
    )
    session.commit()

    stats = run_tenant_billing_check(session)
    org = session.get(Organization, org_id)
    sub = session.query(UserSubscription).filter(UserSubscription.tenant_id == org_id).first()
    session.close()

    assert stats == {"expired": 0, "restored": 1}
    assert org.status == "active"
    assert sub.status == "active"


def test_renew_tenant_restores_and_records_order(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    _seed_expiring_org_and_sub(tenant_session, org_id=org_id, past=True)

    # 置为 expired + 订阅挂起，走续费接口立即恢复
    session = tenant_session()
    session.query(Organization).filter(Organization.id == org_id).update({Organization.status: "expired"})
    session.query(UserSubscription).filter(UserSubscription.tenant_id == org_id).update(
        {UserSubscription.status: "suspended"}
    )
    session.commit()
    session.close()

    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        resp = client.post(f"/admin/tenants/{org_id}/renew", json={"months": 3, "amount": 9900})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "active"
        assert data["expires_at"] is not None

    session = tenant_session()
    org = session.get(Organization, org_id)
    sub = session.query(UserSubscription).filter(UserSubscription.tenant_id == org_id).first()
    order = session.query(SubscriptionOrder).filter(SubscriptionOrder.tenant_id == org_id).first()
    audit = session.query(AuditLog).filter(AuditLog.action == "tenant.renew").first()
    session.close()

    assert org.status == "active"
    assert sub.status == "active"
    assert sub.end_at >= utc_now_naive()
    assert order is not None and order.status == "paid" and float(order.amount) == 9900.0
    assert audit is not None and audit.resource_id == str(org_id)


def test_renew_tenant_validation(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        assert client.post(f"/admin/tenants/{org_id}/renew", json={"months": 0}).status_code == 400
        assert client.post(f"/admin/tenants/{org_id}/renew", json={"months": 37}).status_code == 400
        assert client.post(f"/admin/tenants/{org_id}/renew", json={"months": 1, "amount": -5}).status_code == 400
        assert client.post("/admin/tenants/99999/renew", json={"months": 1}).status_code == 404


def test_renew_requires_admin_role(tenant_session):
    org_id = _seed(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        assert client.post(f"/admin/tenants/{org_id}/renew", json={"months": 1}).status_code == 403
