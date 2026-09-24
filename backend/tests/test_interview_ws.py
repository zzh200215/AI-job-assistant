"""面试 WebSocket 的凭据通道与连接期资源（E16）。

两条判据各自都配了反例，防止"门看着绿其实空转"：
- 凭据只认 `Sec-WebSocket-Protocol: jwt,<token>`。**同一枚有效 token** 从 `?token=` 进来必须被拒
  ——否则"拒 query 串"用假 token 也能过，什么也没证明。
- 引擎按连接持有：连接期间能在 `_active_engines` 里看到它、`engine.db` 是开着的；客户端关闭之后
  两者都必须消失。改动前这两句都会红（旧代码把引擎永久留在进程级 `_engine_pool` 里，
  只有"正常结束/异常"才清，而**关标签页走的是 WebSocketDisconnect**）。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import interview_ws
from app.core.config import settings
from app.core.security import create_access_token
from app.models.interview_session import InterviewSession
from app.services.interview_engine import InterviewEngine

AUTH_FAILED = 4001
FORBIDDEN = 4003
NOT_FOUND = 4004
FINISHED = 4000
FULL = 4005


@pytest.fixture
def ws_client(db_session, monkeypatch):
    """把 WS 与引擎的 `SessionLocal` 都指到测试事务那条连接。

    `conftest` 把 `DATABASE_URL` 设成 `sqlite:///:memory:`，而内存 SQLite **每条连接都是一个新空库**；
    不这样接的话，处理函数里 `db.get(...)` 永远查不到测试建的行，认证之外的分支全都白测。
    """
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.get_bind())
    monkeypatch.setattr(interview_ws, "SessionLocal", factory)
    monkeypatch.setattr("app.services.interview_engine.SessionLocal", factory)
    app = FastAPI()
    app.include_router(interview_ws.router)
    with TestClient(app) as client:
        yield client


def _token_for(user) -> str:
    return create_access_token({"sub": str(user.id)})


def _make_session(db_session, user, status="ongoing") -> int:
    session = InterviewSession(
        user_id=user.id,
        tenant_id=1,
        status=status,
        interview_type="tech",
        questions=[{"question": f"Q{i}"} for i in range(1, 4)],
        messages=[],
        evaluation={},
        answered_count=1 if status == "ongoing" else 0,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session.id


def _close_code_of(client, url, subprotocols=None) -> int:
    """连一次，拿服务端在 accept 之前关连接的 code。"""
    connect = client.websocket_connect(url, subprotocols=subprotocols or [])
    with pytest.raises(WebSocketDisconnect) as info, connect:
        pass
    return info.value.code


def test_token_in_query_string_is_refused_even_when_valid(ws_client, normal_user, db_session):
    sid = _make_session(db_session, normal_user)
    token = _token_for(normal_user)
    assert _close_code_of(ws_client, f"/ws/interview/{sid}?token={token}") == AUTH_FAILED


def test_same_token_via_subprotocol_gets_past_auth(ws_client, normal_user, db_session):
    """对照组：同一枚 token 走子协议就不停在 4001，而是走到"会话不存在"（4004）。"""
    token = _token_for(normal_user)
    code = _close_code_of(ws_client, "/ws/interview/999999", ["jwt", token])
    assert code == NOT_FOUND


def test_anonymous_and_garbage_credentials_are_refused(ws_client, normal_user, db_session):
    sid = _make_session(db_session, normal_user)
    assert _close_code_of(ws_client, f"/ws/interview/{sid}") == AUTH_FAILED
    assert _close_code_of(ws_client, f"/ws/interview/{sid}", ["jwt", "not-a-jwt"]) == AUTH_FAILED


def test_other_users_session_is_refused(ws_client, normal_user, admin_user, db_session):
    """`_verify_ws_token` 只看签名；绑定到本人会话靠 user_id 比对。"""
    sid = _make_session(db_session, admin_user)
    assert _close_code_of(ws_client, f"/ws/interview/{sid}", ["jwt", _token_for(normal_user)]) == FORBIDDEN


def test_completed_session_is_refused(ws_client, normal_user, db_session):
    sid = _make_session(db_session, normal_user, status="completed")
    assert _close_code_of(ws_client, f"/ws/interview/{sid}", ["jwt", _token_for(normal_user)]) == FINISHED


def test_capacity_cap_refuses_new_connections(ws_client, normal_user, db_session, monkeypatch):
    sid = _make_session(db_session, normal_user)
    monkeypatch.setattr(settings, "WS_MAX_LIVE_INTERVIEWS", 0)
    assert _close_code_of(ws_client, f"/ws/interview/{sid}", ["jwt", _token_for(normal_user)]) == FULL


def _wait_until(predicate, timeout=3.0) -> bool:
    """等到条件成立，超时返回 False（不 sleep 一下就断言：服务端 `finally` 跑在 portal 线程上）。"""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_engine_is_released_when_the_client_disconnects(ws_client, normal_user, db_session, monkeypatch):
    """这条就是"每放弃一场面试永久漏一个开着的 Session"那半边。"""
    sid = _make_session(db_session, normal_user)

    monkeypatch.setattr(InterviewEngine, "resume", lambda self: None)
    monkeypatch.setattr(
        InterviewEngine,
        "next_question",
        lambda self: {"type": "question", "content": "Q1", "metadata": {"round": 1}},
    )

    assert interview_ws.live_interview_count() == 0
    with ws_client.websocket_connect(f"/ws/interview/{sid}", subprotocols=["jwt", _token_for(normal_user)]) as ws:
        assert ws.receive_json()["type"] == "question"
        assert interview_ws.live_interview_count() == 1
        engine = next(iter(interview_ws._active_engines))
        assert engine.db is not None, "引擎还没拿到 DB 会话，说明这条连接没真的走通"

    released = _wait_until(lambda: interview_ws.live_interview_count() == 0)
    assert released, "客户端断开后连接仍占着在途名额（旧实现正是这样：_engine_pool 只在结束/异常时清）"
    assert engine.db is None, "cleanup() 没跑：那个 Session（以及它占的那根连接）永久留在进程里"


def test_two_connections_to_one_session_do_not_share_one_engine(ws_client, normal_user, db_session, monkeypatch):
    """旧实现按 session_id 共享同一个可变对象：两个标签页会互相踩 `current_index`。"""
    sid = _make_session(db_session, normal_user)
    monkeypatch.setattr(InterviewEngine, "resume", lambda self: None)
    monkeypatch.setattr(
        InterviewEngine,
        "next_question",
        lambda self: {"type": "question", "content": "Q1", "metadata": {"round": 1}},
    )
    token = _token_for(normal_user)

    url = f"/ws/interview/{sid}"
    first_conn = ws_client.websocket_connect(url, subprotocols=["jwt", token])
    second_conn = ws_client.websocket_connect(url, subprotocols=["jwt", token])
    with first_conn as first, second_conn as second:
        first.receive_json()
        second.receive_json()
        engines = list(interview_ws._active_engines)
        assert len(engines) == 2, "两条连接共用了同一个引擎"
        assert engines[0] is not engines[1]
