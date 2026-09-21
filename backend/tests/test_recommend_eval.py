import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from app.models.job_recommend import JobRecommendationFeedback
from app.services.skill_gap import canonical_skill
from scripts import eval_recommend
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


FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "eval" / "recommend_eval.jsonl"


def _load_fixture() -> list[dict]:
    return [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _canon(values):
    return {c for c in (canonical_skill(v) for v in values) if c}


def test_fixture_labels_are_the_documented_set_rule():
    """标签必须等于 skill_gap 权威定义下的集合运算。

    这条测试是"别用被测代码回生成标签"的护栏：谁把 expected_* 改成迎合 explainer 的输出，
    这里就红。技能身份（canonical_skill）本身归 skill_gap 所有，是 B2 定的单一权威。
    """
    cases = _load_fixture()
    assert len(cases) >= 15, f"评估集只剩 {len(cases)} 条，门槛没有分辨率"

    with_missing = 0
    discriminating = 0
    for case in cases:
        resume = _canon((case.get("resume_profile") or {}).get("skills") or [])
        jd = case.get("jd_profile") or {}
        required = _canon(jd.get("required_skills") or jd.get("skills") or [])
        nice = _canon(jd.get("nice_to_have") or [])
        assert sorted(resume & (required | nice)) == case["expected_skill_overlap"], case["id"]
        assert sorted(required - resume) == case["expected_missing_skills"], case["id"]
        with_missing += 1 if case["expected_missing_skills"] else 0
        discriminating += 1 if resume != _canon(case["expected_skill_overlap"]) else 0

    # 缺失那一臂要真有得测；抄简历列表要真的会掉分
    assert with_missing >= 10, f"只有 {with_missing} 条 case 有期望缺失，缺失一致性门没有分辨率"
    assert discriminating >= 12, f"只有 {discriminating} 条 case 的简历带 JD 没要求的技能，抄列表空模型抓不住"


def test_null_models_cannot_clear_the_shipped_floors():
    """把"不看系统的笨猜测最高能得几分"钉在测试里：门槛一旦被人调回基线以下就会红。"""
    baselines = eval_recommend.trivial_baselines(_load_fixture())

    assert baselines is not None
    assert baselines["skill_match_accuracy"] <= 0.75, baselines
    assert baselines["jd_explanation_consistency"] <= 0.5, baselines

    report = {"total": 16, "skill_match_accuracy": 1.0, "jd_explanation_consistency": 1.0}
    # 旧门槛 0.4 就在这条线以下
    old = eval_recommend.check_thresholds(report, min_skill_match_accuracy=0.4, trivial_baseline=baselines)
    assert old == [
        f"skill_match_accuracy 门槛 0.4 ≤ 空模型基线 {baselines['skill_match_accuracy']}："
        "不看系统输出的笨猜测也能过，抬门槛或改标签"
    ]
    assert (
        eval_recommend.check_thresholds(
            report, min_skill_match_accuracy=0.9, min_explanation_consistency=0.9, trivial_baseline=baselines
        )
        == []
    )


def test_unreadable_db_degrades_the_feedback_arm_instead_of_crashing():
    """CI 没有 MySQL：反馈那一臂要"读不到"地说自己读不到，而不是把整个评估炸掉。"""

    class _DeadSession:
        def query(self, *args, **kwargs):
            raise SQLAlchemyError("Can't connect to MySQL server")

    linkage = eval_recommend._build_online_feedback_linkage(_load_fixture()[:1], [], _DeadSession())

    assert linkage["feedback_agreement_rate"] is None
    assert linkage["linked_pair_count"] == 0
    assert linkage["linkage_status"].startswith("db unavailable: SQLAlchemyError")
