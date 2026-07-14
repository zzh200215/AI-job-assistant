import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.analysis import router as analysis_router
from app.api.auth import router as auth_router
from app.api.history import router as history_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.user import User
from app.utils.response import ERR_PARAM


@pytest.fixture
def access_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(history_router, prefix="/history")
    app.include_router(analysis_router, prefix="/analysis")

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


def _create_resume(db_session, *, user_id: int, file_name: str = "resume.pdf") -> Resume:
    resume = Resume(
        user_id=user_id,
        file_name=file_name,
        file_path=f"uploads/{file_name}",
        file_type="pdf",
        file_size=123,
        is_deleted=0,
        parsed_json={"skills": ["python", "sql"]},
    )
    db_session.add(resume)
    db_session.commit()
    db_session.refresh(resume)
    return resume


def _create_job(db_session, *, user_id, title: str, source: str = "manual") -> JobDescription:
    job = JobDescription(
        user_id=user_id,
        title=title,
        company="Test Co",
        location="Beijing",
        salary_range="20k-30k",
        raw_text=f"{title} role",
        parsed_json={"required_skills": ["python", "fastapi"]},
        source=source,
        industry="AI",
        is_active=1,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def _create_record(
    db_session,
    *,
    user_id: int,
    resume_id: int,
    jd_id: int,
    match_score: int = 88,
) -> AnalysisRecord:
    record = AnalysisRecord(
        user_id=user_id,
        resume_id=resume_id,
        jd_id=jd_id,
        match_score=match_score,
        match_report={"summary": "ok"},
        optimize_suggestions={"items": []},
        interview_questions=[],
        remark="test",
        is_deleted=0,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_history_hides_inaccessible_related_resume_and_jd(access_client, db_session):
    owner = _create_user(db_session, "history_owner", "history_owner@example.com")
    other = _create_user(db_session, "history_other", "history_other@example.com")

    foreign_resume = _create_resume(db_session, user_id=other.id, file_name="foreign.pdf")
    foreign_job = _create_job(db_session, user_id=other.id, title="Foreign Private Job")
    record = _create_record(
        db_session,
        user_id=owner.id,
        resume_id=foreign_resume.id,
        jd_id=foreign_job.id,
    )

    listing = access_client.get("/history", headers=_auth_headers(owner))
    assert listing.status_code == 200
    item = listing.json()["data"]["items"][0]
    assert item["id"] == record.id
    assert item["resume_name"] is None
    assert item["resume_file"] is None
    assert item["jd_title"] is None
    assert item["jd_company"] is None

    detail = access_client.get(f"/history/{record.id}", headers=_auth_headers(owner))
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["resume"] is None
    assert body["jd"] is None


def test_analysis_record_hides_inaccessible_related_resume_and_jd(access_client, db_session):
    owner = _create_user(db_session, "analysis_owner", "analysis_owner@example.com")
    other = _create_user(db_session, "analysis_other", "analysis_other@example.com")

    foreign_resume = _create_resume(db_session, user_id=other.id, file_name="analysis-foreign.pdf")
    foreign_job = _create_job(db_session, user_id=other.id, title="Analysis Private Job")
    record = _create_record(
        db_session,
        user_id=owner.id,
        resume_id=foreign_resume.id,
        jd_id=foreign_job.id,
    )

    response = access_client.get(f"/analysis/{record.id}", headers=_auth_headers(owner))
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["id"] == record.id
    assert body["record_id"] == record.id
    assert body["resume_title"] == ""
    assert body["jd_title"] == ""
    assert body["resume_skills"] == []
    assert body["jd_skills"] == []
    assert body["matched_skills"] == []
    assert body["missing_skills"] == []


def test_analysis_references_returns_empty_when_related_objects_are_hidden(access_client, db_session, monkeypatch):
    owner = _create_user(db_session, "refs_owner", "refs_owner@example.com")
    other = _create_user(db_session, "refs_other", "refs_other@example.com")

    foreign_resume = _create_resume(db_session, user_id=other.id, file_name="refs-foreign.pdf")
    foreign_job = _create_job(db_session, user_id=other.id, title="Refs Private Job")
    record = _create_record(
        db_session,
        user_id=owner.id,
        resume_id=foreign_resume.id,
        jd_id=foreign_job.id,
    )

    called = {"value": False}

    def _fake_references(query, db):
        called["value"] = True
        return [{"title": "should not be returned"}]

    monkeypatch.setattr("app.api.analysis.get_knowledge_references", _fake_references)

    response = access_client.get(f"/analysis/{record.id}/references", headers=_auth_headers(owner))

    assert response.status_code == 200
    assert response.json()["data"] == {"references": []}
    assert called["value"] is False


def test_history_detail_rejects_foreign_record(access_client, db_session):
    owner = _create_user(db_session, "history_detail_owner", "history_detail_owner@example.com")
    other = _create_user(db_session, "history_detail_other", "history_detail_other@example.com")
    resume = _create_resume(db_session, user_id=other.id, file_name="detail-foreign.pdf")
    job = _create_job(db_session, user_id=other.id, title="Detail Foreign Job")
    record = _create_record(
        db_session,
        user_id=other.id,
        resume_id=resume.id,
        jd_id=job.id,
    )

    response = access_client.get(f"/history/{record.id}", headers=_auth_headers(owner))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == ERR_PARAM
    assert body["message"] == "记录不存在或无权限"


def test_history_delete_rejects_foreign_record(access_client, db_session):
    owner = _create_user(db_session, "history_delete_owner", "history_delete_owner@example.com")
    other = _create_user(db_session, "history_delete_other", "history_delete_other@example.com")
    resume = _create_resume(db_session, user_id=other.id, file_name="delete-foreign.pdf")
    job = _create_job(db_session, user_id=other.id, title="Delete Foreign Job")
    record = _create_record(
        db_session,
        user_id=other.id,
        resume_id=resume.id,
        jd_id=job.id,
    )

    response = access_client.delete(f"/history/{record.id}", headers=_auth_headers(owner))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == ERR_PARAM
    assert body["message"] == "记录不存在或无权限"
