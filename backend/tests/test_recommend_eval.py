from datetime import datetime

from app.models.job_recommend import JobRecommendationFeedback
from scripts.eval_recommend import check_thresholds as check_recommend_thresholds
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
    # 这个 case 的 expected_missing_skills 是空的，预测也没有缺失项 → 没有任何可比项。
    # 以前 `_mean(parts) or 1.0` 会把它写成满分 1.0；现在如实是"未测出"。
    assert report["jd_explanation_consistency"] is None
    assert report["measured_cases"]["jd_explanation_consistency"] == 0
    assert report["recommendation_explainability"] > 0
    assert report["interview_score_stability"] >= 0.9
    assert report["feedback_agreement_rate"] == 1.0
    assert report["online_feedback_linkage"]["linked_pair_count"] == 1
    assert report["online_feedback_linkage"]["linked_feedback_count"] == 1
    assert report["online_feedback_linkage"]["feedback_summary"]["like_rate"] == 1.0
    assert report["details"][0]["id"] == "recommend_eval_case"


def test_all_wrong_consistency_arms_read_zero_not_perfect(monkeypatch):
    """改前的形状：两臂全错 → _mean 得 0.0 → `or 1.0` 把它读成"完全一致"。"""
    from scripts import eval_recommend

    def fake_explainer(_resume_profile, _jd_profile):
        return {
            "skill_match": {"matched": ["python"], "missing_required": ["kubernetes"]},
            "recommendation": "强烈推荐",
            "overall_score": 90,
            "overall_reason": "只提到 python",
            "dimensions": [{"reason": "python"}],
            "risk_points": ["r"],
            "optimization_suggestions": ["s"],
        }

    monkeypatch.setattr(eval_recommend, "_run_explainer", fake_explainer)

    case = {
        "id": "all_wrong",
        "resume_profile": {"skills": ["Python"]},
        "jd_profile": {"required_skills": ["Kubernetes"]},
        "expected_skill_overlap": ["python"],
        "expected_missing_skills": ["tableau"],  # 预测的是 kubernetes → Jaccard 0
        "expected_recommendation": "不建议投递",  # 预测 强烈推荐 → 0
        "expected_reason_keywords": ["tableau"],
        "interview_score_samples": [70, 80],
    }

    detail = eval_recommend._evaluate_case(case)
    assert detail["missing_skill_consistency"] == 0.0
    assert detail["jd_explanation_consistency"] == 0.0

    report = eval_recommend.run_eval([case], db=None)
    assert report["jd_explanation_consistency"] == 0.0
    assert report["measured_cases"]["jd_explanation_consistency"] == 1
    assert check_recommend_thresholds(report, min_explanation_consistency=0.85) == [
        "jd_explanation_consistency 0.0 < 0.85"
    ]
