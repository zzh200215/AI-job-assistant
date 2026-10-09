"""P4（D172）：`POST /interview/sessions/{id}/end` —— 候选人自己收口，不要求还挂着 WebSocket。

这条端点存在的理由是 2026-10-09 现量的四行：开发库 14 场面试里 4 场是**非终态僵尸**——
#1 / #3 `ongoing` 各只推过第一题、最后一条消息停在 2026-06-07，#12 / #13 `created` 从未开始，
四场都没有报告。收口的两条路（WS 的 `end` 消息、每问 30 秒计时器）都只在连接活着时存在，
所以标签页一关就永远出不去。这里钉的是三件事：**ongoing 能交卷**、**created 不被空报告糊脸**、
**已完成的不重复生成**。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.api.interview_rest import router as interview_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.interview_evaluation import InterviewTurnEvaluation
from app.models.interview_session import InterviewSession
from app.models.user import User

QUESTIONS = [
    {"id": 1, "question": "介绍一个你主导的项目。", "category": "project", "ref_answer": "讲清背景与贡献。"},
    {"id": 2, "question": "如何设计可观测的异步任务？", "category": "tech", "ref_answer": "队列、重试、指标。"},
]


def _user(db, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com", password=hash_password("Pass1234!"))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client_for(db_session):
    def _make(user: User) -> TestClient:
        app = FastAPI()
        app.include_router(auth_router, prefix="/auth")
        app.include_router(interview_router, prefix="/interview")

        def _override():
            yield db_session

        app.dependency_overrides[get_db] = _override
        client = TestClient(app)
        client.headers.update(
            {
                "Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'email': user.email, 'username': user.username})}"
            }
        )
        return client

    return _make


def _session(db, user: User, *, status: str, messages: list | None = None) -> InterviewSession:
    row = InterviewSession(
        user_id=user.id,
        interview_type="tech",
        status=status,
        questions=QUESTIONS,
        total_questions=len(QUESTIONS),
        messages=messages if messages is not None else [],
        answered_count=0,
        timeout_count=0,
        evaluation_status="idle",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_ending_an_ongoing_session_writes_a_report_and_leaves_ongoing(db_session, client_for):
    user = _user(db_session, "end_owner")
    client = client_for(user)
    row = _session(
        db_session,
        user,
        status="ongoing",
        messages=[
            {"role": "assistant", "type": "question", "content": "介绍一个你主导的项目。", "metadata": {"round": 1}}
        ],
    )

    response = client.post(f"/interview/sessions/{row.id}/end")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "completed"
    assert body["message"] == "面试已结束，报告已生成"

    db_session.refresh(row)
    assert row.status == "completed"
    assert row.completed_at is not None, "结束时间没写，列表上还是看不出它什么时候收的口"
    assert isinstance(row.evaluation, dict) and row.evaluation, "一题没答也要有兜底报告，不能留空"
    assert [m.get("type") for m in row.messages][-1] == "end"


def test_ending_twice_is_idempotent_and_does_not_stack_end_messages(db_session, client_for):
    user = _user(db_session, "end_twice")
    client = client_for(user)
    row = _session(db_session, user, status="ongoing")

    first = client.post(f"/interview/sessions/{row.id}/end")
    messages_after_first = len(db_session.get(InterviewSession, row.id).messages)
    second = client.post(f"/interview/sessions/{row.id}/end")

    assert first.json()["code"] == 0
    assert second.json()["message"] == "这场面试已经结束"
    db_session.refresh(row)
    assert len(row.messages) == messages_after_first, "第二次结束又往消息里追加了一条"
    assert [m.get("type") for m in row.messages].count("end") == 1


def test_a_session_that_never_started_is_refused_instead_of_getting_an_empty_report(db_session, client_for):
    """`created` 一题都没推过。给它一份"完成"的报告会直接把空数据糊在候选人脸上。"""
    user = _user(db_session, "end_never_started")
    client = client_for(user)
    row = _session(db_session, user, status="created")

    body = client.post(f"/interview/sessions/{row.id}/end").json()
    assert body["code"] != 0
    assert "还没有开始" in body["message"]

    db_session.refresh(row)
    assert row.status == "created"
    assert not row.evaluation, "被拒绝的一次不能顺手写下报告"


def test_you_cannot_end_someone_elses_session(db_session, client_for):
    owner = _user(db_session, "end_real_owner")
    stranger = _user(db_session, "end_stranger")
    row = _session(db_session, owner, status="ongoing")

    body = client_for(stranger).post(f"/interview/sessions/{row.id}/end").json()
    assert body["code"] != 0
    assert "不存在或无权限" in body["message"]
    db_session.refresh(row)
    assert row.status == "ongoing", "别人的调用把这场面试改了状态"


def test_ending_with_an_unfinished_score_does_not_claim_the_report_is_final(db_session, client_for):
    """这一条把 D170 与 D163 接起来：交卷时还有一题在排队，就只能说 processing，不能假装备齐。"""
    user = _user(db_session, "end_with_pending")
    client = client_for(user)
    row = _session(db_session, user, status="ongoing")
    db_session.add(
        InterviewTurnEvaluation(
            session_id=row.id,
            turn_id="q-1",
            question_index=0,
            question="介绍一个你主导的项目。",
            category="project",
            user_answer="我负责过下单与支付的稳定性。",
            status="pending",
        )
    )
    db_session.commit()

    body = client.post(f"/interview/sessions/{row.id}/end").json()
    assert body["code"] == 0

    db_session.refresh(row)
    assert row.status == "completed"
    assert row.evaluation_status == "processing", "还有一题没出分，状态却说自己齐了"
    assert row.evaluation["evaluation_status"] == "processing"


def test_ending_after_a_scored_turn_marks_the_report_completed(db_session, client_for):
    user = _user(db_session, "end_scored")
    client = client_for(user)
    row = _session(db_session, user, status="ongoing")
    db_session.add(
        InterviewTurnEvaluation(
            session_id=row.id,
            turn_id="q-1",
            question_index=0,
            question="介绍一个你主导的项目。",
            category="project",
            user_answer="我把失败率从 4% 降到 0.6%。",
            status="completed",
            completeness=82,
            accuracy=80,
            depth=76,
            expression=78,
            overall_score=80,
            feedback="有量化结果。",
            improvement="补充取舍。",
            evidence={"source": "answer_evaluation_agent"},
        )
    )
    db_session.commit()

    assert client.post(f"/interview/sessions/{row.id}/end").json()["code"] == 0

    db_session.refresh(row)
    assert row.status == "completed"
    assert row.evaluation_status == "completed"
    assert row.evaluation and row.evaluation.get("evaluation_status") == "completed"
