"""T4-2 租户级报表测试。

验收对应：「选择不同租户，漏斗与收入数据随之变化；两个租户的 tracking 数据互不串」。
覆盖：funnel/summary/retention 的 tenant_id 过滤隔离、revenue 按租户汇总、
租户不存在 404、非管理员 403。
使用独立 StaticPool 内存库 + 真实租户中间件（同 test_tenant_api）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import analytics as analytics_api
from app.api.auth import get_current_user
from app.core.database import Base, get_db
from app.core.tenant_context import (
    reset_tenant_session_factory,
    set_tenant_session_factory,
    tenant_context_middleware,
)
from app.core.user_roles import ADMIN_ROLE, CANDIDATE_ROLE
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.interview_session import InterviewSession
from app.models.organization import Organization
from app.models.subscription import SubscriptionOrder, UserSubscription
from app.models.user import User

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


def _seed_org(factory, *, name: str, slug: str) -> int:
    session = factory()
    org = Organization(name=name, slug=slug, owner_id=1, status="active")
    session.add(org)
    session.commit()
    session.refresh(org)
    org_id = org.id
    session.close()
    return org_id


def _seed_business(factory, tenant_a: int, tenant_b: int):
    session = factory()
    u1 = User(username="user-a", password="x", role=CANDIDATE_ROLE)
    u2 = User(username="user-b", password="x", role=CANDIDATE_ROLE)
    session.add_all([u1, u2])
    session.commit()
    session.refresh(u1)
    session.refresh(u2)

    # 租户 A：1 简历 + 1 分析 + 1 面试 + 1 订单(1000 分, paid) + 1 pro 订阅
    jd_a = JobDescription(title="JD-A", raw_text="desc", tenant_id=tenant_a)
    r_a = Resume(user_id=u1.id, tenant_id=tenant_a, file_name="a.pdf", file_path="/a.pdf")
    session.add_all([jd_a, r_a])
    session.commit()
    session.refresh(jd_a)
    session.refresh(r_a)
    session.add(AnalysisRecord(user_id=u1.id, resume_id=r_a.id, jd_id=jd_a.id, tenant_id=tenant_a))
    session.add(InterviewSession(user_id=u1.id, tenant_id=tenant_a, status="completed"))
    session.add(
        SubscriptionOrder(user_id=u1.id, plan_tier="pro", amount=1000, status="paid", tenant_id=tenant_a)
    )
    session.add(UserSubscription(user_id=u1.id, plan_tier="pro", status="active", tenant_id=tenant_a))

    # 租户 B：1 简历 + 1 分析 + 1 面试 + 1 订单(2000 分, paid)
    jd_b = JobDescription(title="JD-B", raw_text="desc", tenant_id=tenant_b)
    r_b = Resume(user_id=u2.id, tenant_id=tenant_b, file_name="b.pdf", file_path="/b.pdf")
    session.add_all([jd_b, r_b])
    session.commit()
    session.refresh(jd_b)
    session.refresh(r_b)
    session.add(AnalysisRecord(user_id=u2.id, resume_id=r_b.id, jd_id=jd_b.id, tenant_id=tenant_b))
    session.add(InterviewSession(user_id=u2.id, tenant_id=tenant_b, status="completed"))
    session.add(
        SubscriptionOrder(user_id=u2.id, plan_tier="enterprise", amount=2000, status="paid", tenant_id=tenant_b)
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
    app.include_router(analytics_api.router, prefix="/analytics")
    app.include_router(analytics_api.admin_router, prefix="/admin")
    return app


# ---- 漏斗按租户隔离 ----

def test_funnel_scoped_by_tenant(tenant_session):
    a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    b = _seed_org(tenant_session, name="客户B", slug="customer-b")
    _seed_business(tenant_session, a, b)
    app = _build_app(tenant_session, user=_admin_user)

    with TestClient(app) as client:
        fa = client.get("/analytics/funnel", params={"tenant_id": a}).json()["data"]
        fb = client.get("/analytics/funnel", params={"tenant_id": b}).json()["data"]

    sa = {s["key"]: s["count"] for s in fa["steps"]}
    sb = {s["key"]: s["count"] for s in fb["steps"]}
    # A 只见 A 的数据：各业务步骤恰 1
    assert sa["uploaded"] == 1
    assert sa["analyzed"] == 1
    assert sa["interviewed"] == 1
    assert sa["subscribed"] == 1
    # B 只见 B 的数据
    assert sb["uploaded"] == 1
    assert sb["subscribed"] == 1
    # 互不串：A 的订单不进入 B 的漏斗
    assert sa["subscribed"] == sb["subscribed"] == 1


def test_summary_scoped_by_tenant(tenant_session):
    a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    b = _seed_org(tenant_session, name="客户B", slug="customer-b")
    _seed_business(tenant_session, a, b)
    app = _build_app(tenant_session, user=_admin_user)

    with TestClient(app) as client:
        sa = client.get("/analytics/summary", params={"tenant_id": a}).json()["data"]
        sb = client.get("/analytics/summary", params={"tenant_id": b}).json()["data"]
        all_ = client.get("/analytics/summary").json()["data"]

    assert sa["total_resumes"] == 1
    assert sa["total_analyses"] == 1
    assert sa["total_interviews"] == 1
    assert sa["paid_orders"] == 1
    assert sa["pro_users"] == 1

    assert sb["paid_orders"] == 1
    assert sb["pro_users"] == 0  # B 无 pro 订阅

    # 平台级：两租户数据合计
    assert all_["paid_orders"] == 2
    assert all_["total_resumes"] == 2


def test_retention_scoped_by_tenant(tenant_session):
    a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    b = _seed_org(tenant_session, name="客户B", slug="customer-b")
    _seed_business(tenant_session, a, b)

    # 补队列：注册/产生业务行为于 [now-14, now-7] 的租户 A 用户，
    # 且最近 7 天（[now-7, now]）有分析行为 → 应进入 d7 队列且被计为留存。
    now = datetime.utcnow()
    session = tenant_session()
    try:
        u_cohort = User(
            username="cohort_a", password="x", role=CANDIDATE_ROLE,
            created_at=now - timedelta(days=10),
        )
        session.add(u_cohort)
        session.commit()
        session.refresh(u_cohort)
        r = Resume(
            user_id=u_cohort.id, tenant_id=a, file_name="ca.pdf", file_path="/ca.pdf",
            create_time=now - timedelta(days=10),  # 队列窗口内的业务行为
        )
        jd = JobDescription(title="JD-C", raw_text="desc", tenant_id=a)
        session.add_all([r, jd])
        session.commit()
        session.refresh(r)
        session.refresh(jd)
        session.add(
            AnalysisRecord(
                user_id=u_cohort.id, resume_id=r.id, jd_id=jd.id, tenant_id=a,
                create_time=now - timedelta(days=3),  # 活跃窗口内的分析行为
            )
        )
        session.commit()
    finally:
        session.close()

    app = _build_app(tenant_session, user=_admin_user)

    with TestClient(app) as client:
        ra = client.get("/analytics/retention", params={"tenant_id": a}).json()["data"]
        rb = client.get("/analytics/retention", params={"tenant_id": b}).json()["data"]

    assert ra["daily_active"][-1]["active_users"] == 1  # 今天 A 的分析活跃 1
    assert rb["daily_active"][-1]["active_users"] == 1
    # 队列口径：A 有 1 名 7 天前队列用户且最近 7 天活跃 → d7=100%
    assert ra["retention"]["d7_cohort_size"] == 1
    assert ra["retention"]["d7"] == 100.0
    # 租户隔离：B 无队列用户 → d7=0
    assert rb["retention"]["d7_cohort_size"] == 0
    assert rb["retention"]["d7"] == 0.0
    # 定义修复：d7/d14/d30 各自独立队列，队列错开不再恒等 → 只有 d7 窗口有队列用户，d14/d30 为 0
    assert ra["retention"]["d14"] == 0.0
    assert ra["retention"]["d30"] == 0.0


# ---- 收入汇总 ----

def test_revenue_scoped_and_grouped(tenant_session):
    a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    b = _seed_org(tenant_session, name="客户B", slug="customer-b")
    _seed_business(tenant_session, a, b)
    app = _build_app(tenant_session, user=_admin_user)

    with TestClient(app) as client:
        single = client.get("/admin/analytics/revenue", params={"tenant_id": a}).json()["data"]
        grouped = client.get("/admin/analytics/revenue").json()["data"]

    assert single["total_amount"] == 1000.0
    assert single["order_count"] == 1
    assert single["by_tier"] == {"pro": 1000.0}

    by_id = {item["tenant_id"]: item for item in grouped["items"]}
    assert by_id[a]["amount"] == 1000.0
    assert by_id[b]["amount"] == 2000.0
    assert grouped["total_amount"] == 3000.0
    assert grouped["order_count"] == 2


# ---- 校验与权限 ----

def test_analytics_tenant_not_found_404(tenant_session):
    app = _build_app(tenant_session, user=_admin_user)
    with TestClient(app) as client:
        assert client.get("/analytics/summary", params={"tenant_id": 99999}).status_code == 404
        assert client.get("/analytics/funnel", params={"tenant_id": 99999}).status_code == 404
        assert (
            client.get("/admin/analytics/revenue", params={"tenant_id": 99999}).status_code == 404
        )


def test_analytics_require_admin_role(tenant_session):
    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        assert client.get("/analytics/summary").status_code == 403
        assert client.get("/analytics/funnel").status_code == 403
        assert client.get("/admin/analytics/revenue").status_code == 403
