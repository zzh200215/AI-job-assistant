"""P1 tests for non-blocking interview evaluation and durable evidence."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.interview_rest import router as interview_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.interview_evaluation import InterviewTurnEvaluation
from app.models.interview_session import InterviewSession
from app.models.user import User
from app.services import interview_evaluation_service
from app.services.interview_engine import InterviewEngine
from app.services.interview_evaluation_service import build_memory_snapshot


def _engine(db_session, make_interview_session) -> InterviewEngine:
    session_id = make_interview_session(
        status="created",
        questions=[
            {
                "id": 1,
                "question": "介绍一个你主导的技术项目。",
                "category": "project",
                "ref_answer": "说明背景、方案、个人贡献和量化结果。",
            },
            {
                "id": 2,
                "question": "如何设计可观测的异步任务系统？",
                "category": "tech",
                "ref_answer": "说明队列、重试、指标和告警。",
            },
        ],
    )
    engine = InterviewEngine(session_id)
    engine.db = db_session
    engine.session = db_session.get(InterviewSession, session_id)
    return engine


def test_deferred_evaluation_persists_pending_turn_and_moves_to_next_question(
    db_session, make_interview_session, monkeypatch
):
    engine = _engine(db_session, make_interview_session)
    engine.start()
    submitted = {}
    monkeypatch.setattr(
        "app.services.interview_engine.submit_turn_evaluation",
        lambda session_id, evaluation_id: submitted.update(session_id=session_id, evaluation_id=evaluation_id),
    )

    result = engine.handle_answer("我负责过一个招聘分析服务，重点解决异步稳定性和可观测性。", defer_evaluation=True)

    assert result["type"] == "question"
    assert engine.current_index == 1
    row = db_session.query(InterviewTurnEvaluation).one()
    assert row.status == "pending"
    assert row.turn_id == "q-1"
    assert row.user_answer.startswith("我负责过")
    assert submitted == {"session_id": engine.session_id, "evaluation_id": row.id}
    assert engine.session.evaluation_status == "processing"
    assert any((item.get("metadata") or {}).get("evaluation_pending") for item in engine.session.messages)


def test_duplicate_answer_reuses_pending_turn_record(db_session, make_interview_session):
    """重复作答同一题（同 session+turn）应复用同一行，不撞唯一约束卡死会话（#19）。"""
    session_id = make_interview_session(status="ongoing")

    first = interview_evaluation_service.create_pending_turn_evaluation(
        db_session,
        session_id=session_id,
        turn_id="q-1",
        question_index=0,
        question="第一题",
        category="tech",
        user_answer="第一次回答",
        is_follow_up=False,
    )
    first_id = first.id

    second = interview_evaluation_service.create_pending_turn_evaluation(
        db_session,
        session_id=session_id,
        turn_id="q-1",
        question_index=0,
        question="第一题",
        category="tech",
        user_answer="第二次回答",
        is_follow_up=False,
    )
    assert second.id == first_id  # 复用同一行而非插入新行
    assert second.user_answer == "第二次回答"  # 内容已更新
    assert second.status == "pending"
    rows = db_session.query(InterviewTurnEvaluation).filter(InterviewTurnEvaluation.session_id == session_id).all()
    assert len(rows) == 1


def test_persisted_turn_evaluations_are_the_resume_source_of_truth(db_session, make_interview_session):
    engine = _engine(db_session, make_interview_session)
    db_session.add(
        InterviewTurnEvaluation(
            session_id=engine.session_id,
            turn_id="q-1",
            question_index=0,
            question="介绍一个你主导的技术项目。",
            category="project",
            user_answer="我主导了异步分析服务并将失败率降低。",
            status="completed",
            completeness=84,
            accuracy=82,
            depth=80,
            expression=78,
            overall_score=82,
            feedback="项目描述完整。",
            improvement="补充业务指标。",
            evidence={"source": "answer_evaluation_agent", "answer_excerpt": "我主导了异步分析服务"},
        )
    )
    db_session.commit()

    evaluations = engine._rebuild_evaluations()

    assert len(evaluations) == 1
    assert evaluations[0]["overall_score"] == 82
    assert evaluations[0]["evidence"]["source"] == "answer_evaluation_agent"


def test_memory_snapshot_separates_strength_and_risk_evidence(db_session, make_interview_session):
    engine = _engine(db_session, make_interview_session)
    db_session.add_all(
        [
            InterviewTurnEvaluation(
                session_id=engine.session_id,
                turn_id="q-1",
                question_index=0,
                question="项目题",
                category="project",
                user_answer="详细回答",
                status="completed",
                overall_score=88,
            ),
            InterviewTurnEvaluation(
                session_id=engine.session_id,
                turn_id="q-2",
                question_index=1,
                question="技术题",
                category="tech",
                user_answer="简短回答",
                status="completed",
                overall_score=55,
            ),
        ]
    )
    db_session.commit()

    snapshot = build_memory_snapshot(db_session, engine.session_id)

    assert snapshot["completed_turns"] == 2
    assert snapshot["pending_turns"] == 0
    assert snapshot["covered_categories"] == ["project", "tech"]
    assert snapshot["strengths"][0]["turn_id"] == "q-1"
    assert snapshot["risks"][0]["turn_id"] == "q-2"


def test_turn_evaluation_endpoint_returns_only_the_current_users_session(db_session):
    user = User(username="turn_owner", email="turn_owner@example.com", password=hash_password("TurnPass123!"))
    db_session.add(user)
    db_session.commit()
    session = InterviewSession(user_id=user.id, questions=[], messages=[], evaluation={})
    db_session.add(session)
    db_session.flush()
    db_session.add(
        InterviewTurnEvaluation(
            session_id=session.id,
            turn_id="q-1",
            question_index=0,
            question="测试题",
            category="tech",
            user_answer="测试回答",
            status="completed",
            overall_score=76,
            evidence={"source": "test"},
        )
    )
    db_session.commit()

    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(interview_router, prefix="/interview")

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})

    with TestClient(app) as client:
        response = client.get(
            f"/interview/sessions/{session.id}/evaluations", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"][0]["turn_id"] == "q-1"
    assert data["items"][0]["evidence"] == {"source": "test"}


def test_background_worker_persists_score_evidence_and_memory(db_session, make_interview_session, monkeypatch):
    engine = _engine(db_session, make_interview_session)
    record = InterviewTurnEvaluation(
        session_id=engine.session_id,
        turn_id="q-1",
        question_index=0,
        question="项目题",
        category="project",
        user_answer="我通过队列和指标解决了稳定性问题。",
        status="pending",
    )
    db_session.add(record)
    db_session.commit()
    monkeypatch.setattr(interview_evaluation_service, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    class FakeAgent:
        def run_impl(self, _context):
            return {
                "completeness": 84,
                "accuracy": 82,
                "depth": 80,
                "expression": 78,
                "overall_score": 82,
                "feedback": "项目表达清楚。",
                "improvement": "补充业务收益。",
            }

    monkeypatch.setattr(interview_evaluation_service, "AnswerEvaluationAgent", FakeAgent)

    interview_evaluation_service.process_turn_evaluation(engine.session_id, record.id)

    db_session.refresh(record)
    db_session.refresh(engine.session)
    assert record.status == "completed"
    assert record.evidence["source"] == "answer_evaluation_agent"
    assert engine.session.memory_snapshot["completed_turns"] == 1
    assert any(item["type"] == "evaluation" for item in engine.session.messages)
