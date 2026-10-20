from app.api.interview_rest import (
    _fallback_questions,
    _normalize_generated_questions,
    list_bank_types,
)
from app.core.config import settings
from app.models.interview_session import InterviewSession
from app.services.interview_config_service import max_questions
from app.services.interview_engine import InterviewEngine


def test_max_questions_clamps_to_allowed_range(monkeypatch):
    for raw, expected in ((0, 1), (1, 1), (10, 10), (20, 20), (21, 20), (100, 20)):
        monkeypatch.setattr(settings, "INTERVIEW_MAX_QUESTIONS", raw)
        assert max_questions() == expected


def test_fallback_and_generated_questions_respect_the_configured_limit(monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_MAX_QUESTIONS", 3)

    fallback = _fallback_questions("后端工程师", ["Python"], "tech")
    assert len(fallback) == 3

    raw = {"tech": [{"q": f"模型题{i}"} for i in range(1, 6)]}
    merged = _normalize_generated_questions(raw, fallback)
    assert len(merged) == 3
    assert [item["id"] for item in merged] == [1, 2, 3]


def test_config_types_route_exposes_max_questions(db_session, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_MAX_QUESTIONS", 7)

    body = list_bank_types(db=db_session)

    assert body["code"] == 0
    assert body["data"]["max_questions"] == 7
    assert body["data"]["items"]


def test_engine_instance_reads_the_configured_limit(db_session, make_interview_session, monkeypatch):
    monkeypatch.setattr(settings, "INTERVIEW_MAX_QUESTIONS", 5)
    session_id = make_interview_session(
        status="created",
        questions=[{"question": f"Q{i}"} for i in range(1, 9)],
    )
    engine = InterviewEngine(session_id)
    engine.db = db_session
    engine.session = db_session.get(InterviewSession, session_id)

    assert engine.MAX_QUESTIONS == 5

    payload = engine.start()

    assert engine.question_count == 5
    assert payload["metadata"]["total"] == 5
