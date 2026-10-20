"""P4 收尾：智能分析页的 InterviewQuestionAgent 与模拟面试共用同一套题源。

三件事必须一起成立，否则"统一"只是把两份代码搬到了一个文件旁边：
1. 查询词、文档类型、top_k 是同一个实现；
2. 两道入口拿到的题源上下文格式相同；
3. 模型返回的题经过同一个 `normalize_question`，所以会话题源 schema 只有一份。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents import interview_question_agent as agent_mod
from app.api import interview_rest as rest_mod
from app.api.interview_rest import _build_personalized_prompt, _normalize_generated_questions
from app.models.history import JobDescription, Resume
from app.orchestration.context import AgentContext
from app.services.interview_question_source import (
    DEFAULT_SEARCH_TYPES,
    build_rag_query,
    fetch_interview_question_context,
    format_rag_context,
    normalize_question,
    search_types_for,
)


def test_search_types_match_the_old_mapping():
    assert search_types_for("tech") == ["interview_q", "skill_model"]
    assert search_types_for("comprehensive") == ["interview_q", "skill_model"]
    assert search_types_for("hr") == ["interview_q"]
    assert search_types_for("unknown") == list(DEFAULT_SEARCH_TYPES)


def test_query_uses_the_title_and_first_five_skills():
    assert build_rag_query("后端工程师", ["A", "B", "C", "D", "E", "F"]) == "后端工程师 A B C D E"
    assert build_rag_query("", []) == ""


def test_fetch_uses_one_query_and_top_k_for_every_doc_type(monkeypatch):
    calls = []

    def fake_search(query, *, doc_type, top_k, db, user_id):
        calls.append((query, doc_type, top_k, db, user_id))
        return [{"doc_title": doc_type, "text": f"{doc_type}-body"}]

    monkeypatch.setattr("app.services.interview_question_source.search_knowledge", fake_search)
    groups = fetch_interview_question_context(
        None,
        title="后端工程师",
        skills=["Kafka", "Redis"],
        search_types=["interview_q", "skill_model"],
        user_id=7,
    )

    assert calls == [
        ("后端工程师 Kafka Redis", "interview_q", 3, None, 7),
        ("后端工程师 Kafka Redis", "skill_model", 3, None, 7),
    ]
    assert [group["doc_type"] for group in groups] == ["interview_q", "skill_model"]
    context = format_rag_context(groups)
    assert "===== interview_q =====" in context
    assert "【interview_q】interview_q-body" in context


def test_normalize_question_is_the_one_schema():
    normalized = normalize_question(
        {"q": "讲讲项目", "intent": "考察深度", "expected_answer": "按背景/方案/结果"},
        q_type="tech",
        index=2,
        source="analysis_agent",
    )

    assert normalized == {
        "id": 2,
        "type": "tech",
        "category": "技术基础",
        "question": "讲讲项目",
        "intent": "考察深度",
        "ref_answer": "按背景/方案/结果",
        "source": "analysis_agent",
    }
    assert normalize_question({"question": "  "}, q_type="tech") is None
    assert normalize_question("不是对象", q_type="tech") is None


def test_the_agent_uses_the_shared_context_and_emits_the_shared_schema(db_session: Session, monkeypatch):
    resume = Resume(
        user_id=1,
        tenant_id=1,
        file_name="q-source.pdf",
        file_path="uploads/q-source.pdf",
        file_type="pdf",
        file_size=1,
        parsed_json={"skills": ["Python"]},
    )
    jd = JobDescription(
        user_id=1,
        tenant_id=1,
        title="后端工程师",
        raw_text="后端工程师",
        parsed_json={"title": "后端工程师", "required_skills": ["Kafka", "Redis"]},
    )
    db_session.add_all([resume, jd])
    db_session.commit()
    db_session.refresh(resume)
    db_session.refresh(jd)

    calls = []
    monkeypatch.setattr(
        agent_mod,
        "fetch_interview_question_context",
        lambda db, **kwargs: calls.append(kwargs) or [{"doc_type": "interview_q", "results": []}],
    )
    monkeypatch.setattr(
        agent_mod,
        "chat_json",
        lambda prompt: {"basic": [{"q": "自我介绍", "intent": "开场"}], "tech": [{"question": "讲讲 RAG"}]},
    )

    result = agent_mod.InterviewQuestionAgent().run_impl(
        AgentContext(resume_id=resume.id, jd_id=jd.id, user_id=1, db=db_session)
    )

    assert calls[0]["title"] == "后端工程师"
    assert calls[0]["skills"] == ["Kafka", "Redis"]
    assert [item["type"] for item in result["questions"]] == ["basic", "tech"]
    assert result["questions"][0]["category"] == "通用/HR"
    assert result["questions"][1]["question"] == "讲讲 RAG"


def test_the_rest_prompt_consumes_the_same_context(monkeypatch):
    calls = []

    def fake_context(db, **kwargs):
        calls.append(kwargs)
        return [{"doc_type": "interview_q", "results": [{"doc_title": "题库", "text": "题目正文"}]}]

    monkeypatch.setattr(rest_mod, "fetch_interview_question_context", fake_context)

    prompt = _build_personalized_prompt(
        resume_json={},
        jd_json={},
        jd_title="后端工程师",
        required_skills=["Kafka"],
        interview_type="tech",
        search_types=["interview_q"],
        db=None,
        user_id=7,
    )

    assert calls == [
        {
            "title": "后端工程师",
            "skills": ["Kafka"],
            "search_types": ["interview_q"],
            "user_id": 7,
        }
    ]
    assert "===== interview_q =====" in prompt
    assert "【题库】题目正文" in prompt


def test_the_rest_normalizer_uses_the_shared_schema():
    merged = _normalize_generated_questions(
        {
            "basic": [{"q": "自我介绍", "intent": "开场"}],
            "questions": [{"type": "tech", "q": "讲讲 RAG"}],
        },
        [{"type": "scenario", "category": "场景应对", "question": "兜底题", "source": "starter"}],
    )

    assert [item["type"] for item in merged] == ["basic", "tech", "scenario"]
    assert [item["id"] for item in merged] == [1, 2, 3]
    assert merged[0]["category"] == "通用/HR"
    assert merged[1]["category"] == "技术基础"
