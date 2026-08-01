"""T3-2 面试题型与评分规则配置化测试。

验收对应：「为租户 A 配置『偏前端技术面』题库与评分权重后，A 的面试题目与报告维度变化，B 租户不变」。
- 单元：_fallback_questions 租户题注入、_build_personalized_prompt 租户指令注入
- 服务层：题库/评分规则/报告模板三级回落与覆盖、跨租户隔离
- API：GET /interview/config/types 租户化、PUT /admin/interview-config 配置与权限
- 端到端：create_session 使用租户题库（patch SessionLocal 到内存库、mock LLM）
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import interview_rest
from app.api.auth import get_current_user
from app.api.interview_rest import _build_personalized_prompt, _fallback_questions
from app.core.database import Base, get_db
from app.core.tenant_context import (
    reset_tenant_session_factory,
    set_tenant_session_factory,
    tenant_context_middleware,
)
from app.core.user_roles import ADMIN_ROLE, CANDIDATE_ROLE
from app.models.history import JobDescription, Resume
from app.models.organization import Organization
from app.models.user import User
from app.services.interview_config_service import (
    get_question_bank,
    get_report_template,
    get_scoring_rules,
    list_question_banks,
)

_admin_user = User(id=1, username="admin", email="admin@example.com", role=ADMIN_ROLE)
_normal_user = User(id=2, username="candidate", email="c@example.com", role=CANDIDATE_ROLE)

CUSTOM_QUESTIONS = [
    {"type": "tech", "question": "请解释 Vue 3 响应式系统的实现原理。", "intent": "前端框架理解", "ref_answer": "Proxy + effect 依赖收集。"},
    {"type": "tech", "question": "讲一次你用 TypeScript 重构遗留代码的经历。", "intent": "前端工程化", "ref_answer": "类型边界、渐进迁移、回归验证。"},
    {"type": "project", "question": "描述一个你负责的前端性能优化案例。", "intent": "前端性能", "ref_answer": "指标、瓶颈定位、优化措施与收益。"},
]


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


def _seed_custom_bank(factory, *, tenant_id: int, bank_type: str = "tech", title: str = "前端技术面", questions=None):
    session = factory()
    from app.models.interview_config import InterviewQuestionBank

    session.add(
        InterviewQuestionBank(
            tenant_id=tenant_id,
            type=bank_type,
            title=title,
            prompt_template="重点考察前端基础：Vue/React、TypeScript、工程化与性能优化。",
            questions=questions if questions is not None else CUSTOM_QUESTIONS,
            tags=["前端", "技术"],
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
    app.include_router(interview_rest.router, prefix="/interview")
    return app


# ===== 单元：题库注入 =====


def test_fallback_questions_use_tenant_custom_questions():
    questions = _fallback_questions("前端工程师", ["Vue"], "tech", custom_questions=CUSTOM_QUESTIONS)
    assert len(questions) == len(CUSTOM_QUESTIONS)
    assert questions[0]["question"] == CUSTOM_QUESTIONS[0]["question"]
    assert all(q["source"] == "tenant_config" for q in questions)
    # 非法项被过滤
    dirty = CUSTOM_QUESTIONS + [{"type": "tech", "question": ""}]
    assert len(_fallback_questions("x", [], "tech", custom_questions=dirty)) == len(CUSTOM_QUESTIONS)


def test_fallback_questions_fallback_to_builtin_without_custom():
    questions = _fallback_questions("后端工程师", ["Python"], "tech")
    assert len(questions) == 10
    assert questions[0]["source"] == "starter"


def test_personalized_prompt_injects_tenant_template(mocker):
    mocker.patch("app.api.interview_rest.search_knowledge", return_value=[])
    prompt = _build_personalized_prompt(
        resume_json={},
        jd_json={},
        jd_title="前端工程师",
        required_skills=["Vue"],
        interview_type="tech",
        search_types=["interview_q"],
        prompt_template="重点考察前端基础：Vue/React、TypeScript。",
    )
    assert "重点考察前端基础：Vue/React、TypeScript。" in prompt
    # 未配置时使用内置指令
    default_prompt = _build_personalized_prompt(
        resume_json={}, jd_json={}, jd_title="x", required_skills=[], interview_type="tech", search_types=[]
    )
    assert "技术题和项目题占比更高" in default_prompt


# ===== 服务层 =====


def test_question_bank_three_level_resolution(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    _seed_custom_bank(tenant_session, tenant_id=org_a)

    db = tenant_session()
    try:
        assert get_question_bank(db, org_a, "tech").title == "前端技术面"  # 租户自定义
        assert get_question_bank(db, org_a, "hr") is None  # 未配置 → None（回落内置）
        assert get_question_bank(db, 999, "tech") is None  # 其他租户不受影响
    finally:
        db.close()


def test_list_question_banks_custom_overrides_title(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    _seed_custom_bank(tenant_session, tenant_id=org_a, bank_type="tech", title="前端技术面")

    db = tenant_session()
    try:
        banks_a = {b["type"]: b for b in list_question_banks(db, org_a)}
        banks_default = {b["type"]: b for b in list_question_banks(db, 1)}
    finally:
        db.close()

    assert set(banks_a) == {"tech", "hr", "comprehensive", "stress", "group"}
    assert banks_a["tech"]["title"] == "前端技术面"
    assert banks_a["tech"]["is_custom"] is True
    assert banks_a["hr"]["is_custom"] is False  # 未配置回落内置
    assert banks_default["tech"]["title"] == "技术深挖"  # 默认租户不变


def test_scoring_rules_default_and_custom(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    session = tenant_session()
    try:
        defaults = get_scoring_rules(session, org_a)
        assert [r["dimension"] for r in defaults] == ["completeness", "accuracy", "depth", "expression"]
        assert defaults[0]["weight"] == 0.30

        from app.models.interview_config import InterviewScoringRule

        session.add(
            InterviewScoringRule(tenant_id=org_a, dimension="completeness", label="要点覆盖", weight=0.10, sort_order=0)
        )
        session.add(
            InterviewScoringRule(tenant_id=org_a, dimension="expression", label="表达", weight=0.60, sort_order=1)
        )
        session.commit()

        custom = get_scoring_rules(session, org_a)
        assert len(custom) == 2
        assert {r["dimension"] for r in custom} == {"completeness", "expression"}
        assert custom[0]["weight"] == 0.10
        assert custom[0]["label"] == "要点覆盖"
        # 其他租户不受影响
        other = get_scoring_rules(session, 999)
        assert len(other) == 4
    finally:
        session.close()


def test_report_template_default_and_custom(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    session = tenant_session()
    try:
        assert get_report_template(session, org_a) is None  # 未配置回落内置
        from app.models.interview_config import InterviewReportTemplate

        session.add(InterviewReportTemplate(tenant_id=org_a, template="# 前端专项面试报告"))
        session.commit()
        assert get_report_template(session, org_a) == "# 前端专项面试报告"
        assert get_report_template(session, 999) is None  # 其他租户不受影响
    finally:
        session.close()


# ===== API 层 =====


def test_api_config_types_tenant_scoped(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    _seed_custom_bank(tenant_session, tenant_id=org_a)

    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        resp_a = client.get("/interview/config/types", headers={"X-Tenant-Id": str(org_a)})
        resp_default = client.get("/interview/config/types")

    assert resp_a.status_code == 200
    items_a = {i["type"]: i for i in resp_a.json()["data"]["items"]}
    assert items_a["tech"]["title"] == "前端技术面"
    assert items_a["tech"]["is_custom"] is True

    items_default = {i["type"]: i for i in resp_default.json()["data"]["items"]}
    assert items_default["tech"]["title"] == "技术深挖"  # 默认租户不受影响


def test_api_admin_upsert_question_bank(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")

    app_admin = _build_app(tenant_session, user=_admin_user)
    with TestClient(app_admin) as client:
        resp = client.put(
            "/interview/admin/interview-config",
            json={
                "config_type": "question_bank",
                "tenant_id": org_a,
                "type": "tech",
                "title": "前端技术面",
                "prompt_template": "重点考察前端基础。",
                "questions": CUSTOM_QUESTIONS,
                "tags": ["前端"],
            },
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["question_count"] == len(CUSTOM_QUESTIONS)

    # 租户 A 的 config/types 变化
    app_user = _build_app(tenant_session, user=_normal_user)
    with TestClient(app_user) as client:
        resp2 = client.get("/interview/config/types", headers={"X-Tenant-Id": str(org_a)})
    tech = {i["type"]: i for i in resp2.json()["data"]["items"]}["tech"]
    assert tech["title"] == "前端技术面"
    assert tech["prompt_template"] == "重点考察前端基础。"


def test_api_admin_upsert_scoring_rules_and_report_template(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")

    app_admin = _build_app(tenant_session, user=_admin_user)
    with TestClient(app_admin) as client:
        resp = client.put(
            "/interview/admin/interview-config",
            json={
                "config_type": "scoring_rules",
                "tenant_id": org_a,
                "rules": [
                    {"dimension": "completeness", "label": "要点覆盖", "weight": 0.10},
                    {"dimension": "expression", "label": "表达", "weight": 0.60},
                ],
            },
        )
        resp_tpl = client.put(
            "/interview/admin/interview-config",
            json={"config_type": "report_template", "tenant_id": org_a, "template": "# 前端专项面试报告"},
        )
        resp_bad = client.put(
            "/interview/admin/interview-config",
            json={"config_type": "scoring_rules", "tenant_id": org_a, "rules": [{"dimension": "unknown"}]},
        )
    assert resp.status_code == 200
    assert resp.json()["data"]["rule_count"] == 2
    assert resp_tpl.status_code == 200
    # 非法维度被拒绝（fail 惯例：HTTP 200 + code != 0）
    assert resp_bad.json()["code"] != 0

    db = tenant_session()
    try:
        rules = get_scoring_rules(db, org_a)
        assert len(rules) == 2 and rules[0]["label"] == "要点覆盖" and rules[0]["weight"] == 0.10
        assert get_report_template(db, org_a) == "# 前端专项面试报告"
    finally:
        db.close()


def test_api_admin_config_forbidden_for_normal_user(tenant_session):
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        resp = client.put(
            "/interview/admin/interview-config",
            json={"config_type": "question_bank", "tenant_id": org_a, "type": "tech"},
        )
    assert resp.status_code != 200  # 403


# ===== 端到端：创建面试使用租户题库 =====


def test_create_session_uses_tenant_question_bank(tenant_session, mocker):
    """验收核心：租户 A 配置题库后，A 创建的面试题目来自租户配置，B 租户不变。"""
    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    org_b = _seed_org(tenant_session, name="客户B", slug="customer-b")
    _seed_custom_bank(tenant_session, tenant_id=org_a)

    # 背景任务改走内存库 + mock LLM（返回空，题目回落 fallback=租户题）
    mocker.patch("app.api.interview_rest.SessionLocal", tenant_session)
    mocker.patch("app.api.interview_rest.chat_json", return_value={})

    def _seed_user_data(org_id: int):
        session = tenant_session()
        resume = Resume(user_id=_normal_user.id, file_name=f"r{org_id}.pdf", file_path=f"uploads/r{org_id}.pdf", parsed_json={"name": "张三", "skills": ["Vue"]})
        jd = JobDescription(user_id=_normal_user.id, title="前端工程师", raw_text="招聘前端工程师", parsed_json={"title": "前端工程师", "required_skills": ["Vue"]})
        session.add_all([resume, jd])
        session.commit()
        session.refresh(resume)
        session.refresh(jd)
        ids = (resume.id, jd.id)
        session.close()
        return ids

    resume_a, jd_a = _seed_user_data(org_a)
    resume_b, jd_b = _seed_user_data(org_b)

    app = _build_app(tenant_session, user=_normal_user)
    with TestClient(app) as client:
        resp_a = client.post(
            "/interview/sessions",
            headers={"X-Tenant-Id": str(org_a)},
            json={"resume_id": resume_a, "jd_id": jd_a, "interview_type": "tech"},
        )
        resp_b = client.post(
            "/interview/sessions",
            headers={"X-Tenant-Id": str(org_b)},
            json={"resume_id": resume_b, "jd_id": jd_b, "interview_type": "tech"},
        )

    assert resp_a.status_code == 200
    questions_a = resp_a.json()["data"]["questions"]
    questions_b = resp_b.json()["data"]["questions"]

    assert questions_a[0]["source"] == "tenant_config"
    assert questions_a[0]["question"] == CUSTOM_QUESTIONS[0]["question"]
    assert len(questions_a) == len(CUSTOM_QUESTIONS)
    # B 租户不受影响：内置 starter 题库
    assert questions_b[0]["source"] == "starter"
    assert len(questions_b) == 10


def test_background_personalization_does_not_override_custom_bank(tenant_session, mocker):
    """T3-2：租户自定义题库优先，后台个性化不得把自定义题换成通用题（#8）。"""
    from app.api.interview_rest import _fallback_questions, _personalize_unstarted_questions
    from app.models.interview_session import InterviewSession
    from app.services.interview_config_service import get_question_bank

    org_a = _seed_org(tenant_session, name="客户A", slug="customer-a")
    _seed_custom_bank(tenant_session, tenant_id=org_a)
    mocker.patch("app.api.interview_rest.SessionLocal", tenant_session)
    mocker.patch("app.api.interview_rest.chat_json", return_value={})  # 若被调用不应真实 LLM

    session = tenant_session()
    resume = Resume(
        user_id=_normal_user.id, file_name="r.pdf", file_path="uploads/r.pdf",
        parsed_json={"name": "张三", "skills": ["Vue"]},
    )
    jd = JobDescription(
        user_id=_normal_user.id, title="前端工程师", raw_text="招聘前端工程师",
        parsed_json={"title": "前端工程师", "required_skills": ["Vue"]},
    )
    session.add_all([resume, jd])
    session.commit()
    session.refresh(resume)
    session.refresh(jd)

    bank = get_question_bank(session, org_a, "tech")
    ordered = _fallback_questions("前端工程师", ["Vue"], "tech", custom_questions=bank.questions if bank else None)
    isess = InterviewSession(
        user_id=_normal_user.id,
        resume_id=resume.id,
        jd_id=jd.id,
        interview_type="tech",
        status="created",
        questions=ordered,
        messages=[],
        evaluation={},
        evaluation_status="idle",
        memory_snapshot={"question_generation": {"status": "pending"}},
        total_questions=len(ordered),
        answered_count=0,
        timeout_count=0,
        tenant_id=org_a,
    )
    session.add(isess)
    session.commit()
    session.refresh(isess)
    sid = isess.id
    session.close()

    # 同步执行后台个性化，模拟 BackgroundTasks 生效路径
    _personalize_unstarted_questions(
        sid,
        {"name": "张三", "skills": ["Vue"]},
        {"title": "前端工程师", "required_skills": ["Vue"]},
        "前端工程师",
        ["Vue"],
        "tech",
        ["interview_q", "skill_model"],
    )

    check = tenant_session()
    try:
        updated = check.get(InterviewSession, sid)
        assert updated.memory_snapshot["question_generation"]["status"] == "custom_bank"
        assert updated.questions[0]["source"] == "tenant_config"
        assert len(updated.questions) == len(CUSTOM_QUESTIONS)
    finally:
        check.close()
