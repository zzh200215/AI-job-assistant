# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import app.api.resume as resume_api
from app.api.auth import router as auth_router
from app.api.jd import router as jd_router
from app.api.resume import router as resume_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import JobDescription, Resume
from app.models.user import User


@pytest.fixture
def jd_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(jd_router, prefix="/jd")
    app.include_router(resume_router, prefix="/resume")

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
        parsed_json={"skills": ["python"], "years_exp": 3},
    )
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)
    return resume


def _create_job(db_session, *, title: str, user_id=None, source: str = "manual") -> JobDescription:
    job = JobDescription(
        user_id=user_id,
        title=title,
        company="Test Co",
        location="Beijing",
        salary_range="20k-30k",
        raw_text=f"{title} role",
        parsed_json={"title": title, "required_skills": ["python"]},
        source=source,
        industry="AI",
        is_active=1,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_jd_detail_allows_public_job_for_other_user(jd_client, db_session):
    owner = _create_user(db_session, "jd_owner", "jd_owner@example.com")
    outsider = _create_user(db_session, "jd_outsider", "jd_outsider@example.com")

    _create_job(db_session, title="Private Job", user_id=owner.id)
    public_job = _create_job(db_session, title="Public Job", user_id=None, source="api")

    response = jd_client.get(f"/jd/{public_job.id}", headers=_auth_headers(outsider))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["title"] == "Public Job"


def test_jd_detail_still_blocks_other_users_private_job(jd_client, db_session):
    owner = _create_user(db_session, "jd_private_owner", "jd_private_owner@example.com")
    outsider = _create_user(db_session, "jd_private_outsider", "jd_private_outsider@example.com")

    private_job = _create_job(db_session, title="Private Job", user_id=owner.id)

    response = jd_client.get(f"/jd/{private_job.id}", headers=_auth_headers(outsider))

    assert response.status_code == 200
    assert response.json()["code"] != 0


def test_resume_generate_optimized_accepts_public_target_jd(jd_client, db_session, monkeypatch):
    user = _create_user(db_session, "resume_user", "resume_user@example.com")
    resume = _create_resume(db_session, user_id=user.id)
    public_job = _create_job(db_session, title="Public Optimize Job", user_id=None, source="api")

    captured = {}

    def _fake_generate(db, resume_id, jd_id, user_id=None):
        captured["resume_id"] = resume_id
        captured["jd_id"] = jd_id
        captured["user_id"] = user_id
        return {"version_id": 1, "markdown_content": "optimized"}

    monkeypatch.setattr(resume_api.resume_export_service, "generate_optimized", _fake_generate)

    response = jd_client.post(
        f"/resume/{resume.id}/generate-optimized",
        json={"target_jd_id": public_job.id},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert captured == {
        "resume_id": resume.id,
        "jd_id": public_job.id,
        "user_id": user.id,
    }
