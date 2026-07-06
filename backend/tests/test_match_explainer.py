from types import SimpleNamespace

from app.services.match_explainer_service import MatchExplainer


def test_match_explainer_ignores_none_values(monkeypatch):
    monkeypatch.setattr(
        "app.services.match_explainer_service.chat_json",
        lambda prompt: {
            "overall": "候选人与岗位整体匹配。",
            "reasons": {
                "skill": "技能基本匹配",
                "project": "项目经历相关",
                "experience": "经验符合要求",
                "education": "学历满足要求",
                "keyword": "关键词有覆盖",
                "bonus": "加分项一般",
            },
            "risk_points": [],
            "suggestions": [],
        },
    )

    resume = SimpleNamespace(
        parsed_json={
            "skills": [None, "Python", {"skill": None}, {"skill": "FastAPI"}],
            "projects": [{"tech": [None, "Python"], "desc": None}],
            "education": None,
            "years_exp": 3,
        }
    )
    jd = SimpleNamespace(
        title="Python 后端",
        parsed_json={
            "title": "Python 后端",
            "required_skills": [None, "Python", {"skill": None}, {"skill": "FastAPI"}],
            "nice_to_have": [None, {"skill": "Docker"}],
            "responsibilities": [None, {"responsibility": "接口开发"}],
            "keywords": [None, {"requirement": None, "reason": "稳定性"}],
            "education_requirement": None,
            "experience_requirement": {"years": "3-5年"},
        },
    )

    result = MatchExplainer().explain(resume, jd).to_dict()

    assert result["overall_score"] >= 0
    assert "python" in result["skill_match"]["matched"]


def test_match_explainer_falls_back_to_jd_skill_tags(monkeypatch):
    monkeypatch.setattr(
        "app.services.match_explainer_service.chat_json",
        lambda prompt: {
            "overall": "候选人与岗位整体匹配。",
            "reasons": {
                "skill": "技能基本匹配",
                "project": "项目经历相关",
                "experience": "经验符合要求",
                "education": "学历满足要求",
                "keyword": "关键词有覆盖",
                "bonus": "加分项一般",
            },
            "risk_points": [],
            "suggestions": [],
        },
    )

    resume = SimpleNamespace(
        parsed_json={"skills": ["Python", "FastAPI"], "years_exp": 3}
    )
    jd = SimpleNamespace(
        title="Python 后端",
        skill_tags=["Python", "Docker"],
        experience_requirement="3-5年",
        education_requirement="本科及以上",
        parsed_json={},
    )

    result = MatchExplainer().explain(resume, jd).to_dict()

    assert "python" in result["skill_match"]["matched"]
    assert "docker" in result["skill_match"]["missing_required"]
