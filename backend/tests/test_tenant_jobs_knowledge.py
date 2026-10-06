"""T3-3 岗位库与知识库按租户挂载测试。

验收对应：「租户 A 导入的 JD/文档只出现在 A 的推荐与检索中；导入接口有校验与错误提示」。
覆盖：模型 tenant_id、推荐/检索/访问租户隔离、批量导入、管理端导入 API（校验/权限/404）。
API 部分使用独立 StaticPool 内存库 + 真实租户中间件（同 test_tenant_api）。
"""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.tenant_context import (
    TenantContext,
    reset_current_tenant,
    reset_tenant_session_factory,
    set_current_tenant,
    set_tenant_session_factory,
)
from app.core.user_roles import ADMIN_ROLE, CANDIDATE_ROLE
from app.models.history import JobDescription
from app.models.knowledge import KnowledgeDocument
from app.models.organization import Organization
from app.models.user import User
from app.services import rag_service
from app.services.job_recommend_engine import JobRecommendationEngine, batch_import_jobs
from app.utils import job_access, knowledge_access

_admin_user = User(id=1, username="admin", email="admin@example.com", role=ADMIN_ROLE)
_normal_user = User(id=2, username="candidate", email="c@example.com", role=CANDIDATE_ROLE)


# ===================== 工具 =====================


def _create_job(db, *, title, tenant_id=None, user_id=None, **overrides):
    job = JobDescription(
        title=title,
        company="Test Co",
        location="Beijing",
        salary_range="25k-35k",
        raw_text=f"{title} role",
        industry="AI",
        is_active=1,
        tenant_id=tenant_id,
        user_id=user_id,
        parsed_json={
            "title": title,
            "required_skills": ["python", "fastapi"],
            "experience_requirement": "3-5年",
        },
        **overrides,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _create_kb_doc(db, *, title, tenant_id=None, user_id=None, organization_id=None):
    doc = KnowledgeDocument(
        title=title,
        file_name=f"{title}.txt",
        file_type="txt",
        file_path=f"knowledge/{title}.txt",
        doc_type="general",
        status="ready",
        tenant_id=tenant_id,
        user_id=user_id,
        organization_id=organization_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@pytest.fixture(autouse=True)
def clear_recommend_cache():
    JobRecommendationEngine.clear_cache()
    yield
    JobRecommendationEngine.clear_cache()


@pytest.fixture
def tenant_ctx():
    """按需设置租户上下文，用例结束后按逆序复位。"""
    tokens = []

    def _set(tenant_id: int, name: str = "租户"):
        ctx = TenantContext(tenant_id=tenant_id, name=name)
        tokens.append(set_current_tenant(ctx))
        return ctx

    yield _set

    for token in reversed(tokens):
        reset_current_tenant(token)


@contextlib.contextmanager
def _create_job_with_embedding_patches():
    with (
        patch("app.services.job_recommend_engine.get_knowledge_collection", return_value=MagicMock()),
        patch(
            "app.services.job_recommend_engine.embed_texts",
            side_effect=lambda texts: [[1.0, 0.0] for _ in texts],
        ),
    ):
        yield


# ===================== 模型：tenant_id =====================


def test_models_have_tenant_id_column(db_session):
    assert "tenant_id" in JobDescription.__table__.columns
    assert "tenant_id" in KnowledgeDocument.__table__.columns


# ===================== 推荐隔离 =====================


def test_recommend_scopes_jobs_by_tenant(db_session, make_resume, tenant_ctx):
    tenant_ctx(1)
    _create_job(db_session, title="Tenant1 Job", tenant_id=1)
    _create_job(db_session, title="Tenant2 Job", tenant_id=2)
    _create_job(db_session, title="Platform Job", tenant_id=None)
    resume_id = make_resume(
        user_id=1,
        parsed_json={
            "name": "User",
            "skills": ["python", "fastapi"],
            "years_exp": 4,
            "location": "Beijing",
            "expected_salary": "20k-30k",
        },
    )

    with _create_job_with_embedding_patches():
        engine = JobRecommendationEngine(db_session)
        results = engine.recommend(resume_id=resume_id, limit=10, bypass_cache=True)

    titles = [item["job_title"] for item in results]
    assert "Tenant1 Job" in titles
    assert "Platform Job" in titles
    assert "Tenant2 Job" not in titles


def test_recommend_other_tenant_sees_its_own_jobs(db_session, make_resume, tenant_ctx):
    tenant_ctx(2)
    _create_job(db_session, title="Tenant1 Job", tenant_id=1)
    _create_job(db_session, title="Tenant2 Job", tenant_id=2)
    _create_job(db_session, title="Platform Job", tenant_id=None)
    resume_id = make_resume(
        user_id=1,
        parsed_json={
            "name": "User",
            "skills": ["python", "fastapi"],
            "years_exp": 4,
            "location": "Beijing",
            "expected_salary": "20k-30k",
        },
    )

    with _create_job_with_embedding_patches():
        engine = JobRecommendationEngine(db_session)
        results = engine.recommend(resume_id=resume_id, limit=10, bypass_cache=True)

    titles = [item["job_title"] for item in results]
    assert "Tenant2 Job" in titles
    assert "Tenant1 Job" not in titles
    assert "Platform Job" in titles


# ===================== 批量导入 =====================


def test_batch_import_jobs_sets_tenant(db_session):
    ids = batch_import_jobs(
        db_session,
        [{"title": "A Job", "raw_text": "desc", "industry": "AI"}],
        source="tenant-import",
        tenant_id=7,
    )
    assert len(ids) == 1
    jd = db_session.get(JobDescription, ids[0])
    assert jd.tenant_id == 7
    assert jd.source == "tenant-import"
    assert jd.user_id is None


def test_batch_import_jobs_platform_keeps_tenant_null(db_session):
    ids = batch_import_jobs(db_session, [{"title": "Platform Job", "raw_text": "desc"}], source="imported")
    assert db_session.get(JobDescription, ids[0]).tenant_id is None


# ===================== 岗位详情访问隔离 =====================


def test_job_access_requires_same_tenant(db_session, tenant_ctx):
    tenant_ctx(1)
    a_job = _create_job(db_session, title="A", tenant_id=1)
    b_job = _create_job(db_session, title="B", tenant_id=2)
    user = User(id=99, username="candidate", email="c@x.com", role=CANDIDATE_ROLE)

    assert job_access.can_access_job(a_job, user) is True
    assert job_access.can_access_job(b_job, user) is False


# ===================== 知识库可见性隔离 =====================


def test_knowledge_visibility_scopes_by_tenant(db_session, tenant_ctx):
    tenant_ctx(1)
    a_doc = _create_kb_doc(db_session, title="A", tenant_id=1)
    b_doc = _create_kb_doc(db_session, title="B", tenant_id=2)
    plat_doc = _create_kb_doc(db_session, title="P", tenant_id=None)

    visible = knowledge_access.get_visible_knowledge_doc_ids(db_session, user_id=None)
    assert str(a_doc.id) in visible
    assert str(plat_doc.id) in visible
    assert str(b_doc.id) not in visible


def test_knowledge_visibility_other_tenant_excludes_first(db_session, tenant_ctx):
    tenant_ctx(2)
    a_doc = _create_kb_doc(db_session, title="A", tenant_id=1)
    b_doc = _create_kb_doc(db_session, title="B", tenant_id=2)

    visible = knowledge_access.get_visible_knowledge_doc_ids(db_session, user_id=None)
    assert str(a_doc.id) not in visible
    assert str(b_doc.id) in visible


def test_rag_search_excludes_other_tenant_docs(db_session, tenant_ctx):
    tenant_ctx(1)
    a_doc = _create_kb_doc(db_session, title="A", tenant_id=1)
    b_doc = _create_kb_doc(db_session, title="B", tenant_id=2)

    collection = MagicMock()
    collection.count.return_value = 2
    collection.query.return_value = {
        "ids": [["c1", "c2"]],
        "documents": [["A chunk", "B chunk"]],
        "metadatas": [[{"doc_id": str(a_doc.id)}, {"doc_id": str(b_doc.id)}]],
        "distances": [[0.1, 0.2]],
    }
    with (
        patch("app.services.rag_service.get_knowledge_collection", return_value=collection),
        patch("app.services.rag_service.embed_text", return_value=[0.1, 0.2]),
    ):
        results = rag_service.search_knowledge("query", db=db_session)

    assert [item["doc_id"] for item in results] == [str(a_doc.id)]


def test_knowledge_personal_docs_not_visible_to_tenant_mates(db_session, tenant_ctx):
    """同租户用户之间不应互相看到彼此的个人知识文档（个人文档也盖了 tenant_id）。"""
    tenant_ctx(1)
    personal_a = _create_kb_doc(db_session, title="个人A", tenant_id=1, user_id=10)
    tenant_doc = _create_kb_doc(db_session, title="租户T", tenant_id=1)
    plat_doc = _create_kb_doc(db_session, title="平台P", tenant_id=None)

    other_visible = knowledge_access.get_visible_knowledge_doc_ids(db_session, user_id=99)
    assert str(tenant_doc.id) in other_visible  # 租户级文档可见
    assert str(plat_doc.id) in other_visible  # 平台共享可见
    assert str(personal_a.id) not in other_visible  # 他人个人文档不可见

    owner_visible = knowledge_access.get_visible_knowledge_doc_ids(db_session, user_id=10)
    assert str(personal_a.id) in owner_visible  # 本人可见


def test_rag_search_fail_closed_without_db():
    """无 DB 会话时 RAG 检索拒绝执行（fail-closed），返回空而非全量泄漏。"""
    assert rag_service.search_knowledge("Python开发") == []


def test_rag_multi_recall_fail_closed_without_db():
    """multi_recall 同样要求 DB 会话做可见性过滤，无 db 时拒绝检索。"""
    from app.services.multi_recall import multi_recall

    assert multi_recall("Python开发") == []


# ===================== 管理端导入 API =====================


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


def _seed_org(factory, *, name="客户A", slug="customer-a") -> int:
    session = factory()
    org = Organization(name=name, slug=slug, owner_id=1, status="active")
    session.add(org)
    session.commit()
    session.refresh(org)
    org_id = org.id
    session.close()
    return org_id
