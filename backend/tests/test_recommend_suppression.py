"""A5: "不感兴趣" and thumbs-down must actually remove a job from recommendations.

Both signals were already being written — JobBookmark(action="dismiss") and
JobRecommendationFeedback(feedback_type="dislike") — but only the analytics
dashboards read them, so a dismissed job reappeared on the next refresh.
"""

from __future__ import annotations

import pytest

from app.core.security import hash_password
from app.models.history import JobDescription, Resume
from app.models.job_recommend import JobBookmark, JobRecommendationFeedback
from app.models.user import User
from app.services import job_recommend_engine as engine_mod
from app.services.job_recommend_engine import JobRecommendationEngine, load_suppressed_jd_ids


@pytest.fixture(autouse=True)
def _clear_recommend_cache():
    engine_mod._RECOMMEND_CACHE.clear()
    yield
    engine_mod._RECOMMEND_CACHE.clear()


def _user(db, name):
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


def _resume(db, user):
    row = Resume(
        user_id=user.id,
        name="a5 resume",
        file_name="a5.pdf",
        file_path="uploads/a5.pdf",
        file_type="pdf",
        file_size=1024,
        parsed_json={
            "name": "李四",
            "skills": ["Python", "FastAPI"],
            "years_exp": 3,
            "education": "本科",
            "project_experience": [],
            "self_evaluation": "后端开发",
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _job(db, user, title):
    row = JobDescription(
        user_id=user.id if user is not None else None,
        title=title,
        company="示例公司",
        location="上海",
        raw_text=f"{title} 需要 Python FastAPI",
        is_active=1,
        parsed_json={
            "title": title,
            "required_skills": ["Python", "FastAPI"],
            "nice_to_have": [],
            "experience_requirement": "3-5年",
            "education_requirement": "本科",
            "keywords": [],
        },
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _dismiss(db, user, jd):
    db.add(JobBookmark(user_id=user.id, jd_id=jd.id, action="dismiss", note=""))
    db.commit()


def _recommended_ids(db, resume, limit=10):
    results = JobRecommendationEngine(db).recommend(resume_id=resume.id, limit=limit, bypass_cache=False)
    return {item["jd_id"] for item in results}


def test_dismissed_job_is_excluded_from_recommendations(db_session):
    user = _user(db_session, "a5_dismiss")
    resume = _resume(db_session, user)
    keep = _job(db_session, user, "算法工程师")
    gone = _job(db_session, user, "数据平台工程师")

    assert _recommended_ids(db_session, resume) >= {keep.id, gone.id}

    _dismiss(db_session, user, gone)

    assert gone.id not in _recommended_ids(db_session, resume)
    assert keep.id in _recommended_ids(db_session, resume)


def test_disliked_job_is_excluded(db_session):
    user = _user(db_session, "a5_dislike")
    resume = _resume(db_session, user)
    keep = _job(db_session, user, "后端工程师")
    disliked = _job(db_session, user, "运维工程师")

    db_session.add(
        JobRecommendationFeedback(
            user_id=user.id,
            resume_id=resume.id,
            jd_id=disliked.id,
            feedback_type="dislike",
            match_score=70,
        )
    )
    db_session.commit()

    recommended = _recommended_ids(db_session, resume)
    assert disliked.id not in recommended
    assert keep.id in recommended


def test_dismissing_invalidates_the_cached_recommendation_list(db_session):
    """The regression this guards: the list is cached in-process, so without the
    suppression fingerprint in the cache key a just-dismissed job would keep
    appearing until the TTL expired."""
    user = _user(db_session, "a5_cache")
    resume = _resume(db_session, user)
    target = _job(db_session, user, "测试工程师")

    engine_mod._RECOMMEND_CACHE.clear()
    assert target.id in _recommended_ids(db_session, resume)

    _dismiss(db_session, user, target)

    assert target.id not in _recommended_ids(db_session, resume)


def test_suppression_is_per_user(db_session):
    alice = _user(db_session, "a5_alice")
    bob = _user(db_session, "a5_bob")
    alice_resume = _resume(db_session, alice)
    bob_resume = _resume(db_session, bob)
    shared = _job(db_session, None, "共享岗位")  # platform-visible job

    _dismiss(db_session, alice, shared)

    assert shared.id not in _recommended_ids(db_session, alice_resume)
    assert shared.id in _recommended_ids(db_session, bob_resume)


def test_load_suppressed_returns_both_sources_and_changes_on_write(db_session):
    user = _user(db_session, "a5_fingerprint")
    resume = _resume(db_session, user)
    a = _job(db_session, user, "岗位A")
    b = _job(db_session, user, "岗位B")

    empty, version_before = load_suppressed_jd_ids(db_session, user.id)
    assert empty == set()

    _dismiss(db_session, user, a)
    db_session.add(
        JobRecommendationFeedback(
            user_id=user.id, resume_id=resume.id, jd_id=b.id, feedback_type="dislike", match_score=50
        )
    )
    db_session.commit()

    suppressed, version_after = load_suppressed_jd_ids(db_session, user.id)
    assert suppressed == {a.id, b.id}
    assert version_before != version_after, "cache fingerprint must move when suppression changes"


def test_like_feedback_does_not_suppress(db_session):
    user = _user(db_session, "a5_like")
    resume = _resume(db_session, user)
    liked = _job(db_session, user, "前端工程师")

    db_session.add(
        JobRecommendationFeedback(
            user_id=user.id, resume_id=resume.id, jd_id=liked.id, feedback_type="like", match_score=90
        )
    )
    db_session.commit()

    assert liked.id in _recommended_ids(db_session, resume)
