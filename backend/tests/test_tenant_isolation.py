"""T2-4 跨租户隔离测试。

验收对应：「跨租户测试全绿」——A 租户上下文访问 B 租户数据为空/403；写入自动带租户。

覆盖：
1. `stamp_tenant`：写入自动打上当前租户（单元，用 conftest db_session）；
2. `tenant_filter`：查询只返回当前租户数据（单元）；
3. 端到端（中间件 + 租户过滤路由）：A/B 租户互不可见；无租户回落默认租户 1（空）；
4. 端到端写入：租户 A 上下文创建的简历自动归属 A。
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.tenant_context import (
    TenantContext,
    reset_current_tenant,
    reset_tenant_session_factory,
    set_current_tenant,
    set_tenant_session_factory,
    stamp_tenant,
    tenant_context_middleware,
    tenant_filter,
)
from app.models.history import Resume
from app.models.organization import Organization

# ===== 单元：stamp_tenant / tenant_filter（conftest db_session） =====


def test_stamp_tenant_sets_current_tenant(db_session):
    token = set_current_tenant(TenantContext(tenant_id=42, name="租户A"))
    try:
        row = stamp_tenant(Resume(user_id=1, file_name="a.pdf", file_path="/tmp/a", raw_text="x"))
        assert row.tenant_id == 42
    finally:
        reset_current_tenant(token)


def test_stamp_tenant_falls_back_to_default(db_session):
    row = stamp_tenant(Resume(user_id=1, file_name="a.pdf", file_path="/tmp/a", raw_text="x"))
    assert row.tenant_id == 1


def test_tenant_filter_returns_only_current_tenant_rows(db_session):
    a = Resume(user_id=1, file_name="a.pdf", file_path="/tmp/a", raw_text="x", tenant_id=1)
    b = Resume(user_id=1, file_name="b.pdf", file_path="/tmp/b", raw_text="y", tenant_id=7)
    db_session.add_all([a, b])
    db_session.commit()

    token = set_current_tenant(TenantContext(tenant_id=1, name="默认"))
    try:
        ids = [r.id for r in db_session.query(Resume).filter(tenant_filter(Resume)).all()]
        assert ids == [a.id]
    finally:
        reset_current_tenant(token)

    token2 = set_current_tenant(TenantContext(tenant_id=7, name="租户B"))
    try:
        ids = [r.id for r in db_session.query(Resume).filter(tenant_filter(Resume)).all()]
        assert ids == [b.id]
    finally:
        reset_current_tenant(token2)


# ===== 端到端：独立 StaticPool 引擎 + 真实中间件 =====


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


def _seed_org(factory, slug: str, org_id: int | None = None) -> int:
    session = factory()
    org = Organization(name=f"租户-{slug}", slug=slug, owner_id=1, status="active")
    if org_id is not None:
        org.id = org_id  # 显式指定 id，避免与内置默认租户 1 冲突
    session.add(org)
    session.commit()
    session.refresh(org)
    resolved_id = org.id
    session.close()
    return resolved_id


def _seed_resume(factory, tenant_id: int, file_name: str) -> int:
    session = factory()
    row = Resume(user_id=1, file_name=file_name, file_path=f"/tmp/{file_name}", raw_text="x", tenant_id=tenant_id)
    session.add(row)
    session.commit()
    session.refresh(row)
    row_id = row.id
    session.close()
    return row_id


def _build_iso_app(factory):
    """带真实租户中间件 + 使用 tenant_filter 的简历列表/创建路由。"""
    app = FastAPI()
    app.middleware("http")(tenant_context_middleware)

    def _get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db

    @app.get("/resumes")
    def list_resumes(db: Session = Depends(get_db)):
        rows = db.query(Resume).filter(tenant_filter(Resume)).order_by(Resume.id).all()
        return {"items": [{"id": r.id, "tenant_id": r.tenant_id} for r in rows]}

    @app.post("/resumes")
    def create_resume(db: Session = Depends(get_db)):
        row = stamp_tenant(Resume(user_id=1, file_name="new.pdf", file_path="/tmp/new", raw_text="x"))
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"id": row.id, "tenant_id": row.tenant_id}

    return app


def test_cross_tenant_read_isolation(tenant_session):
    tenant_a = _seed_org(tenant_session, slug="isolation-a", org_id=100)
    tenant_b = _seed_org(tenant_session, slug="isolation-b", org_id=200)
    resume_a = _seed_resume(tenant_session, tenant_id=tenant_a, file_name="A.pdf")
    resume_b = _seed_resume(tenant_session, tenant_id=tenant_b, file_name="B.pdf")

    app = _build_iso_app(tenant_session)
    with TestClient(app) as client:
        # A 租户只看到 A 的数据
        resp_a = client.get("/resumes", headers={"X-Tenant-Id": str(tenant_a)})
        # B 租户只看到 B 的数据（跨租户互不可见）
        resp_b = client.get("/resumes", headers={"X-Tenant-Id": str(tenant_b)})
        # 无租户头 → 默认租户 1，看不到 A/B 的数据
        resp_default = client.get("/resumes")

    assert [i["id"] for i in resp_a.json()["items"]] == [resume_a]
    assert [i["id"] for i in resp_b.json()["items"]] == [resume_b]
    assert resp_default.json()["items"] == []


def test_cross_tenant_write_stamps_tenant(tenant_session):
    tenant_a = _seed_org(tenant_session, slug="write-a", org_id=100)
    _seed_org(tenant_session, slug="write-b", org_id=200)  # 存在另一个租户，写请求才谈得上"盖对了租户"

    app = _build_iso_app(tenant_session)
    with TestClient(app) as client:
        resp = client.post("/resumes", headers={"X-Tenant-Id": str(tenant_a)})

    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == tenant_a
