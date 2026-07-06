# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

import pytest

from app.models.history import JobDescription
from app.services.job_recommend_engine import JobRecommendationEngine


def _create_job(
    db_session,
    *,
    title: str,
    location: str = "Beijing",
    salary_range: str = "25k-35k",
    industry: str = "AI",
    required_skills=None,
    experience_requirement: str = "3-5 years",
    **overrides,
):
    job = JobDescription(
        title=title,
        company="Test Co",
        location=location,
        salary_range=salary_range,
        raw_text=f"{title} role",
        industry=industry,
        is_active=1,
        experience_requirement=experience_requirement,
        parsed_json={
            "title": title,
            "required_skills": required_skills or ["python", "fastapi"],
            "experience_requirement": experience_requirement,
        },
        **overrides,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


@pytest.fixture(autouse=True)
def clear_recommend_cache():
    JobRecommendationEngine.clear_cache()
    yield
    JobRecommendationEngine.clear_cache()


def test_recommend_cache_reuses_full_results_for_different_limits(db_session, make_resume):
    resume_id = make_resume(
        parsed_json={
            "name": "User A",
            "skills": ["python", "fastapi"],
            "years_exp": 4,
            "location": "Beijing",
            "expected_salary": "20k-30k",
        }
    )
    for idx in range(3):
        _create_job(db_session, title=f"Backend {idx}")

    with patch("app.services.job_recommend_engine.get_knowledge_collection", return_value=MagicMock()), patch(
        "app.services.job_recommend_engine.embed_texts",
        side_effect=lambda texts: [[1.0, 0.0] for _ in texts],
    ) as mock_embed:
        engine = JobRecommendationEngine(db_session)
        first = engine.recommend(resume_id=resume_id, limit=1)
        second = engine.recommend(resume_id=resume_id, limit=3)

    assert len(first) == 1
    assert len(second) == 3
    assert mock_embed.call_count == 1


def test_recommend_cache_uses_stable_filter_key(db_session, make_resume):
    resume_id = make_resume(
        parsed_json={
            "name": "User B",
            "skills": ["python", "fastapi"],
            "years_exp": 4,
            "location": "Beijing",
            "expected_salary": "20k-30k",
        }
    )
    _create_job(db_session, title="Backend Stable")

    with patch("app.services.job_recommend_engine.get_knowledge_collection", return_value=MagicMock()), patch(
        "app.services.job_recommend_engine.embed_texts",
        side_effect=lambda texts: [[1.0, 0.0] for _ in texts],
    ) as mock_embed:
        engine = JobRecommendationEngine(db_session)
        filters_a = {"location": "Beijing", "salary_min": 20}
        filters_b = {"salary_min": 20, "location": "Beijing"}
        first = engine.recommend(resume_id=resume_id, limit=5, filters=filters_a)
        second = engine.recommend(resume_id=resume_id, limit=5, filters=filters_b)

    assert first == second
    assert mock_embed.call_count == 1


def test_recommend_cache_returns_isolated_copies(db_session, make_resume):
    resume_id = make_resume(
        parsed_json={
            "name": "User C",
            "skills": ["python", "fastapi"],
            "years_exp": 4,
            "location": "Beijing",
            "expected_salary": "20k-30k",
        }
    )
    _create_job(db_session, title="Backend Copy")

    with patch("app.services.job_recommend_engine.get_knowledge_collection", return_value=MagicMock()), patch(
        "app.services.job_recommend_engine.embed_texts",
        side_effect=lambda texts: [[1.0, 0.0] for _ in texts],
    ) as mock_embed:
        engine = JobRecommendationEngine(db_session)
        first = engine.recommend(resume_id=resume_id, limit=5)
        first[0]["job_title"] = "Mutated"
        second = engine.recommend(resume_id=resume_id, limit=5)

    assert second[0]["job_title"] == "Backend Copy"
    assert mock_embed.call_count == 1


def test_recommend_exp_level_filter_is_applied(db_session, make_resume):
    resume_id = make_resume(
        parsed_json={
            "name": "User D",
            "skills": ["python", "fastapi"],
            "years_exp": 3,
            "location": "Beijing",
            "expected_salary": "20k-30k",
        }
    )
    _create_job(db_session, title="Junior Backend", experience_requirement="1-3 years")
    _create_job(db_session, title="Senior Backend", experience_requirement="5-8 years")

    with patch("app.services.job_recommend_engine.get_knowledge_collection", return_value=MagicMock()), patch(
        "app.services.job_recommend_engine.embed_texts",
        side_effect=lambda texts: [[1.0, 0.0] for _ in texts],
    ):
        engine = JobRecommendationEngine(db_session)
        results = engine.recommend(
            resume_id=resume_id,
            limit=10,
            filters={"exp_level": "junior"},
            bypass_cache=True,
        )

    assert [item["job_title"] for item in results] == ["Junior Backend"]


def test_recommend_only_uses_owned_and_public_jobs(db_session, make_resume):
    resume_id = make_resume(
        user_id=1,
        parsed_json={
            "name": "User E",
            "skills": ["python", "fastapi"],
            "years_exp": 3,
            "location": "Beijing",
            "expected_salary": "20k-30k",
        },
    )
    _create_job(db_session, title="Owned Backend", user_id=1)
    _create_job(db_session, title="Public Backend", user_id=None)
    _create_job(db_session, title="Other User Backend", user_id=2)

    with patch("app.services.job_recommend_engine.get_knowledge_collection", return_value=MagicMock()), patch(
        "app.services.job_recommend_engine.embed_texts",
        side_effect=lambda texts: [[1.0, 0.0] for _ in texts],
    ):
        engine = JobRecommendationEngine(db_session)
        results = engine.recommend(resume_id=resume_id, limit=10, bypass_cache=True)

    assert [item["job_title"] for item in results] == ["Owned Backend", "Public Backend"]


def test_recommend_industry_filter_matches_normalized_keyword(db_session, make_resume):
    resume_id = make_resume(
        parsed_json={
            "name": "User F",
            "skills": ["python", "fastapi"],
            "years_exp": 3,
            "location": "Beijing",
            "expected_salary": "20k-30k",
        }
    )
    _create_job(db_session, title="AI Backend", industry="AI")
    _create_job(db_session, title="Cloud Backend", industry="Cloud")

    with patch("app.services.job_recommend_engine.get_knowledge_collection", return_value=MagicMock()), patch(
        "app.services.job_recommend_engine.embed_texts",
        side_effect=lambda texts: [[1.0, 0.0] for _ in texts],
    ):
        engine = JobRecommendationEngine(db_session)
        results = engine.recommend(
            resume_id=resume_id,
            limit=10,
            filters={"industry": "ai"},
            bypass_cache=True,
        )

    assert [item["job_title"] for item in results] == ["AI Backend"]


def test_recommend_exp_level_filter_keeps_jobs_without_experience_requirement(db_session, make_resume):
    resume_id = make_resume(
        parsed_json={
            "name": "User G",
            "skills": ["python", "fastapi"],
            "years_exp": 3,
            "location": "Beijing",
            "expected_salary": "20k-30k",
        }
    )
    _create_job(db_session, title="No Experience Backend", experience_requirement="")
    _create_job(db_session, title="Junior Backend", experience_requirement="1-3 years")
    _create_job(db_session, title="Senior Backend", experience_requirement="8-10 years")

    with patch("app.services.job_recommend_engine.get_knowledge_collection", return_value=MagicMock()), patch(
        "app.services.job_recommend_engine.embed_texts",
        side_effect=lambda texts: [[1.0, 0.0] for _ in texts],
    ):
        engine = JobRecommendationEngine(db_session)
        results = engine.recommend(
            resume_id=resume_id,
            limit=10,
            filters={"exp_level": "junior"},
            bypass_cache=True,
        )

    titles = [item["job_title"] for item in results]
    assert "No Experience Backend" in titles
    assert "Junior Backend" in titles
    assert "Senior Backend" not in titles
