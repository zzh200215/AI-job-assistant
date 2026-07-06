# -*- coding: utf-8 -*-
from datetime import datetime

from app.models.job_recommend import JobRecommendationFeedback
from scripts.eval_recommend import run_eval


def test_recommend_eval_generates_metrics_and_feedback_linkage(db_session, make_resume, make_jd):
    resume_id = make_resume(
        parsed_json={
            "name": "Eval User",
            "skills": ["Python", "FastAPI", "Redis", "Docker"],
            "years_exp": 3,
            "education": "本科",
            "project_experience": [{"desc": "负责后端接口与缓存优化", "tech": ["Python", "FastAPI", "Redis"]}],
        }
    )
    jd_id = make_jd(
        title="Python 后端开发工程师",
        parsed_json={
            "title": "Python 后端开发工程师",
            "required_skills": ["Python", "FastAPI", "Redis"],
            "nice_to_have": ["Docker"],
            "experience_requirement": "3-5年",
            "education_requirement": "本科",
            "responsibilities": ["后端 API 开发"],
            "keywords": ["python", "fastapi", "redis"],
        },
    )

    db_session.add(
        JobRecommendationFeedback(
            user_id=1,
            resume_id=resume_id,
            jd_id=jd_id,
            feedback_type="like",
            match_score=88,
            created_at=datetime(2026, 6, 28, 10, 0, 0),
        )
    )
    db_session.commit()

    report = run_eval(
        [
            {
                "id": "recommend_eval_case",
                "resume_id": resume_id,
                "jd_id": jd_id,
                "resume_profile": {
                    "name": "Eval User",
                    "skills": ["Python", "FastAPI", "Redis", "Docker"],
                    "years_exp": 3,
                    "education": "本科",
                    "project_experience": [{"desc": "负责后端接口与缓存优化", "tech": ["Python", "FastAPI", "Redis"]}],
                },
                "jd_profile": {
                    "title": "Python 后端开发工程师",
                    "required_skills": ["Python", "FastAPI", "Redis"],
                    "nice_to_have": ["Docker"],
                    "experience_requirement": "3-5年",
                    "education_requirement": "本科",
                    "responsibilities": ["后端 API 开发"],
                    "keywords": ["python", "fastapi", "redis"],
                },
                "expected_skill_overlap": ["python", "fastapi", "redis", "docker"],
                "expected_missing_skills": [],
                "expected_reason_keywords": ["python", "fastapi", "redis"],
                "interview_score_samples": [81, 83, 82],
            }
        ],
        db=db_session,
    )

    assert report["total"] == 1
    assert report["skill_match_accuracy"] >= 0.75
    assert report["jd_explanation_consistency"] >= 0.9
    assert report["recommendation_explainability"] > 0
    assert report["interview_score_stability"] >= 0.9
    assert report["feedback_agreement_rate"] == 1.0
    assert report["online_feedback_linkage"]["linked_pair_count"] == 1
    assert report["online_feedback_linkage"]["linked_feedback_count"] == 1
    assert report["online_feedback_linkage"]["feedback_summary"]["like_rate"] == 1.0
    assert report["details"][0]["id"] == "recommend_eval_case"
