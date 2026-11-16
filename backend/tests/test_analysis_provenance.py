"""结果页的"底账"：这条分析的模型调用是几发、谁答的、几发没成功（D14）。

起因是 2026-11-14 那次真 provider 实测：7 发调用里 4 发 429，分数只来自规则臂，
而结果页上只写着"分析完成，匹配度 57"。数据一直躺在库里（`AgentTask.analysis_record_id`
指回记录、`PromptTrace.task_id` 指回任务），只是没人把它们接起来。

两条判据要点：
1. 有任务、有 trace → 如实报数（含 `failed` / `degraded`）；
2. **没有任务或没有 trace → `provenance` 是 `None`**，不造一个全零的底账——
   否则"查不到"与"跑了但全失败"在屏幕上长得一样。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.agent import AgentTask
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.prompt_trace import PromptTrace
from app.models.user import User


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(analysis_router, prefix="/analysis")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _user(db, name: str) -> User:
    user = User(username=name, email=f"{name}@example.com", password=hash_password("abc12345"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _record(db, user: User) -> AnalysisRecord:
    resume = Resume(
        user_id=user.id,
        file_name="resume.pdf",
        file_path="uploads/resume.pdf",
        file_type="pdf",
        file_size=1,
        is_deleted=0,
        parsed_json={"skills": ["python"]},
    )
    job = JobDescription(
        user_id=user.id,
        title="后端工程师",
        company="Test Co",
        raw_text="jd",
        parsed_json={"required_skills": ["python"]},
        source="manual",
        is_active=1,
    )
    db.add_all([resume, job])
    db.commit()
    db.refresh(resume)
    db.refresh(job)
    record = AnalysisRecord(
        user_id=user.id,
        resume_id=resume.id,
        jd_id=job.id,
        match_score=57,
        match_report={"summary": "ok"},
        optimize_suggestions={"items": []},
        interview_questions=[],
        is_deleted=0,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _task(db, user: User, record: AnalysisRecord, status: str = "completed") -> AgentTask:
    task = AgentTask(
        user_id=user.id,
        resume_id=record.resume_id,
        jd_id=record.jd_id,
        strategy_name="linear",
        status=status,
        analysis_record_id=record.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _trace(db, task: AgentTask, source: str, status: str, degraded: int) -> None:
    db.add(
        PromptTrace(
            request_id=f"prov-{uuid4().hex[:12]}",
            task_id=task.id,
            source="agent.MatchAnalysisAgent",
            prompt_version="match-v1",
            provider="openai",
            model="test-model",
            response_source=source,
            status=status,
            degraded=degraded,
        )
    )
    db.commit()


def test_a_degraded_run_says_so(client, db_session):
    user = _user(db_session, "prov_degraded")
    record = _record(db_session, user)
    task = _task(db_session, user, record)
    _trace(db_session, task, "real", "success", 0)
    _trace(db_session, task, "fallback_model", "success", 1)
    _trace(db_session, task, "unknown", "failed", 1)
    _trace(db_session, task, "unknown", "failed", 1)

    body = client.get(f"/analysis/{record.id}", headers=_headers(user)).json()["data"]
    provenance = body["provenance"]

    assert provenance["task_id"] == task.id
    assert provenance["calls"] == 4
    assert provenance["failed"] == 2
    assert provenance["degraded"] == 3
    assert provenance["by_source"]["unknown"] == 2
    assert provenance["task_status"] == "completed"


def test_a_clean_run_reports_zero_failures(client, db_session):
    user = _user(db_session, "prov_clean")
    record = _record(db_session, user)
    task = _task(db_session, user, record)
    _trace(db_session, task, "real", "success", 0)
    _trace(db_session, task, "real", "success", 0)

    provenance = client.get(f"/analysis/{record.id}", headers=_headers(user)).json()["data"]["provenance"]

    assert provenance["calls"] == 2
    assert provenance["failed"] == 0
    assert provenance["degraded"] == 0


def test_a_record_without_a_task_has_no_provenance(client, db_session):
    """反证：不许把"查不到"写成一份全零的底账。"""
    user = _user(db_session, "prov_legacy")
    record = _record(db_session, user)

    body = client.get(f"/analysis/{record.id}", headers=_headers(user)).json()["data"]

    assert body["provenance"] is None
    assert body["match_score"] == 57  # 其余字段不受影响


def test_another_users_task_is_not_counted(client, db_session):
    """底账要带 `user_id` 过滤：别人任务上的调用不该出现在我的结果页上。"""
    owner = _user(db_session, "prov_owner")
    other = _user(db_session, "prov_other")
    record = _record(db_session, owner)
    foreign_task = _task(db_session, other, record)
    _trace(db_session, foreign_task, "real", "success", 0)

    body = client.get(f"/analysis/{record.id}", headers=_headers(owner)).json()["data"]

    assert body["provenance"] is None
