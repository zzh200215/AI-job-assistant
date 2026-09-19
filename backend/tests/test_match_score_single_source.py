"""A4: one (resume, job) pair must have exactly one displayed match score.

Before this, three paths computed three numbers — the recommend engine's
vector/rule blend, the explainer's 6-dimension rubric, and a raw LLM score — and
none of them applied the weak-fit cap, so the recommend page and the explain page
could disagree about the same job.
"""

from __future__ import annotations

from app.core.security import hash_password
from app.models.history import JobDescription, Resume
from app.models.match_score import MatchScore
from app.models.user import User
from app.services.match_explainer_service import MatchExplainer
from app.services.scoring_config import SCORE_METHOD
from app.services.match_score_service import (
    canonical_match_score,
    compute_canonical_score,
    resume_version_of,
)


def _user(db, name="a4_user"):
    user = User(
        username=name,
        email=f"{name}@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _resume(db, user, skills, years=3, self_eval="三年经验"):
    row = Resume(
        user_id=user.id,
        name="a4 resume",
        file_name="a4.pdf",
        file_path="uploads/a4.pdf",
        file_type="pdf",
        file_size=1024,
        parsed_json={
            "name": "张三",
            "skills": skills,
            "years_exp": years,
            "education": "本科",
            "project_experience": [],
            "self_evaluation": self_eval,
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _job(db, user, required, title="后端工程师", experience_requirement=""):
    row = JobDescription(
        user_id=user.id,
        title=title,
        company="示例公司",
        location="上海",
        raw_text=f"{title} 示例公司",
        is_active=1,
        parsed_json={
            "title": title,
            "required_skills": required,
            "nice_to_have": [],
            "experience_requirement": experience_requirement,
            "education_requirement": "本科",
            "keywords": [],
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_rubric_does_not_mutate_the_objects_it_scores(db_session):
    """A scoring function must not write into the resume it is reading.

    compute_rubric backfills compatibility fields; they used to land on the live
    parsed_json dict, so `skills: []` could be persisted onto a real resume and
    scoring the same pair twice produced different numbers.
    """
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python", "FastAPI"])
    jd = _job(db_session, user, ["Python"])

    before_resume = dict(resume.parsed_json)
    before_jd = dict(jd.parsed_json)

    MatchExplainer().compute_rubric(resume, jd)

    assert resume.parsed_json == before_resume, "compute_rubric mutated resume.parsed_json"
    assert jd.parsed_json == before_jd, "compute_rubric mutated jd.parsed_json"


def test_scoring_the_same_pair_twice_is_stable(db_session):
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python", "FastAPI", "Docker"])
    jd = _job(db_session, user, ["Python", "Kubernetes"])

    first = compute_canonical_score(resume, jd)["score"]
    second = compute_canonical_score(resume, jd)["score"]

    assert first == second


def test_explain_and_canonical_agree_on_the_same_number(db_session):
    """The acceptance criterion: recommend and explain cannot disagree."""
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python", "FastAPI"])
    jd = _job(db_session, user, ["Python", "PostgreSQL"])

    canonical = canonical_match_score(db_session, resume, jd, user_id=user.id)["score"]
    explained = MatchExplainer().explain(resume, jd).overall_score

    assert round(float(explained), 1) == round(float(canonical), 1)


def test_weak_fit_cap_applies_on_the_canonical_path(db_session):
    """The cap used to run only inside the agent graph, never on the two paths
    candidates actually see.

    Note the limit of the current implementation: infer_match_score_cap only
    recognises three role shapes (全栈 / 高级产品经理 / 技术项目经理), so this is a
    targeted guard, not a general weak-fit detector.
    """
    user = _user(db_session)
    # Frontend-only candidate against a full-stack role: has_frontend true,
    # has_backend and has_db both absent, which is the documented cap-55 case.
    resume = _resume(
        db_session,
        user,
        ["React", "TypeScript"],
        years=3,
        self_eval="三年界面开发经验",
    )
    jd = _job(
        db_session,
        user,
        ["React", "Node.js", "PostgreSQL"],
        title="全栈工程师",
    )

    result = compute_canonical_score(resume, jd)

    assert result["cap_applied"] == 55
    # The invariant is that the displayed score never exceeds the cap; whether it
    # binds depends on the rubric score itself.
    assert result["score"] == round(min(result["raw_score"], 55.0), 1)


def test_canonical_score_is_persisted_once_per_pair(db_session):
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python"])
    jd = _job(db_session, user, ["Python"])

    canonical_match_score(db_session, resume, jd, user_id=user.id)
    canonical_match_score(db_session, resume, jd, user_id=user.id)

    rows = (
        db_session.query(MatchScore)
        .filter(MatchScore.resume_id == resume.id, MatchScore.jd_id == jd.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].method == SCORE_METHOD
    assert rows[0].resume_version == resume_version_of(resume)


def test_recommend_engine_reports_the_canonical_score(monkeypatch, db_session):
    """The engine may still rank by its blend internally, but the number it hands
    the UI must be the canonical one."""
    from app.services import job_recommend_engine as engine_mod

    user = _user(db_session)
    resume = _resume(db_session, user, ["Python", "FastAPI"])
    jd = _job(db_session, user, ["Python"])

    engine = engine_mod.JobRecommendationEngine(db_session)
    results = engine.recommend(resume.id, limit=5, bypass_cache=True)

    assert results, "expected at least one recommendation"
    by_id = {item["jd_id"]: item for item in results}
    assert jd.id in by_id

    canonical = canonical_match_score(db_session, resume, jd, user_id=user.id, persist=False)["score"]
    assert round(float(by_id[jd.id]["match_score"])) == round(float(canonical))
    assert by_id[jd.id]["match_score_method"] == SCORE_METHOD
    # Retrieval signal is still reported, but as a separate diagnostic field.
    assert "retrieval_score" in by_id[jd.id]


def test_resume_without_stated_tenure_does_not_crash_the_rubric(db_session):
    """`resume.get("years_exp", 0)` yields None when the key exists but is null,
    which made `abs(None - jd_mid)` raise and 500 /explain-match for any resume
    parsed without a stated tenure."""
    user = _user(db_session)
    resume = _resume(db_session, user, ["Python"])
    resume.parsed_json = {**resume.parsed_json, "years_exp": None}
    jd = _job(db_session, user, ["Python"], experience_requirement="3-5年")

    result = compute_canonical_score(resume, jd)

    assert 0 <= result["score"] <= 100
    exp = next(d for d in result["dimensions"] if d["name"] == "工作经验")
    assert any("未标注工作年限" in detail for detail in exp["details"])


def test_coerce_years_distinguishes_absent_from_zero():
    coerce = MatchExplainer._coerce_years

    assert coerce(None) is None
    assert coerce("") is None
    assert coerce("未提及") is None
    assert coerce(0) == 0.0
    assert coerce("3年") == 3.0
    assert coerce(3.5) == 3.5
