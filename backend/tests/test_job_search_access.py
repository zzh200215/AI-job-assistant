# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import job_search as job_search_api
from app.api.auth import router as auth_router
from app.api.job_search import router as job_search_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import JobDescription
from app.models.user import User
from app.services.job_spider import JobItem


@pytest.fixture
def job_search_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(job_search_router, prefix="/jobs")

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


def _create_job(
    db_session,
    *,
    user_id,
    title: str,
    company: str = "Test Co",
    location: str = "Beijing",
    source: str = "crawled",
    external_url: str | None = None,
    raw_text: str | None = None,
) -> JobDescription:
    job = JobDescription(
        user_id=user_id,
        title=title,
        company=company,
        location=location,
        salary_range="20k-30k",
        raw_text=raw_text or f"{title} description",
        parsed_json={"required_skills": ["python"]},
        source=source,
        industry="AI",
        is_active=1,
        external_url=external_url,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_search_external_does_not_reuse_other_users_private_job(job_search_client, db_session, monkeypatch):
    owner = _create_user(db_session, "search_owner", "search_owner@example.com")
    other = _create_user(db_session, "search_other", "search_other@example.com")

    other_job = _create_job(
        db_session,
        user_id=other.id,
        title="Python Backend",
        company="Acme",
        location="Shanghai",
    )

    monkeypatch.setattr(
        job_search_api.spider,
        "search",
        lambda keyword, city, source, page: (
            [
                JobItem(
                    title="Python Backend",
                    company="Acme",
                    location="Shanghai",
                    salary_range="30k-40k",
                    raw_text="fresh description",
                    source="boss",
                )
            ],
            None,
        ),
    )

    response = job_search_client.post(
        "/jobs/search-external",
        params={"keyword": "python", "save": True},
        headers=_auth_headers(owner),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["saved_count"] == 1
    new_job_id = body["data"]["jobs"][0]["id"]
    assert new_job_id != other_job.id

    new_job = db_session.get(JobDescription, new_job_id)
    assert new_job is not None
    assert new_job.user_id == owner.id


def test_fetch_detail_does_not_overwrite_other_users_private_job(job_search_client, db_session, monkeypatch):
    owner = _create_user(db_session, "detail_owner", "detail_owner@example.com")
    other = _create_user(db_session, "detail_other", "detail_other@example.com")
    shared_url = "https://example.com/job/1"

    other_job = _create_job(
        db_session,
        user_id=other.id,
        title="Existing Job",
        external_url=shared_url,
        raw_text="original private text",
    )

    monkeypatch.setattr(
        job_search_api.spider,
        "fetch_detail",
        lambda source, url: JobItem(
            title="Fetched Job",
            company="Acme",
            location="Beijing",
            salary_range="35k-45k",
            raw_text="new fetched text",
            skill_tags=["python"],
            source=source,
            source_url=url,
        ),
    )

    response = job_search_client.post(
        "/jobs/fetch-detail",
        params={"source": "boss", "url": shared_url},
        headers=_auth_headers(owner),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["id"] != other_job.id

    db_session.refresh(other_job)
    assert other_job.raw_text == "original private text"

    created = db_session.get(JobDescription, body["data"]["id"])
    assert created is not None
    assert created.user_id == owner.id
    assert created.raw_text == "new fetched text"


def test_search_external_fallback_only_returns_visible_jobs(job_search_client, db_session, monkeypatch):
    owner = _create_user(db_session, "fallback_owner", "fallback_owner@example.com")
    other = _create_user(db_session, "fallback_other", "fallback_other@example.com")

    own_job = _create_job(db_session, user_id=owner.id, title="Python Owner Job")
    _create_job(db_session, user_id=other.id, title="Python Private Job")
    public_job = _create_job(db_session, user_id=None, title="Python Public Job", source="imported")

    monkeypatch.setattr(job_search_api.spider, "search", lambda keyword, city, source, page: ([], "network limited"))

    response = job_search_client.post(
        "/jobs/search-external",
        params={"keyword": "Python", "save": False},
        headers=_auth_headers(owner),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0

    jobs = body["data"]["jobs"]
    assert {item["title"] for item in jobs} == {"Python Owner Job", "Python Public Job"}
    assert {item["id"] for item in jobs} == {own_job.id, public_job.id}
