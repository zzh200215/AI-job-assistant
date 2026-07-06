# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import app.api.agent as agent_api
import app.api.analysis as analysis_api
import app.api.interview_rest as interview_api
import app.api.multi_agent as multi_agent_api
from app.api.agent import router as agent_router
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.interview_rest import router as interview_router
from app.api.job_pipeline import router as job_pipeline_router
from app.api.multi_agent import router as multi_agent_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.agent_run import AgentRun
from app.models.history import JobDescription, Resume
from app.models.user import User


@pytest.fixture
def flow_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(analysis_router, prefix="/analysis")
    app.include_router(interview_router, prefix="/interview")
    app.include_router(job_pipeline_router, prefix="/jobs")
    app.include_router(agent_router, prefix="/agent")
    app.include_router(multi_agent_router, prefix="/multi-agent")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _create_user(db_session, username: str, email: str) -> User:
    user = User(
        username=username,
        email=email,
        password=hash_password("abc12345"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _create_resume(db_session, *, user_id: int) -> Resume:
    resume = Resume(
        user_id=user_id,
        file_name="resume.pdf",
        file_path="uploads/resume.pdf",
        file_type="pdf",
        file_size=123,
        is_deleted=0,
        parsed_json={"skills": ["python", "fastapi"], "years_exp": 3},
    )
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)
    return resume


def _create_public_job(db_session, *, title: str = "Public Job") -> JobDescription:
    jd = JobDescription(
        user_id=None,
        title=title,
        company="Public Co",
        location="Beijing",
        salary_range="20k-30k",
        raw_text="Public JD",
        parsed_json={
            "title": title,
            "required_skills": ["python", "fastapi"],
            "responsibilities": ["Build APIs"],
        },
        source="api",
        industry="AI",
        is_active=1,
    )
    db_session.add(jd)
    db_session.commit()
    db_session.refresh(jd)
    return jd


def test_analysis_full_accepts_public_job(flow_client, db_session, monkeypatch):
    user = _create_user(db_session, "analysis_user", "analysis@example.com")
    resume = _create_resume(db_session, user_id=user.id)
    public_job = _create_public_job(db_session)

    monkeypatch.setattr(analysis_api, "run_smart_analysis", lambda resume_id, jd_id, user_id: 99)

    response = flow_client.post(
        "/analysis/full",
        json={"resume_id": resume.id, "jd_id": public_job.id},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["task_id"] == 99


def test_interview_session_accepts_public_job(flow_client, db_session, monkeypatch):
    user = _create_user(db_session, "interview_user", "interview@example.com")
    resume = _create_resume(db_session, user_id=user.id)
    public_job = _create_public_job(db_session, title="Interview Job")

    monkeypatch.setattr(interview_api, "search_knowledge", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        interview_api,
        "chat_json",
        lambda prompt: {
            "basic": [{"q": "Tell me about yourself", "intent": "intro", "ref_answer": "summary"}],
            "tech": [],
            "project": [],
            "scenario": [],
        },
    )

    response = flow_client.post(
        "/interview/sessions",
        json={"resume_id": resume.id, "jd_id": public_job.id, "interview_type": "tech"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["jd_summary"]["id"] == public_job.id


def test_job_pipeline_accepts_public_job(flow_client, db_session):
    user = _create_user(db_session, "pipeline_user", "pipeline@example.com")
    resume = _create_resume(db_session, user_id=user.id)
    public_job = _create_public_job(db_session, title="Pipeline Job")

    response = flow_client.post(
        "/jobs/pipeline",
        json={
            "resume_id": resume.id,
            "jd_id": public_job.id,
            "title": "Pipeline Job",
            "stage": "todo",
        },
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["jd_id"] == public_job.id


def test_legacy_agent_start_accepts_public_job(flow_client, db_session, monkeypatch):
    user = _create_user(db_session, "agent_user", "agent@example.com")
    resume = _create_resume(db_session, user_id=user.id)
    public_job = _create_public_job(db_session, title="Agent Job")

    monkeypatch.setattr(agent_api, "run_workflow", lambda resume_id, jd_id, user_id: 88)

    response = flow_client.post(
        "/agent/start",
        json={"resume_id": resume.id, "jd_id": public_job.id},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["task_id"] == 88


def test_legacy_multi_agent_start_accepts_public_job(flow_client, db_session, monkeypatch):
    user = _create_user(db_session, "legacy_user", "legacy@example.com")
    resume = _create_resume(db_session, user_id=user.id)
    public_job = _create_public_job(db_session, title="Legacy Job")

    monkeypatch.setattr(multi_agent_api, "run_multi_agents", lambda resume_id, jd_id, user_id: 66)

    response = flow_client.post(
        "/multi-agent/start",
        json={"resume_id": resume.id, "jd_id": public_job.id},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["run_id"] == 66


def test_legacy_multi_agent_run_detail_is_scoped_to_resume_owner(flow_client, db_session):
    owner = _create_user(db_session, "run_owner", "run_owner@example.com")
    outsider = _create_user(db_session, "run_outsider", "run_outsider@example.com")
    resume = _create_resume(db_session, user_id=owner.id)
    public_job = _create_public_job(db_session, title="Run Job")

    run = AgentRun(
        resume_id=resume.id,
        jd_id=public_job.id,
        status="completed",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    denied = flow_client.get(f"/multi-agent/run/{run.id}", headers=_auth_headers(outsider))
    assert denied.status_code == 200
    assert denied.json()["code"] != 0

    allowed = flow_client.get(f"/multi-agent/run/{run.id}", headers=_auth_headers(owner))
    assert allowed.status_code == 200
    assert allowed.json()["code"] == 0
    assert allowed.json()["data"]["id"] == run.id
