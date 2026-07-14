"""API-level candidate journey test for the P0 critical path.

This exercises the same HTTP contracts used by the UI while replacing file storage,
LLM parsing, and background execution with deterministic local collaborators.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import analysis as analysis_api
from app.api import jd as jd_api
from app.api import resume as resume_api
from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.jd import router as jd_router
from app.api.resume import router as resume_router
from app.core.database import get_db
from app.models.history import JobDescription, Resume


@pytest.fixture
def candidate_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(resume_router, prefix="/resume")
    app.include_router(jd_router, prefix="/jd")
    app.include_router(analysis_router, prefix="/analysis")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def test_candidate_can_register_prepare_inputs_and_start_analysis(candidate_client, db_session, monkeypatch):
    monkeypatch.setattr(
        resume_api.resume_service,
        "save_upload_file",
        lambda data, file_name: {
            "file_name": file_name,
            "file_path": "uploads/test-resume.pdf",
            "file_type": "pdf",
            "file_size": len(data),
        },
    )

    def parse_resume(db, resume_id):
        resume = db.get(Resume, resume_id)
        resume.raw_text = "Python developer with FastAPI experience"
        resume.parsed_json = {"name": "Journey User", "skills": ["Python", "FastAPI"]}
        db.commit()
        return resume

    def parse_jd(db, jd_id):
        jd = db.get(JobDescription, jd_id)
        jd.parsed_json = {"required_skills": ["Python", "FastAPI"]}
        db.commit()
        return jd

    started = {}

    def start_analysis(*, resume_id, jd_id, user_id):
        started.update(resume_id=resume_id, jd_id=jd_id, user_id=user_id)
        return 9001

    monkeypatch.setattr(resume_api.resume_service, "parse_and_save", parse_resume)
    monkeypatch.setattr(jd_api.jd_service, "parse_and_save", parse_jd)
    monkeypatch.setattr(analysis_api, "run_smart_analysis", start_analysis)

    registration = candidate_client.post(
        "/auth/register",
        json={"username": "journey_user", "email": "journey@example.com", "password": "JourneyPass123!"},
    )
    assert registration.status_code == 200
    auth = {"Authorization": f"Bearer {registration.json()['data']['access_token']}"}
    user_id = registration.json()["data"]["user"]["id"]

    upload = candidate_client.post(
        "/resume/upload",
        headers=auth,
        files={"file": ("resume.pdf", b"%PDF-1.4 journey resume", "application/pdf")},
    )
    assert upload.status_code == 200
    resume_id = upload.json()["data"]["id"]

    parsed_resume = candidate_client.post("/resume/parse", headers=auth, json={"resume_id": resume_id})
    assert parsed_resume.status_code == 200
    assert parsed_resume.json()["data"]["parsed"]["skills"] == ["Python", "FastAPI"]

    created_jd = candidate_client.post(
        "/jd",
        headers=auth,
        json={"title": "Python Engineer", "company": "Acme", "raw_text": "Need Python and FastAPI skills."},
    )
    assert created_jd.status_code == 200
    jd_id = created_jd.json()["data"]["id"]

    parsed_jd = candidate_client.post("/jd/parse", headers=auth, json={"jd_id": jd_id})
    assert parsed_jd.status_code == 200
    assert parsed_jd.json()["data"]["parsed"]["required_skills"] == ["Python", "FastAPI"]

    analysis = candidate_client.post("/analysis/full", headers=auth, json={"resume_id": resume_id, "jd_id": jd_id})
    assert analysis.status_code == 200
    assert analysis.json()["data"]["task_id"] == 9001
    assert started == {"resume_id": resume_id, "jd_id": jd_id, "user_id": user_id}
