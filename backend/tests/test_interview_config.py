"""面试题型与评分规则配置化测试（两级回落：平台配置 → 内置常量）。

2026-10-06 真删企业侧第六增量（D136，§10.32 他点「整族拆到底」）之前，这一族是**三级**
（租户自定义 → 平台默认 → 内置），本文件也就照着那句验收写："给租户 A 配『偏前端技术面』
后 A 变、B 不变"。租户那一级与 `PUT /admin/interview-config`（三张表唯一的写入端）一起出树之后：
- 跨租户隔离那三条断言**没有对应行为了**，删；
- `InterviewReportTemplate` / `get_report_template` 一起删——后者在生产里从来没有调用方，
  所以"自定义报告模板"这句话从没落到过屏幕上；
- 留下来的用例测的是"平台行覆盖内置"这一级，以及自定义静态题在创建与后台个性化两条路上
  都不被通用题替换掉（#8 那条老缺陷）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.interview_rest import _build_personalized_prompt, _fallback_questions
from app.core.database import Base
from app.core.user_roles import CANDIDATE_ROLE
from app.models.history import JobDescription, Resume
from app.models.user import User
from app.services.interview_config_service import (
    get_question_bank,
    get_scoring_rules,
    list_question_banks,
)

_normal_user = User(id=2, username="candidate", email="c@example.com", role=CANDIDATE_ROLE)

CUSTOM_QUESTIONS = [
    {
        "type": "tech",
        "question": "请解释 Vue 3 响应式系统的实现原理。",
        "intent": "前端框架理解",
        "ref_answer": "Proxy + effect 依赖收集。",
    },
    {
        "type": "tech",
        "question": "讲一次你用 TypeScript 重构遗留代码的经历。",
        "intent": "前端工程化",
        "ref_answer": "类型边界、渐进迁移、回归验证。",
    },
    {
        "type": "project",
        "question": "描述一个你负责的前端性能优化案例。",
        "intent": "前端性能",
        "ref_answer": "指标、瓶颈定位、优化措施与收益。",
    },
]


@pytest.fixture
def cfg_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def cfg_session(cfg_engine):
    factory = sessionmaker(bind=cfg_engine)
    yield factory


def _seed_platform_bank(factory, *, bank_type: str = "tech", title: str = "前端技术面", questions=None):
    """平台级题库行（`tenant_id IS NULL`）——租户级那一档随 organization 出树后唯一的覆盖来源。"""
    session = factory()
    from app.models.interview_config import InterviewQuestionBank

    session.add(
        InterviewQuestionBank(
            tenant_id=None,
            type=bank_type,
            title=title,
            prompt_template="重点考察前端基础：Vue/React、TypeScript、工程化与性能优化。",
            questions=questions if questions is not None else CUSTOM_QUESTIONS,
            tags=["前端", "技术"],
        )
    )
    session.commit()
    session.close()


# ===== 单元：题库注入 =====


def test_fallback_questions_use_platform_custom_questions():
    questions = _fallback_questions("前端工程师", ["Vue"], "tech", custom_questions=CUSTOM_QUESTIONS)
    assert len(questions) == len(CUSTOM_QUESTIONS)
    assert questions[0]["question"] == CUSTOM_QUESTIONS[0]["question"]
    assert all(q["source"] == "platform_config" for q in questions)
    # 非法项被过滤
    dirty = CUSTOM_QUESTIONS + [{"type": "tech", "question": ""}]
    assert len(_fallback_questions("x", [], "tech", custom_questions=dirty)) == len(CUSTOM_QUESTIONS)


def test_fallback_questions_fallback_to_builtin_without_custom():
    questions = _fallback_questions("后端工程师", ["Python"], "tech")
    assert len(questions) == 10
    assert questions[0]["source"] == "starter"


def test_personalized_prompt_injects_platform_template(mocker):
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


# ===== 服务层：两级回落 =====


def test_question_bank_platform_row_overrides_builtin(cfg_session):
    _seed_platform_bank(cfg_session)

    db = cfg_session()
    try:
        assert get_question_bank(db, "tech").title == "前端技术面"  # 平台行
        assert get_question_bank(db, "hr") is None  # 未配置 → None（由调用方回落内置）
    finally:
        db.close()


def test_list_question_banks_platform_override_and_builtin_rest(cfg_session):
    _seed_platform_bank(cfg_session, bank_type="tech", title="前端技术面")

    db = cfg_session()
    try:
        banks = {b["type"]: b for b in list_question_banks(db)}
    finally:
        db.close()

    assert set(banks) == {"tech", "hr", "comprehensive", "stress", "group"}
    assert banks["tech"]["title"] == "前端技术面"  # 平台行覆盖内置
    assert banks["tech"]["tags"] == ["前端", "技术"]
    assert banks["hr"]["title"] == "HR / 行为面"  # 未覆盖的那几档仍是内置
    # `is_custom` 随租户级一起出树：它原来的定义就是"这一行带租户"
    assert "is_custom" not in banks["tech"]


def test_scoring_rules_builtin_default_then_platform_override(cfg_session):
    session = cfg_session()
    try:
        defaults = get_scoring_rules(session)
        assert [r["dimension"] for r in defaults] == ["completeness", "accuracy", "depth", "expression"]
        assert defaults[0]["weight"] == 0.30

        from app.models.interview_config import InterviewScoringRule

        session.add(
            InterviewScoringRule(tenant_id=None, dimension="completeness", label="要点覆盖", weight=0.10, sort_order=0)
        )
        session.add(
            InterviewScoringRule(tenant_id=None, dimension="expression", label="表达", weight=0.60, sort_order=1)
        )
        session.commit()

        custom = get_scoring_rules(session)
        assert len(custom) == 2
        assert {r["dimension"] for r in custom} == {"completeness", "expression"}
        assert custom[0]["weight"] == 0.10
        assert custom[0]["label"] == "要点覆盖"
    finally:
        session.close()


# ===== 端到端：创建面试使用平台题库 =====


def test_background_personalization_does_not_override_custom_bank(cfg_session, mocker):
    """平台自定义题库优先，后台个性化不得把自定义题换成通用题（#8）。"""
    from app.api.interview_rest import _fallback_questions, _personalize_unstarted_questions
    from app.models.interview_session import InterviewSession

    _seed_platform_bank(cfg_session)
    mocker.patch("app.api.interview_rest.SessionLocal", cfg_session)
    mocker.patch("app.api.interview_rest.chat_json", return_value={})  # 若被调用不应真实 LLM

    session = cfg_session()
    resume = Resume(
        user_id=_normal_user.id,
        file_name="r.pdf",
        file_path="uploads/r.pdf",
        parsed_json={"name": "张三", "skills": ["Vue"]},
    )
    jd = JobDescription(
        user_id=_normal_user.id,
        title="前端工程师",
        raw_text="招聘前端工程师",
        parsed_json={"title": "前端工程师", "required_skills": ["Vue"]},
    )
    session.add_all([resume, jd])
    session.commit()
    session.refresh(resume)
    session.refresh(jd)

    bank = get_question_bank(session, "tech")
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

    check = cfg_session()
    try:
        updated = check.get(InterviewSession, sid)
        assert updated.memory_snapshot["question_generation"]["status"] == "custom_bank"
        assert updated.questions[0]["source"] == "platform_config"
        assert len(updated.questions) == len(CUSTOM_QUESTIONS)
    finally:
        check.close()
