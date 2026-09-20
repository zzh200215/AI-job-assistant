"""What counts as "a new version of this resume", and therefore when scores redo.

`resume_version_of` keys both the persisted MatchScore rows and the in-process
recommendation cache. It used to be `Resume.update_time.isoformat()`, which is
unreliable twice over: MySQL stores that column as DATETIME(0), so two writes in
the same second share a version, and any write that cannot move a score (a touch,
an unrelated column) invalidates every cached score for the resume.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import hash_password
from app.models.history import JobDescription, Resume
from app.models.match_score import MatchScore
from app.models.user import User
from app.services.match_score_service import canonical_match_score, resume_version_of
from app.services.resume_blocks import apply_block_edits

FIXED_STAMP = datetime(2026, 9, 19, 3, 4, 5, tzinfo=timezone.utc)


@pytest.fixture
def user(db_session):
    row = User(
        username="ver_user", email="ver_user@example.com", password=hash_password("StrongP@ssw0rd"), role="candidate"
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _resume(db, user, stamp, self_eval="三年后端经验"):
    row = Resume(
        user_id=user.id,
        name="版本验证简历",
        file_name="v.pdf",
        file_path="uploads/v.pdf",
        file_type="pdf",
        file_size=1024,
        update_time=stamp,
        create_time=stamp,
        parsed_json={"name": "张三", "skills": ["Python"], "years_exp": 3, "self_evaluation": self_eval},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _job(db, user):
    row = JobDescription(
        user_id=user.id,
        title="后端工程师",
        company="示例公司",
        location="上海",
        raw_text="后端工程师 需要 Python",
        is_active=1,
        parsed_json={"title": "后端工程师", "required_skills": ["Python"], "experience_requirement": "3-5年"},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_identical_timestamp_different_content_gives_different_versions(db_session, user):
    a = _resume(db_session, user, FIXED_STAMP, "三年后端经验")
    b = _resume(db_session, user, FIXED_STAMP, "五年高并发经验")

    assert a.update_time == b.update_time
    assert resume_version_of(a) != resume_version_of(b)


def test_touching_only_the_timestamp_keeps_the_cached_score(db_session, user):
    resume = _resume(db_session, user, FIXED_STAMP)
    job = _job(db_session, user)

    first = canonical_match_score(db_session, resume, job, user_id=user.id)
    stored = db_session.query(MatchScore).filter(MatchScore.resume_id == resume.id).one()
    stored.score = 1.5  # sentinel: reading it back proves the row was reused, not recomputed
    db_session.commit()

    resume.update_time = FIXED_STAMP + timedelta(days=2)
    db_session.commit()

    again = canonical_match_score(db_session, resume, job, user_id=user.id)
    assert again["score"] == 1.5
    assert db_session.query(MatchScore).filter(MatchScore.resume_id == resume.id).count() == 1
    assert first["score"] != again["score"]


def test_applying_an_edit_and_reassigning_persists_and_rereports(db_session, user):
    resume = _resume(db_session, user, FIXED_STAMP)
    before = resume_version_of(resume)

    new_parsed, applied, rejected = apply_block_edits(
        resume.parsed_json, [{"block_id": "self_evaluation", "proposed_text": "五年高并发与 RAG 落地"}]
    )
    assert applied and not rejected

    resume.parsed_json = new_parsed
    resume_id = resume.id
    db_session.add(resume)
    db_session.commit()
    db_session.expunge_all()

    fresh = db_session.get(Resume, resume_id)
    assert fresh.parsed_json["self_evaluation"] == "五年高并发与 RAG 落地"
    assert resume_version_of(fresh) != before


def test_in_place_mutation_never_reaches_the_row(db_session, user):
    """The contrast that makes the reassignment in the test above load-bearing."""
    resume = _resume(db_session, user, FIXED_STAMP)

    resume.parsed_json["self_evaluation"] = "只改了内存里的字典"
    resume_id = resume.id
    db_session.add(resume)
    db_session.commit()
    db_session.expunge_all()

    fresh = db_session.get(Resume, resume_id)
    assert fresh.parsed_json["self_evaluation"] == "三年后端经验"
