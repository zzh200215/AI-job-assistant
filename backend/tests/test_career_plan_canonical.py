"""P4 收口：完整规划（CareerAgent）的 skill_gaps 也要带 canonical。

`skill_gaps` 是模型自由文本（K8s / Kubernetes / k8s），画像里的技能弱点按
canonical 存。缺了这层，前端只能按拼写比，别名缺口就贴不上面试证据。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import career_agent as agent_mod
from app.api.analysis import router as analysis_router
from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.agent import AgentStepLog, AgentTask
from app.models.history import AnalysisRecord, Resume
from app.models.user import User
from app.orchestration.context import AgentContext


def _run_impl(monkeypatch, result):
    monkeypatch.setattr(agent_mod, "search_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(agent_mod, "chat_json", lambda prompt: result)
    return agent_mod.CareerAgent().run_impl(AgentContext(resume_id=1, jd_id=1, user_id=1))


def test_skill_gaps_get_canonical_identity(monkeypatch):
    result = _run_impl(
        monkeypatch,
        {"skill_gaps": [{"skill": "K8s"}, {"skill": "C++"}, {"skill": "关系型数据库"}]},
    )

    assert [gap["canonical"] for gap in result["skill_gaps"]] == [
        "kubernetes",
        "c-plus-plus",
        "关系型数据库",
    ]
    # 展示文本不动：页面仍显示模型写的那个名字。
    assert result["skill_gaps"][0]["skill"] == "K8s"


def test_missing_or_malformed_skill_gaps_pass_through(monkeypatch):
    result = _run_impl(monkeypatch, {"skill_gaps": "不适用"})
    assert result["skill_gaps"] == "不适用"

    rows = ["redis", {"skill": ""}, None]
    result = _run_impl(monkeypatch, {"skill_gaps": list(rows)})
    assert result["skill_gaps"] == rows


@pytest.fixture
def client(db_session):
    user = User(
        username="plan_canonical",
        email="plan_canonical@example.com",
        password="x",
        role="candidate",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    app = FastAPI()
    app.include_router(analysis_router, prefix="/analysis")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as test_client:
        yield test_client, user


def test_stored_plan_is_canonicalized_on_read_without_touching_the_row(db_session, client):
    """历史记录落库时没有 canonical；读接口必须补上，但库里那行一个字都不许改。"""
    test_client, user = client
    resume = Resume(
        user_id=user.id,
        file_name="canonical.pdf",
        file_path="uploads/canonical.pdf",
        file_type="pdf",
        file_size=1,
        parsed_json={"skills": ["Python"]},
        is_deleted=0,
    )
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)

    record = AnalysisRecord(
        user_id=user.id,
        resume_id=resume.id,
        jd_id=1,
        match_score=60,
        match_report={},
        optimize_suggestions={},
        interview_questions={},
        is_deleted=0,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    task = AgentTask(user_id=user.id, resume_id=resume.id, jd_id=1, analysis_record_id=record.id, status="completed")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    stored = {"skill_gaps": [{"skill": "K8s", "priority": "高"}, {"skill": "Redis", "priority": "中"}]}
    step = AgentStepLog(
        task_id=task.id, step_name="career_planning", step_index=1, status="completed", output_data=stored
    )
    db_session.add(step)
    db_session.commit()
    db_session.refresh(step)

    body = test_client.get(f"/analysis/{record.id}").json()

    assert body["code"] == 0
    gaps = body["data"]["career_planning"]["skill_gaps"]
    assert [gap.get("canonical") for gap in gaps] == ["kubernetes", "redis"]
    assert gaps[0]["skill"] == "K8s", "展示文本要原样保留"

    db_session.expire_all()
    assert "canonical" not in db_session.get(AgentStepLog, step.id).output_data["skill_gaps"][0]
