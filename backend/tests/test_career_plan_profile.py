"""D283：完整规划（CareerAgent）也要吃上一场面试画像。

`CareerPathAgent`（职业方向）从 v2 起会引用面试证据，但 orchestration 的完整规划没有这份
画像，规划理由里永远不会提"上次面试"。这一格把 `compact_profile` 放进 prompt，并钉住三件事：
有画像要带上且包在不可信数据边界里；没画像/读失败/没有 db 时明说"无"而不挡规划。
"""

from __future__ import annotations

from datetime import datetime

from app.agents import career_agent as agent_mod
from app.orchestration.context import AgentContext


def _report(skill: str = "Kafka", score: int = 55) -> dict:
    return {
        "overall_score": 62,
        "dimension_scores": {"completeness": 80, "accuracy": 75, "depth": 58, "expression": 60},
        "question_evaluations": [
            {
                "question": f"{skill} 的消费语义怎么保证不丢消息？",
                "overall_score": score,
                "feedback": "只说了 at-least-once",
            }
        ],
        "answered_questions": 1,
        "interview_memory": {"jd_required_skills": [skill]},
    }


def _run(monkeypatch, context):
    prompts = []
    monkeypatch.setattr(agent_mod, "search_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(agent_mod, "chat_json", lambda prompt: prompts.append(prompt) or {})
    result = agent_mod.CareerAgent().run_impl(context)
    return prompts[0] if prompts else "", result


def test_prompt_carries_the_compact_profile_inside_the_untrusted_boundary(
    db_session, normal_user, make_interview_session, monkeypatch
):
    make_interview_session(
        user_id=normal_user.id,
        status="completed",
        evaluation=_report(),
        evaluation_status="completed",
        completed_at=datetime(2026, 10, 2),
    )

    prompt, _ = _run(monkeypatch, AgentContext(resume_id=1, jd_id=1, user_id=normal_user.id, db=db_session))

    assert '<interview_profile data-role="untrusted">' in prompt
    assert '"canonical": "kafka"' in prompt
    assert "55.0" in prompt or '"avg_score": 55' in prompt
    # 规则本身要进 prompt：有证据才点名，没有证据不许编。
    assert "上次面试该技能得分" in prompt
    assert "不许编造分数、题目或场次" in prompt


def test_prompt_says_none_when_the_user_has_no_interview_history(db_session, normal_user, monkeypatch):
    prompt, _ = _run(monkeypatch, AgentContext(resume_id=1, jd_id=1, user_id=normal_user.id, db=db_session))

    assert agent_mod.NO_PROFILE_HINT in prompt
    assert "Kafka" not in prompt


def test_profile_failure_does_not_block_the_plan(db_session, normal_user, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("profile down")

    monkeypatch.setattr(agent_mod, "get_profile", _boom)

    prompt, result = _run(monkeypatch, AgentContext(resume_id=1, jd_id=1, user_id=normal_user.id, db=db_session))

    assert agent_mod.NO_PROFILE_HINT in prompt
    assert result["_rag_references"] == []


def test_no_db_or_user_skips_the_profile_read(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("没有 db 时不该去读画像")

    monkeypatch.setattr(agent_mod, "get_profile", _boom)

    prompt, _ = _run(monkeypatch, AgentContext(resume_id=1, jd_id=1, user_id=1))

    assert agent_mod.NO_PROFILE_HINT in prompt
