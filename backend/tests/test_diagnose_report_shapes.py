"""The diagnosis report must survive a model that follows its own schema.

`/resume/{id}/diagnose` used to read `dimensions.get("structure", 0)` and hand the
result straight to the UI. The analysis prompt asks for
`{"score": .., "issues": [], "suggestions": []}` per dimension, so every
schema-conforming response rendered as a JSON blob next to a 0-width bar, the
dict-shaped `improvement_roadmap` was dropped by an `isinstance(list)` check, and
the model's `missing_keywords` — nested inside its dimension — never appeared, so
the keywords panel told candidates "覆盖良好" about a resume with five named gaps.
"""

from __future__ import annotations

import asyncio

from app.api import resume as resume_api
from app.core.security import hash_password
from app.models.user import User

SCHEMA_ANALYSIS = {
    "overall_score": 65,
    "dimensions": {
        "structure": {
            "score": 60,
            "issues": ["缺少明确的个人简介模块"],
            "suggestions": ["添加个人简介"],
        },
        "content_quality": {"score": 65, "issues": ["描述过于笼统"], "suggestions": ["补充成果"]},
        "keyword_density": {
            "score": 70,
            "issues": [],
            "suggestions": [],
            "missing_keywords": ["RESTful API", "微服务架构", "CI/CD"],
        },
        "differentiation": {"score": 50, "issues": ["缺乏差异化亮点"], "suggestions": []},
        "ats_friendly": {"score": 75, "issues": [], "suggestions": []},
    },
    "strengths": ["4 年经验", "掌握 Python"],
    "critical_issues": ["目标岗位偏后端"],
    "improvement_roadmap": {
        "quick_wins": ["1 小时内：补一行个人简介"],
        "medium_effort": ["1-2 天：重写项目描述"],
        "major_rework": ["需要重构：职业主线"],
    },
    "target_position_match": {
        "match_level": "中",
        "gap_analysis": ["技能展示不全"],
        "bridge_strategies": ["补充关键词"],
    },
}


def _user(db):
    user = User(username="diag_owner", email="diag_owner@example.com", password=hash_password("StrongP@ssw0rd"), role="candidate")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _diagnose(db, resume_id, user, analysis, monkeypatch):
    monkeypatch.setattr(resume_api, "analyze_resume", lambda *a, **k: analysis)
    body = asyncio.run(resume_api.diagnose_resume(resume_id, {"target_position": ""}, db=db, current_user=user))
    assert body["code"] == 0, body
    return body["data"]


def test_dimension_scores_are_numbers_not_blobs(db_session, make_resume, monkeypatch):
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A", "self_evaluation": "x"})

    result = _diagnose(db_session, rid, user, SCHEMA_ANALYSIS, monkeypatch)

    assert result["structure_score"] == 60
    assert result["expression_score"] == 65
    assert result["keyword_score"] == 70
    assert result["highlight_score"] == 50
    assert result["ats_score"] == 75
    assert result["total_score"] == 65


def test_the_models_own_dimension_issues_win_over_keyword_guessing(db_session, make_resume, monkeypatch):
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A", "self_evaluation": "x"})

    result = _diagnose(db_session, rid, user, SCHEMA_ANALYSIS, monkeypatch)

    assert result["structure_issues"] == ["缺少明确的个人简介模块"]
    assert result["expression_issues"] == ["描述过于笼统"]


def test_missing_keywords_reach_the_report(db_session, make_resume, monkeypatch):
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A", "self_evaluation": "x"})

    result = _diagnose(db_session, rid, user, SCHEMA_ANALYSIS, monkeypatch)

    assert result["missing_keywords"] == ["RESTful API", "微服务架构", "CI/CD"]


def test_a_dict_shaped_roadmap_is_not_discarded(db_session, make_resume, monkeypatch):
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A", "self_evaluation": "x"})

    result = _diagnose(db_session, rid, user, SCHEMA_ANALYSIS, monkeypatch)

    assert result["improvement_roadmap"] == [
        "1 小时内：补一行个人简介",
        "1-2 天：重写项目描述",
        "需要重构：职业主线",
    ]


def test_match_analysis_renders_as_a_sentence(db_session, make_resume, monkeypatch):
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A", "self_evaluation": "x"})

    result = _diagnose(db_session, rid, user, SCHEMA_ANALYSIS, monkeypatch)

    assert result["match_analysis"] == "匹配度：中。差距：技能展示不全。弥补方式：补充关键词"


def test_punctuated_items_do_not_double_up(db_session, make_resume, monkeypatch):
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A", "self_evaluation": "x"})
    analysis = dict(SCHEMA_ANALYSIS)
    analysis["target_position_match"] = {
        "match_level": "中",
        "gap_analysis": ["技能展示不全。", "缺少关键词。"],
        "bridge_strategies": [],
    }

    result = _diagnose(db_session, rid, user, analysis, monkeypatch)

    assert result["match_analysis"] == "匹配度：中。差距：技能展示不全；缺少关键词"


def test_a_flat_model_response_still_works(db_session, make_resume, monkeypatch):
    """Earlier models emitted bare numbers; both shapes must read."""
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A", "self_evaluation": "x"})
    flat = {
        "overall_score": 70,
        "dimensions": {"structure": 80, "ats_friendly": 90},
        "critical_issues": ["结构松散", "表达啰嗦"],
        "strengths": [],
        "improvement_roadmap": ["直接给条列"],
        "target_position_match": "整体匹配",
    }

    result = _diagnose(db_session, rid, user, flat, monkeypatch)

    assert result["structure_score"] == 80
    assert result["ats_score"] == 90
    assert result["keyword_score"] is None, "an absent dimension is unknown, not zero"
    assert result["structure_issues"] == ["结构松散"]
    assert result["expression_issues"] == ["表达啰嗦"]
    assert result["improvement_roadmap"] == ["直接给条列"]
    assert result["match_analysis"] == "整体匹配"


def test_a_boolean_score_is_not_a_score(db_session, make_resume, monkeypatch):
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A", "self_evaluation": "x"})
    weird = {"dimensions": {"structure": {"score": True}}, "critical_issues": [], "strengths": []}

    result = _diagnose(db_session, rid, user, weird, monkeypatch)

    assert result["structure_score"] is None
