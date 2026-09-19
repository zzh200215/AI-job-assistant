"""Hiding a job must be reversible, and the recovery list must say why it is hidden.

A5 made "不感兴趣" and thumbs-down actually exclude jobs from recommendations.
Without a way back, a single mis-click permanently shrank the candidate's result
set, so these tests pin the two halves of the loop: the reason-aware listing
endpoint and the one-call restore.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.job_recommend import router as job_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import JobDescription, Resume
from app.models.job_recommend import JobBookmark, JobRecommendationFeedback
from app.models.user import User
from app.services import job_recommend_engine as engine_mod
from app.services.job_recommend_engine import (
    JobRecommendationEngine,
    load_suppressed_reasons,
)


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(job_router, prefix="/jobs")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clear_recommend_cache():
    engine_mod._RECOMMEND_CACHE.clear()
    yield
    engine_mod._RECOMMEND_CACHE.clear()


def _user(db, name):
    row = User(
        username=name,
        email=f"{name}@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _headers(user):
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _resume(db, user):
    row = Resume(
        user_id=user.id,
        name="recovery resume",
        file_name="recovery.pdf",
        file_path="uploads/recovery.pdf",
        file_type="pdf",
        file_size=1024,
        parsed_json={
            "name": "王五",
            "skills": ["Python", "FastAPI"],
            "years_exp": 3,
            "education": "本科",
            "self_evaluation": "后端开发",
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _job(db, user, title):
    row = JobDescription(
        user_id=user.id,
        title=title,
        company="示例公司",
        location="上海",
        raw_text=f"{title} 需要 Python FastAPI",
        is_active=1,
        parsed_json={
            "title": title,
            "required_skills": ["Python", "FastAPI"],
            "experience_requirement": "3-5年",
            "education_requirement": "本科",
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _recommended_ids(db, resume):
    results = JobRecommendationEngine(db).recommend(resume_id=resume.id, limit=10, bypass_cache=False)
    return {item["jd_id"] for item in results}


# ---------------------------------------------------------------- reason map


def test_reason_map_labels_each_source(db_session):
    user = _user(db_session, "rc_reasons")
    a = _job(db_session, user, "岗位A")
    b = _job(db_session, user, "岗位B")
    c = _job(db_session, user, "岗位C")
    resume = _resume(db_session, user)

    db_session.add(JobBookmark(user_id=user.id, jd_id=a.id, action="dismiss", note=""))
    db_session.add(
        JobRecommendationFeedback(
            user_id=user.id, resume_id=resume.id, jd_id=b.id, feedback_type="dislike", match_score=60
        )
    )
    db_session.add(
        JobRecommendationFeedback(
            user_id=user.id, resume_id=resume.id, jd_id=c.id, feedback_type="like", match_score=90
        )
    )
    db_session.commit()

    reasons = load_suppressed_reasons(db_session, user.id)
    assert reasons == {a.id: ["dismiss"], b.id: ["dislike"]}


def test_both_sources_on_one_job_report_both_reasons(db_session):
    user = _user(db_session, "rc_both")
    job = _job(db_session, user, "双信号岗位")
    resume = _resume(db_session, user)

    db_session.add(JobBookmark(user_id=user.id, jd_id=job.id, action="dismiss", note=""))
    db_session.add(
        JobRecommendationFeedback(
            user_id=user.id, resume_id=resume.id, jd_id=job.id, feedback_type="dislike", match_score=40
        )
    )
    db_session.commit()

    assert load_suppressed_reasons(db_session, user.id) == {job.id: ["dismiss", "dislike"]}


# ---------------------------------------------------------------- list endpoint


def test_dismissed_endpoint_returns_jobs_with_reasons(client, db_session, job_client_headers):
    headers, _, hidden = job_client_headers
    hidden_id = hidden.id

    body = client.get("/jobs/bookmarks/dismissed", headers=headers).json()["data"]

    assert body["total"] == 1
    assert body["orphaned"] == 0
    item = body["items"][0]
    assert item["jd_id"] == hidden_id
    assert item["job_title"] == "被隐藏岗位"
    assert item["reasons"] == ["dismiss"]


def test_dismissed_endpoint_counts_orphaned_rows(client, db_session, job_client_headers):
    """A suppression row can outlive its job; the list must not claim it as restorable."""
    headers, _, hidden = job_client_headers
    db_session.query(JobBookmark).filter(JobBookmark.jd_id == hidden.id).update({"jd_id": 999999})
    db_session.commit()

    body = client.get("/jobs/bookmarks/dismissed", headers=headers).json()["data"]

    assert body["total"] == 1
    assert body["items"] == []
    assert body["orphaned"] == 1
    assert body["truncated"] == 0


@pytest.fixture
def job_client_headers(db_session):
    user = _user(db_session, "rc_list_user")
    resume = _resume(db_session, user)
    keep = _job(db_session, user, "正常岗位")
    hidden = _job(db_session, user, "被隐藏岗位")
    db_session.add(JobBookmark(user_id=user.id, jd_id=hidden.id, action="dismiss", note=""))
    db_session.commit()
    return _headers(user), resume, hidden


# ---------------------------------------------------------------- restore


def test_restore_clears_dismiss_and_returns_the_job(client, db_session, job_client_headers):
    headers, resume, hidden = job_client_headers

    assert hidden.id not in _recommended_ids(db_session, resume)

    resp = client.post("/jobs/bookmarks/restore", json={"jd_id": hidden.id}, headers=headers).json()
    assert resp["code"] == 0
    assert resp["data"]["dismiss"] == 1

    assert hidden.id in _recommended_ids(db_session, resume)


def test_restore_clears_dislike_too(client, db_session, job_client_headers):
    """Restoring only the bookmark would report success while the thumbs-down kept
    the job hidden — the exact false-success this endpoint exists to prevent."""
    headers, resume, hidden = job_client_headers
    db_session.add(
        JobRecommendationFeedback(
            user_id=resume.user_id,
            resume_id=resume.id,
            jd_id=hidden.id,
            feedback_type="dislike",
            match_score=55,
        )
    )
    db_session.commit()

    resp = client.post("/jobs/bookmarks/restore", json={"jd_id": hidden.id}, headers=headers).json()
    assert resp["data"] == {"jd_id": hidden.id, "dismiss": 1, "dislike": 1}

    assert hidden.id in _recommended_ids(db_session, resume)
    assert load_suppressed_reasons(db_session, resume.user_id) == {}


def test_restore_is_idempotent(client, db_session, job_client_headers):
    headers, _, hidden = job_client_headers

    first = client.post("/jobs/bookmarks/restore", json={"jd_id": hidden.id}, headers=headers).json()
    second = client.post("/jobs/bookmarks/restore", json={"jd_id": hidden.id}, headers=headers).json()

    assert first["code"] == 0
    assert second["code"] == 0
    assert second["data"]["dismiss"] == 0


def test_restore_does_not_touch_other_users(client, db_session, job_client_headers):
    headers, resume, hidden = job_client_headers
    other = _user(db_session, "rc_other")
    other_resume = _resume(db_session, other)
    db_session.add(JobBookmark(user_id=other.id, jd_id=hidden.id, action="dismiss", note=""))
    db_session.commit()

    client.post("/jobs/bookmarks/restore", json={"jd_id": hidden.id}, headers=headers)

    assert hidden.id not in _recommended_ids(db_session, other_resume)


def test_restore_requires_a_job_id(client, db_session, job_client_headers):
    headers, _, _ = job_client_headers
    assert client.post("/jobs/bookmarks/restore", json={}, headers=headers).json()["code"] != 0


def test_restore_rejects_anonymous(client, db_session):
    assert client.post("/jobs/bookmarks/restore", json={"jd_id": 1}).status_code in (401, 403)


# ---------------------------------------------------------------- through /recommend


def test_recommended_jobs_disappear_and_return_via_api(client, db_session, job_client_headers):
    headers, resume, hidden = job_client_headers

    def recommended():
        data = client.get("/jobs/recommend", params={"resume_id": resume.id, "limit": 10}, headers=headers).json()
        return {item["jd_id"] for item in data["data"]["recommendations"]}

    assert hidden.id not in recommended()

    client.post("/jobs/bookmarks/restore", json={"jd_id": hidden.id}, headers=headers)

    assert hidden.id in recommended()
