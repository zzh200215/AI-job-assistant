# -*- coding: utf-8 -*-
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.auth import router as auth_router
from app.api.job_recommend import router as job_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import JobDescription, Resume
from app.models.job_recommend import JobRecommendationFeedback
from app.models.user import User
from app.services import recommendation_tuning as tuning_service


@pytest.fixture
def job_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(job_router, prefix="/jobs")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def isolate_recommendation_tuning_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tuning_service,
        "_CONFIG_PATH",
        tmp_path / "recommendation_tuning_configs.json",
    )
    yield


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


def _create_job(db_session, *, title: str, user_id=None, source: str = "manual") -> JobDescription:
    job = JobDescription(
        user_id=user_id,
        title=title,
        company="Test Co",
        location="Beijing",
        salary_range="20k-30k",
        raw_text=f"{title} role",
        parsed_json={"required_skills": ["python"]},
        source=source,
        industry="AI",
        is_active=1,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


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


def test_job_list_only_returns_owned_and_public_jobs(job_client, db_session):
    owner = _create_user(db_session, "jobs_owner", "jobs_owner@example.com")
    other = _create_user(db_session, "jobs_other", "jobs_other@example.com")

    _create_job(db_session, title="owner-job", user_id=owner.id)
    _create_job(db_session, title="public-job", user_id=None, source="api")
    _create_job(db_session, title="other-job", user_id=other.id)

    response = job_client.get("/jobs/list", headers=_auth_headers(owner))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert {item["title"] for item in body["data"]["items"]} == {"owner-job", "public-job"}


def test_job_detail_blocks_other_users_private_job(job_client, db_session):
    owner = _create_user(db_session, "detail_owner", "detail_owner@example.com")
    outsider = _create_user(db_session, "detail_outsider", "detail_outsider@example.com")

    private_job = _create_job(db_session, title="private-job", user_id=owner.id)
    public_job = _create_job(db_session, title="public-job", user_id=None, source="api")

    denied = job_client.get(f"/jobs/{private_job.id}", headers=_auth_headers(outsider))
    assert denied.status_code == 200
    assert denied.json()["code"] != 0

    allowed = job_client.get(f"/jobs/{public_job.id}", headers=_auth_headers(outsider))
    assert allowed.status_code == 200
    assert allowed.json()["code"] == 0
    assert allowed.json()["data"]["title"] == "public-job"


def test_job_feedback_blocks_other_users_private_job(job_client, db_session):
    owner = _create_user(db_session, "feedback_owner", "feedback_owner@example.com")
    outsider = _create_user(db_session, "feedback_outsider", "feedback_outsider@example.com")

    private_job = _create_job(db_session, title="private-job", user_id=owner.id)
    outsider_resume = _create_resume(db_session, user_id=outsider.id)

    response = job_client.post(
        "/jobs/feedback",
        params={
            "resume_id": outsider_resume.id,
            "jd_id": private_job.id,
            "feedback_type": "like",
        },
        headers=_auth_headers(outsider),
    )

    assert response.status_code == 200
    assert response.json()["code"] != 0


def test_job_feedback_stats_only_counts_current_user(job_client, db_session):
    user = _create_user(db_session, "stats_owner", "stats_owner@example.com")
    other = _create_user(db_session, "stats_other", "stats_other@example.com")
    resume = _create_resume(db_session, user_id=user.id)
    resume_two = _create_resume(db_session, user_id=user.id)
    job = _create_job(db_session, title="stats-job", user_id=None, source="api")
    industry_job = _create_job(db_session, title="ops-job", user_id=None, source="api")
    industry_job.industry = "Cloud"
    other_resume = _create_resume(db_session, user_id=other.id)
    db_session.add(industry_job)
    db_session.commit()

    db_session.add_all(
        [
            JobRecommendationFeedback(
                user_id=user.id,
                resume_id=resume.id,
                jd_id=job.id,
                feedback_type="like",
                match_score=88,
                created_at=datetime(2026, 6, 24, 9, 0, 0),
            ),
            JobRecommendationFeedback(
                user_id=user.id,
                resume_id=resume_two.id,
                jd_id=industry_job.id,
                feedback_type="dislike",
                match_score=72,
                created_at=datetime(2026, 6, 25, 11, 0, 0),
            ),
            JobRecommendationFeedback(
                user_id=user.id,
                resume_id=resume.id,
                jd_id=job.id,
                feedback_type="dislike",
                match_score=91,
                created_at=datetime(2026, 6, 25, 15, 0, 0),
            ),
            JobRecommendationFeedback(
                user_id=other.id,
                resume_id=other_resume.id,
                jd_id=job.id,
                feedback_type="like",
                match_score=99,
                created_at=datetime(2026, 6, 25, 12, 0, 0),
            ),
        ]
    )
    db_session.commit()

    response = job_client.get("/jobs/feedback/stats", headers=_auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 3
    assert body["data"]["like_count"] == 1
    assert body["data"]["dislike_count"] == 2
    assert body["data"]["avg_match_score"] == 83.67
    assert body["data"]["like_rate"] == pytest.approx(1 / 3, rel=0, abs=1e-4)
    assert len(body["data"]["trend"]) == 7
    assert body["data"]["trend"][-2]["date"] == "2026-06-24"
    assert body["data"]["trend"][-2]["like"] == 1
    assert body["data"]["trend"][-1]["date"] == "2026-06-25"
    assert body["data"]["trend"][-1]["dislike"] == 2
    assert body["data"]["by_resume"][0]["resume_id"] == resume.id
    assert {item["industry"] for item in body["data"]["by_industry"]} == {"AI", "Cloud"}
    assert len(body["data"]["tuning_signals"]["high_score_dislikes"]) == 1
    assert body["data"]["tuning_signals"]["high_score_dislikes"][0]["match_score"] == 91
    assert any(
        item["type"] == "score_calibration"
        for item in body["data"]["tuning_signals"]["action_items"]
    )


def test_job_feedback_evaluation_exposes_calibration_and_coverage(job_client, db_session):
    user = _create_user(db_session, "eval_owner", "eval_owner@example.com")
    resume_a = _create_resume(db_session, user_id=user.id)
    resume_b = _create_resume(db_session, user_id=user.id)
    job_a = _create_job(db_session, title="ml-job", user_id=None, source="api")
    job_b = _create_job(db_session, title="ops-job", user_id=None, source="api")
    job_a_id = job_a.id
    job_b.industry = "Cloud"
    db_session.add(job_b)
    db_session.commit()

    db_session.add_all(
        [
            JobRecommendationFeedback(
                user_id=user.id,
                resume_id=resume_a.id,
                jd_id=job_a.id,
                feedback_type="like",
                match_score=85,
                created_at=datetime(2026, 6, 20, 10, 0, 0),
            ),
            JobRecommendationFeedback(
                user_id=user.id,
                resume_id=resume_a.id,
                jd_id=job_a.id,
                feedback_type="dislike",
                match_score=90,
                created_at=datetime(2026, 6, 21, 10, 0, 0),
            ),
            JobRecommendationFeedback(
                user_id=user.id,
                resume_id=resume_b.id,
                jd_id=job_b.id,
                feedback_type="like",
                match_score=55,
                created_at=datetime(2026, 6, 22, 10, 0, 0),
            ),
        ]
    )
    db_session.commit()

    response = job_client.get("/jobs/feedback/evaluation", headers=_auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["evaluation"]["coverage"]["unique_resume_count"] == 2
    assert body["data"]["evaluation"]["coverage"]["unique_job_count"] == 2
    assert body["data"]["evaluation"]["coverage"]["active_days"] == 3
    assert {item["bucket"] for item in body["data"]["evaluation"]["calibration"]["buckets"]} == {"0-59", "80-100"}
    assert body["data"]["evaluation"]["calibration"]["high_score_dislike_count"] == 1
    assert body["data"]["evaluation"]["calibration"]["low_score_like_count"] == 1
    assert body["data"]["evaluation"]["mismatch_focus"]["jobs"][0]["jd_id"] == job_a_id
    assert body["data"]["evaluation"]["sample_health"]["enough_for_tuning"] is False
    assert body["data"]["tuning_recommendation"]["sample_total"] == 3
    assert "current_config" in body["data"]["tuning_recommendation"]
    assert "suggested_config" in body["data"]["tuning_recommendation"]


def test_job_feedback_tuning_samples_and_csv_export(job_client, db_session):
    user = _create_user(db_session, "tuning_owner", "tuning_owner@example.com")
    headers = _auth_headers(user)
    resume = _create_resume(db_session, user_id=user.id)
    resume.parsed_json = {
        "skills": ["python"],
        "years_exp": 2,
        "expected_salary": "25k-35k",
        "location": "Beijing",
    }
    job = _create_job(db_session, title="backend-job", user_id=None, source="api")
    job.parsed_json = {
        "required_skills": ["python", "redis", "mysql", "docker"],
        "experience_requirement": "5-8年",
    }
    job.salary_range = "12k-18k"
    job.location = "Shanghai"
    db_session.add_all([resume, job])
    db_session.commit()

    db_session.add(
        JobRecommendationFeedback(
            user_id=user.id,
            resume_id=resume.id,
            jd_id=job.id,
            feedback_type="dislike",
            match_score=88,
            created_at=datetime(2026, 6, 23, 10, 0, 0),
        )
    )
    db_session.commit()

    samples = job_client.get("/jobs/feedback/tuning-samples", headers=headers)
    assert samples.status_code == 200
    samples_body = samples.json()
    assert samples_body["code"] == 0
    assert samples_body["data"]["total"] == 1
    item = samples_body["data"]["items"][0]
    assert item["feedback_type"] == "dislike"
    assert "high_score_dislike" in item["tuning_tags"]
    assert "salary_gap" in item["tuning_tags"]
    assert "location_gap" in item["tuning_tags"]
    assert "experience_gap" in item["tuning_tags"]
    assert "skill_gap_heavy" in item["tuning_tags"]

    exported = job_client.get(
        "/jobs/feedback/tuning-export",
        params={"format": "csv"},
        headers=headers,
    )
    assert exported.status_code == 200
    content = exported.content.decode("utf-8-sig")
    assert "feedback_id,feedback_type,match_score" in content
    assert "high_score_dislike" in content


def test_job_feedback_apply_tuning_updates_config(job_client, db_session):
    user = _create_user(db_session, "apply_owner", "apply_owner@example.com")
    headers = _auth_headers(user)
    resume = _create_resume(db_session, user_id=user.id)
    resume.parsed_json = {
        "skills": ["python"],
        "years_exp": 2,
        "expected_salary": "25k-35k",
        "location": "Beijing",
    }
    job = _create_job(db_session, title="backend-job-2", user_id=None, source="api")
    job.parsed_json = {
        "required_skills": ["python", "redis", "mysql", "docker"],
        "experience_requirement": "5-8年",
    }
    job.salary_range = "12k-18k"
    job.location = "Shanghai"
    db_session.add_all([resume, job])
    db_session.commit()

    db_session.add(
        JobRecommendationFeedback(
            user_id=user.id,
            resume_id=resume.id,
            jd_id=job.id,
            feedback_type="dislike",
            match_score=88,
            created_at=datetime(2026, 6, 23, 10, 0, 0),
        )
    )
    db_session.commit()

    dry_run = job_client.post("/jobs/feedback/apply-tuning", json={"dry_run": True}, headers=headers)
    assert dry_run.status_code == 200
    dry_body = dry_run.json()
    assert dry_body["code"] == 0
    assert dry_body["data"]["sample_total"] == 1
    assert dry_body["data"]["confidence"] > 0

    apply_resp = job_client.post("/jobs/feedback/apply-tuning", json={"dry_run": False}, headers=headers)
    assert apply_resp.status_code == 200
    apply_body = apply_resp.json()
    assert apply_body["code"] == 0
    assert apply_body["data"]["saved_config"]["vector_weight"] != 0.6
    assert apply_body["data"]["saved_config"]["rule_weight"] != 0.4


def test_job_recommend_config_roundtrip_and_recommend_uses_saved_config(job_client, db_session, monkeypatch):
    user = _create_user(db_session, "config_owner", "config_owner@example.com")
    headers = _auth_headers(user)
    resume = _create_resume(db_session, user_id=user.id)

    original = job_client.get("/jobs/recommend-config", headers=headers)
    assert original.status_code == 200
    assert original.json()["data"]["vector_weight"] == 0.6

    updated_payload = {
        "vector_weight": 0.3,
        "rule_weight": 0.7,
        "rule_components": {
            "skill": 0.4,
            "experience": 0.3,
            "salary": 0.2,
            "location": 0.1,
        },
        "thresholds": {
            "high": 88,
            "medium": 66,
        },
    }
    updated = job_client.put("/jobs/recommend-config", json=updated_payload, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["data"]["rule_weight"] == 0.7

    captured = {}

    def fake_recommend(self, resume_id, limit=5, filters=None, bypass_cache=False):
        captured["resume_id"] = resume_id
        captured["vector_weight"] = self._vector_weight
        captured["rule_weight"] = self._rule_weight
        captured["rule_components"] = self._rule_component_weights
        captured["high"] = self.THRESHOLD_HIGH
        captured["medium"] = self.THRESHOLD_MEDIUM
        return []

    monkeypatch.setattr("app.api.job_recommend.JobRecommendationEngine.recommend", fake_recommend)

    recommend_resp = job_client.get(
        "/jobs/recommend",
        params={"resume_id": resume.id},
        headers=headers,
    )
    assert recommend_resp.status_code == 200
    assert captured["resume_id"] == resume.id
    assert captured["vector_weight"] == 0.3
    assert captured["rule_weight"] == 0.7
    assert captured["rule_components"]["salary"] == 0.2
    assert captured["high"] == 88
    assert captured["medium"] == 66

    reset = job_client.post("/jobs/recommend-config/reset", headers=headers)
    assert reset.status_code == 200
    assert reset.json()["data"]["vector_weight"] == 0.6


def test_job_recommend_config_compare_returns_delta(job_client, db_session):
    user = _create_user(db_session, "compare_owner", "compare_owner@example.com")
    headers = _auth_headers(user)
    resume = _create_resume(db_session, user_id=user.id)
    resume.parsed_json = {
        "skills": ["python", "sql"],
        "years_exp": 3,
        "expected_salary": "20k-30k",
        "location": "Beijing",
    }
    job = _create_job(db_session, title="ml-backend", user_id=None, source="api")
    job.parsed_json = {
        "required_skills": ["python", "sql", "docker"],
        "experience_requirement": "3-5年",
    }
    job.salary_range = "18k-28k"
    job.location = "Beijing"
    db_session.add_all([resume, job])
    db_session.commit()

    db_session.add(
        JobRecommendationFeedback(
            user_id=user.id,
            resume_id=resume.id,
            jd_id=job.id,
            feedback_type="like",
            match_score=78,
            created_at=datetime(2026, 6, 24, 10, 0, 0),
        )
    )
    db_session.commit()

    response = job_client.post(
        "/jobs/recommend-config/compare",
        json={
            "label_a": "baseline",
            "label_b": "candidate",
            "config_a": {
                "vector_weight": 0.6,
                "rule_weight": 0.4,
                "rule_components": {"skill": 0.5, "experience": 0.2, "salary": 0.15, "location": 0.15},
                "thresholds": {"high": 80, "medium": 60},
            },
            "config_b": {
                "vector_weight": 0.2,
                "rule_weight": 0.8,
                "rule_components": {"skill": 0.7, "experience": 0.1, "salary": 0.1, "location": 0.1},
                "thresholds": {"high": 75, "medium": 55},
            },
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["sample_total"] == 1
    assert body["data"]["variant_a"]["label"] == "baseline"
    assert body["data"]["variant_b"]["label"] == "candidate"
    assert "agreement_rate" in body["data"]["delta"]
    assert "top_movers" in body["data"]["delta"]
