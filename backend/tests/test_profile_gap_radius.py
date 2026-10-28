"""旧报告画像缺口半径：分清"能推回 / 推回也没新弱点 / 推不回"，且脚本真的只读。"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

import scripts.profile_gap_radius as radius
from app.models.history import JobDescription
from app.models.interview_session import InterviewSession


def _report(question: str = "Kafka 的消费语义怎么保证不丢消息？", score: int = 55, required=None) -> dict:
    report = {
        "overall_score": 62,
        "dimension_scores": {"completeness": 80, "accuracy": 75, "depth": 58, "expression": 60},
        "question_evaluations": [
            {"question": question, "overall_score": score, "feedback": "只说了 at-least-once"},
        ],
        "answered_questions": 1,
    }
    if required is not None:
        report["interview_memory"] = {"jd_required_skills": list(required)}
    return report


def _session(
    db,
    *,
    session_id: int,
    user_id: int = 1,
    jd_id: int | None = None,
    status: str = "completed",
    evaluation=None,
):
    row = InterviewSession(
        id=session_id,
        user_id=user_id,
        jd_id=jd_id,
        tenant_id=1,
        interview_type="tech",
        status=status,
        evaluation_status="completed",
        evaluation=evaluation if evaluation is not None else _report(),
        completed_at=datetime(2026, 10, 1),
    )
    db.add(row)
    db.commit()
    return row


def _job(db, *, jd_id: int, required=(), skill_tags=None):
    row = JobDescription(
        id=jd_id,
        user_id=1,
        tenant_id=1,
        title="后端开发工程师",
        company="示例",
        raw_text="",
        parsed_json={"title": "后端开发工程师", "required_skills": list(required)} if required else {},
        skill_tags=list(skill_tags or []),
        source="manual",
        is_active=1,
    )
    db.add(row)
    db.commit()
    return row


def test_recoverable_session_would_gain_a_weakness(db_session):
    _job(db_session, jd_id=10, required=["Kafka"])
    _session(db_session, session_id=1, jd_id=10)

    report = radius.build_report(db_session, 15)
    s = report["summary"]

    assert s["completed"] == 1
    assert s["missing_required"] == 1
    assert s["missing_with_jd"] == 1
    assert s["recoverable"] == 1
    assert s["would_gain_sessions"] == 1
    assert s["would_gain_weaknesses"] == 1
    assert report["detail"][0]["gained"][0]["canonical"] == "kafka"


def test_sessions_that_already_have_required_skills_are_not_radius(db_session):
    _job(db_session, jd_id=11, required=["Kafka"])
    _session(db_session, session_id=2, jd_id=11, evaluation=_report(required=["Kafka"]))

    s = radius.build_report(db_session, 15)["summary"]

    assert s["with_required"] == 1
    assert s["missing_required"] == 0
    assert s["recoverable"] == 0


def test_missing_jd_or_jd_without_skills_is_unrecoverable(db_session):
    _session(db_session, session_id=3, jd_id=None)
    _job(db_session, jd_id=12)
    _session(db_session, session_id=4, jd_id=12)

    s = radius.build_report(db_session, 15)["summary"]

    assert s["missing_required"] == 2
    assert s["unrecoverable_no_jd"] == 1
    assert s["unrecoverable_jd_no_skills"] == 1
    assert s["recoverable"] == 0


def test_skill_tags_are_the_fallback_source(db_session):
    _job(db_session, jd_id=13, skill_tags=["Kafka"])
    _session(db_session, session_id=5, jd_id=13)

    s = radius.build_report(db_session, 15)["summary"]

    assert s["recoverable"] == 1
    assert s["would_gain_weaknesses"] == 1


def test_recovered_skills_without_a_low_score_add_nothing(db_session):
    _job(db_session, jd_id=14, required=["Kafka"])
    _session(
        db_session,
        session_id=6,
        jd_id=14,
        evaluation=_report(question="Kafka 的消费语义怎么保证不丢消息？", score=88),
    )

    s = radius.build_report(db_session, 15)["summary"]

    assert s["recoverable"] == 1
    assert s["recoverable_but_no_new_weakness"] == 1
    assert s["would_gain_sessions"] == 0


def test_recovered_but_unusable_report_is_counted_separately(db_session):
    _job(db_session, jd_id=18, required=["Kafka"])
    _session(
        db_session,
        session_id=11,
        jd_id=18,
        evaluation={"overall_score": 0, "question_evaluations": [], "answered_questions": 0},
    )

    s = radius.build_report(db_session, 15)["summary"]

    assert s["recoverable"] == 1
    assert s["recoverable_no_summary"] == 1
    assert s["would_gain_sessions"] == 0


def test_a_weakness_already_in_the_profile_is_not_counted_twice(db_session):
    _job(db_session, jd_id=15, required=["Kafka"])
    _session(db_session, session_id=7, jd_id=15, evaluation=_report(required=["Kafka"]))
    _session(db_session, session_id=8, jd_id=15)

    s = radius.build_report(db_session, 15)["summary"]

    assert s["would_gain_sessions"] == 0, "画像里已经有 kafka，回推不会新增"
    assert s["recoverable_but_no_new_weakness"] == 1


def test_non_completed_sessions_are_skipped(db_session):
    _job(db_session, jd_id=16, required=["Kafka"])
    _session(db_session, session_id=9, jd_id=16, status="ongoing")

    s = radius.build_report(db_session, 15)["summary"]

    assert s["completed"] == 0
    assert s["missing_required"] == 0


def test_the_radius_script_never_writes(db_session, capsys, monkeypatch):
    _job(db_session, jd_id=17, required=["Kafka"])
    _session(db_session, session_id=10, jd_id=17)

    def _no_write(self, *args, **kwargs):
        raise AssertionError("半径脚本写了库——回填是另一次拍板，这里不许动手")

    monkeypatch.setattr(radius, "SessionLocal", lambda: db_session)
    db_session.autoflush = False
    monkeypatch.setattr(Session, "commit", _no_write)
    monkeypatch.setattr(Session, "flush", _no_write)

    assert radius.main(["--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["would_gain_sessions"] == 1
    assert payload["detail"][0]["session_id"] == 10

    with pytest.raises(AssertionError, match="写了库"):
        db_session.commit()
    with pytest.raises(AssertionError, match="写了库"):
        db_session.flush()
