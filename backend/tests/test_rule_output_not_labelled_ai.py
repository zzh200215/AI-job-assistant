"""A3: rule-derived output must not be labelled as AI analysis.

Two of the six spots the audit flagged turned out to be honest already and were
deliberately left alone: `MatchExplainer._generate_reason` reports real computed
facts under a non-AI name, and `dashboard._generate_suggestions` lives in the
weekly report as plain "suggestions". These tests pin the four that were not.
"""

from __future__ import annotations

from app.api import dashboard, resume as resume_api
from app.core.security import hash_password
from app.models.user import User


def _user(db):
    """The test database starts empty; make_resume does not create an owner."""
    user = User(
        username="a3_owner",
        email="a3_owner@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
from app.services.match_explainer_service import DimensionScore, MatchExplainer
from app.services.resume_analysis_service import quick_score_resume


# ------------------------------------------------------- completeness vs quality
def test_completeness_check_no_longer_claims_to_be_a_score(db_session, make_resume):
    """quick_score_resume counts populated sections; it must not call itself a
    resume quality score, and must not be silently substituted for one."""
    rid = make_resume(parsed_json={"name": "张三", "phone": "1", "email": "e@x.com"})
    result = quick_score_resume(db_session, rid)

    assert result["measure"] == "completeness"
    assert "completeness_score" in result
    assert "quick_score" not in result, "the old quality-sounding key is gone"
    assert "grade" not in result
    assert result["module_check"]["work_experience"] is False


def test_padding_a_resume_does_not_improve_quality_wording(db_session, make_resume):
    """Completeness is intentionally count-based; the point is that the API
    never presents it as quality."""
    thin = make_resume(parsed_json={"name": "A", "work_experience": [{"t": "x"}]})
    padded = make_resume(
        parsed_json={
            "name": "A",
            "work_experience": [{"t": "x"}] * 6,
            "projects": [{"t": "y"}] * 5,
            "skills": ["s"] * 10,
        }
    )
    thin_score = quick_score_resume(db_session, thin)["completeness_score"]
    padded_score = quick_score_resume(db_session, padded)["completeness_score"]

    # The count heuristic still rewards volume — that is why the key says
    # "completeness" and why nothing may feed it into a quality score.
    assert padded_score > thin_score


def test_diagnose_does_not_backfill_total_score_from_completeness(db_session, monkeypatch, make_resume):
    """Previously `overall_score` absent meant the completeness number appeared
    as the overall quality score."""
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A", "work_experience": [{"t": "x"}]})
    monkeypatch.setattr(
        resume_api,
        "analyze_resume",
        lambda *a, **k: {"dimensions": {}, "critical_issues": [], "strengths": []},
    )

    result = _call_diagnose(db_session, rid, user)

    assert result["total_score"] is None
    assert "completeness_score" in result
    assert result["completeness_issues"]  # rule output still available, correctly named


def test_diagnose_does_not_invent_issues_when_nothing_matched(db_session, monkeypatch, make_resume):
    user = _user(db_session)
    rid = make_resume(user_id=user.id, parsed_json={"name": "A"})
    monkeypatch.setattr(
        resume_api,
        "analyze_resume",
        lambda *a, **k: {"overall_score": 70, "dimensions": {}, "critical_issues": ["目标岗位偏后端"]},
    )

    result = _call_diagnose(db_session, rid, user)

    assert result["structure_issues"] == [], "stock advice must not appear as analysis"
    assert result["expression_issues"] == []
    assert result["total_score"] == 70


def _call_diagnose(db_session, resume_id, user):
    import asyncio

    payload = asyncio.run(
        resume_api.diagnose_resume(resume_id, {"target_position": ""}, db=db_session, current_user=user)
    )
    return payload["data"]


# ------------------------------------------------------------- explain fallback
def test_explain_fallback_declares_itself_rules_and_has_no_key_collision():
    explainer = MatchExplainer()
    def dim(name, score, weight):
        return DimensionScore(
            name=name, score=score, weight=weight, weighted_score=score * weight, reason=""
        )

    dims = [dim("技能匹配", 40, 0.3), dim("项目经历", 90, 0.2), dim("一个未登记的维度", 10, 0.1)]

    result = explainer._fallback_explain(dims, overall=55)

    assert result["explain_mode"] == "rules"
    # Unmapped dimension names used to collapse onto a single "" key.
    assert "" not in result["reasons"]
    assert set(result["reasons"]) == {"skill", "project"}
    assert result["suggestions"] == [], "generic advice must not masquerade as analysis"
    assert "规则" in result["overall"]
    assert MatchExplainer().explain.__doc__  # sanity: class still importable


# --------------------------------------------------------------- next actions
def test_next_actions_declares_rules_mode_and_can_return_nothing(db_session, monkeypatch):
    """The endpoint used to pad to 3 suggestions so the panel always looked busy."""
    import asyncio

    user = _user(db_session)
    response = asyncio.run(dashboard.next_actions(db=db_session, current_user=user))

    data = response["data"]
    assert data["mode"] == "rules"
    assert len(data["suggestions"]) <= 3
    assert "context" in data


def test_ai_suggestions_route_is_gone():
    """The old AI-branded path must not linger as a hidden alias."""
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/dashboard/ai-suggestions" not in paths
    assert "/api/dashboard/next-actions" in paths
