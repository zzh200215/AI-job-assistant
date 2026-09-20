"""T2-3 租户上下文中间件测试。

验收对应：「curl 带/不带 X-Tenant-Id 行为符合预期；停用租户返回 403；单测覆盖 4 种场景」：
1. 无租户头 → 回落默认租户 id=1；
2. 无效租户（不存在）→ 403 code=-13；
3. 停用租户 → 403 code=-13；
4. 跨租户（Header 与 Host 同时命中）→ Header 优先。

额外覆盖：Host 域名绑定解析、非法 X-Tenant-Id 格式。
使用独立 StaticPool 内存库 + 可替换 Session 工厂，与 conftest 的 db_session 互不干扰。
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.tenant_context import (
    DEFAULT_TENANT_ID,
    TenantContext,
    require_tenant,
    reset_tenant_session_factory,
    set_tenant_session_factory,
    tenant_context_middleware,
)
from app.models.organization import ORGANIZATION_STATUS_SUSPENDED, Organization
from app.models.tenant import TenantDomainBinding


@pytest.fixture
def tenant_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def tenant_session(tenant_engine):
    factory = sessionmaker(bind=tenant_engine)
    set_tenant_session_factory(factory)
    yield factory
    reset_tenant_session_factory()


@pytest.fixture
def tenant_app(tenant_session):
    app = FastAPI()
    app.middleware("http")(tenant_context_middleware)

    @app.get("/tenant")
    def demo_tenant(tenant: TenantContext = Depends(require_tenant)):
        return {"tenant_id": tenant.tenant_id, "name": tenant.name}

    return app


@pytest.fixture
def client(tenant_app):
    with TestClient(tenant_app) as test_client:
        yield test_client


def _seed_org(factory, *, name: str = "租户A", slug: str = "tenant-a", status: str = "active") -> int:
    session = factory()
    org = Organization(name=name, slug=slug, owner_id=1, status=status)
    session.add(org)
    session.commit()
    session.refresh(org)
    org_id = org.id
    session.close()
    return org_id


def _seed_domain(factory, tenant_id: int, domain: str) -> None:
    session = factory()
    session.add(TenantDomainBinding(tenant_id=tenant_id, domain=domain, is_primary=1))
    session.commit()
    session.close()


# ---- 场景 1：无租户头 → 默认租户 ----


def test_no_tenant_header_falls_back_to_default(client):
    resp = client.get("/tenant")
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == DEFAULT_TENANT_ID


# ---- 场景 2：无效租户 → 403 ----


def test_nonexistent_tenant_returns_403(client):
    resp = client.get("/tenant", headers={"X-Tenant-Id": "999999"})
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == -13
    assert body["message"] == "租户不可用"


def test_malformed_tenant_header_returns_403(client):
    resp = client.get("/tenant", headers={"X-Tenant-Id": "abc"})
    assert resp.status_code == 403
    assert resp.json()["code"] == -13


# ---- 场景 3：停用租户 → 403 ----


def test_suspended_tenant_returns_403(client, tenant_session):
    org_id = _seed_org(tenant_session, slug="suspended-a", status=ORGANIZATION_STATUS_SUSPENDED)
    resp = client.get("/tenant", headers={"X-Tenant-Id": str(org_id)})
    assert resp.status_code == 403
    assert resp.json()["code"] == -13


# ---- 场景 4：跨租户，Header 优先于 Host ----


def test_cross_tenant_header_wins_over_host(tenant_app, tenant_session):
    host_org_id = _seed_org(tenant_session, name="Host租户", slug="host-b")
    _seed_domain(tenant_session, host_org_id, "corp.example.com")
    header_org_id = _seed_org(tenant_session, name="Header租户", slug="header-b")

    with TestClient(tenant_app, base_url="http://corp.example.com") as test_client:
        resp = test_client.get("/tenant", headers={"X-Tenant-Id": str(header_org_id)})

    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == header_org_id


# ---- 额外：Host 域名绑定解析 ----


def test_host_binding_resolves_tenant(tenant_app, tenant_session):
    org_id = _seed_org(tenant_session, name="客户A", slug="host-a")
    _seed_domain(tenant_session, org_id, "acme.example.com")

    with TestClient(tenant_app, base_url="http://acme.example.com") as test_client:
        resp = test_client.get("/tenant")

    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == org_id
    assert resp.json()["name"] == "客户A"
