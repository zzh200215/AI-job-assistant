"""面试 WebSocket 的凭据通道与连接期资源（E16）。

两条判据各自都配了反例，防止"门看着绿其实空转"：
- 凭据只认 `Sec-WebSocket-Protocol: jwt,<token>`。**同一枚有效 token** 从 `?token=` 进来必须被拒
  ——否则"拒 query 串"用假 token 也能过，什么也没证明。
- 引擎按连接持有：连接期间能在 `_active_engines` 里看到它、`engine.db` 是开着的；客户端关闭之后
  两者都必须消失。改动前这两句都会红（旧代码把引擎永久留在进程级 `_engine_pool` 里，
  只有"正常结束/异常"才清，而**关标签页走的是 WebSocketDisconnect**）。
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import interview_ws
from app.core.config import settings
from app.core.security import create_access_token
from app.models.interview_evaluation import InterviewTurnEvaluation
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
    """这条就是"每放弃一场面试永久漏一个开着的 Session"那半边。

    D213 之后这条连接**根本不开 Session**（读也走 worker），所以"漏一个开着的 Session"变成结构上
    不可能；`_active_engines` 里留的只是容量记账用的引擎对象。断言因此从"断开后那个 db 被关掉了"
    改成"全程就没有 db"——后者更强：只要有人在循环线程里再加一次库访问，这条就红。
    """
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
        assert engine.db is None, "循环线程又开 Session 了：那条读事务会把一根池连接占到 commit/rollback 为止"

    # 谓词里两个条件一起等：`finally` 中 `discard()` 与 `cleanup()` 之间没有 await，但线程可以在
    # 两条语句之间被换下去。D212 之后这条曾单独红过一次（先看见 count==0、再读 db 还在）就是这个缝。
    released = _wait_until(lambda: interview_ws.live_interview_count() == 0 and engine.db is None)
    assert released, "客户端断开后连接仍占着在途名额（旧实现正是这样：_engine_pool 只在结束/异常时清）"


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


# ------------------------------------------------------------------ D212：模型那一步不能在事件循环上

MODEL_CAPABLE_STEPS = ("finish", "handle_timeout", "handle_answer", "next_question", "start")


def _bare_engine_calls(source: str) -> list[str]:
    """连接那只引擎上、会同步走到模型的裸调用。

    `resume()` / `_load_session()` / `init()` / `cleanup()` 不在名单里：它们只读库或纯内存，
    走不到 `_generate_report`。判据认的是 `engine.<name>(` 这个字面形态——每一步现在都必须
    写成 `_step(session_id, "<name>")`，所以退化一次就会红。
    """
    return sorted(name for name in MODEL_CAPABLE_STEPS if f"engine.{name}(" in source)


def test_ws_source_has_no_bare_model_capable_engine_call():
    src = Path("app/api/interview_ws.py").read_text(encoding="utf-8")
    assert _bare_engine_calls(src) == [], "这些步骤会同步等模型（`chat_json` 最坏 364.5s），必须在 worker 线程里跑"
    # 反向证据：这台判据认得退化写法，不是一眼看上去就空的绿灯
    assert _bare_engine_calls("result = engine.finish()\nresult = engine.handle_timeout()") == [
        "finish",
        "handle_timeout",
    ]


def test_the_model_capable_step_runs_off_the_event_loop_thread(ws_client, normal_user, db_session, monkeypatch):
    sid = _make_session(db_session, normal_user)

    loop_threads: list[int] = []
    step_threads: dict[str, list[int]] = {"next_question": [], "finish": []}

    original_emit = interview_ws._emit_snapshot

    async def spy_emit(websocket, new_messages, fallback=None):
        # 这一步回到循环线程 —— 拿它当"事件循环是谁"的参照（D213 之后连接阶段也不再碰库，
        # 原来借 `InterviewEngine.init` 取循环线程 ident 的做法没有落点了）
        loop_threads.append(threading.get_ident())
        return await original_emit(websocket, new_messages, fallback)

    def spy(name):
        def impl(self):
            step_threads[name].append(threading.get_ident())
            if name == "next_question":
                return {"type": "question", "content": "Q1", "metadata": {"round": 1}}
            return {"type": "end", "content": "结束", "metadata": {}}

        return impl

    monkeypatch.setattr(interview_ws, "_emit_snapshot", spy_emit)
    monkeypatch.setattr(InterviewEngine, "resume", lambda self: None)
    monkeypatch.setattr(InterviewEngine, "next_question", spy("next_question"))
    monkeypatch.setattr(InterviewEngine, "finish", spy("finish"))

    with ws_client.websocket_connect(f"/ws/interview/{sid}", subprotocols=["jwt", _token_for(normal_user)]) as ws:
        assert ws.receive_json()["type"] == "question"
        ws.send_json({"type": "end"})
        assert ws.receive_json()["type"] == "end"

    assert loop_threads and step_threads["next_question"] and step_threads["finish"], "探针没跑到"
    loop_thread = loop_threads[0]
    assert step_threads["finish"][-1] != loop_thread, "收尾那一步还跑在事件循环线程上：一发模型调用会卡住整个进程"
    assert step_threads["next_question"][-1] != loop_thread, "出题那一步（题库耗尽会走 `_finish`）还跑在循环线程上"


def _ai_report_fake(monkeypatch, calls):
    def fake_chat_json(prompt, **kwargs):
        calls.append(prompt)
        return {
            "strengths": ["项目主导经验"],
            "weaknesses": ["量化指标不足"],
            "improvement_suggestions": ["补充业务结果"],
            "overall_evaluation": "可做下一轮",
            "hiring_recommendation": "可进入下一轮",
            "dimensions": {},
        }

    monkeypatch.setattr("app.agents.answer_evaluation_agent.chat_json", fake_chat_json)


def test_the_off_loop_finish_still_builds_the_ai_report(ws_client, normal_user, db_session, monkeypatch):
    """新开引擎的那条真风险：`_generate_report` 吃的是内存里的 `self.evaluations`
    （`interview_engine.py:373`），worker 侧不先 `resume()` 就会**静默**把 AI 报告换成兜底报告。"""
    sid = _make_session(db_session, normal_user)
    db_session.add(
        InterviewTurnEvaluation(
            session_id=sid,
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

    calls: list[str] = []
    _ai_report_fake(monkeypatch, calls)

    new_messages, payload = interview_ws._engine_steps_snapshot(sid, [("finish", (), {})])

    report = payload["metadata"]
    assert calls, "worker 那侧没打到模型 —— 说明落库的工作态没被重建起来"
    assert report["answered_questions"] == 1
    assert report["hiring_recommendation"] == "可进入下一轮"
    assert [item["type"] for item in new_messages] == ["end"], "这一步新增的消息没带回来，客户端就看不到收尾"


def test_a_session_without_evaluations_still_takes_the_fallback_and_pays_nothing(
    ws_client, normal_user, db_session, monkeypatch
):
    """反证：没有已完成评分时，那条链本来就不调模型——新引擎不该改变这个行为。"""
    sid = _make_session(db_session, normal_user)
    calls: list[str] = []
    _ai_report_fake(monkeypatch, calls)

    _, payload = interview_ws._engine_steps_snapshot(sid, [("finish", (), {})])

    assert calls == []
    assert payload["metadata"]["answered_questions"] == 0
    assert payload["metadata"]["improvement_suggestions"] == ["请至少完成一道题后再查看复盘报告。"]


def test_the_loop_thread_never_opens_a_db_session_while_the_interview_runs(
    ws_client, normal_user, db_session, monkeypatch
):
    """D212 自己引入的那条容量回归，得有腿盯着。

    机制是实测的：SQLAlchemy 的**读事务**会把那根连接一路握到 commit/rollback——真 MySQL 池上
    读完不提交 `checkedout=1`，`rollback()` 之后回到 `0`。D212 之后循环线程不再 commit，所以只要
    它还开一次 Session，每条在途面试就长期钉住一根池连接，而 `WS_MAX_LIVE_INTERVIEWS=12` 对上的
    正是 `DB_POOL_SIZE + DB_MAX_OVERFLOW = 10 + 10` 那口池。修法是让循环线程**根本不开 Session**
    （连接阶段的读也走 worker），所以这条断言的是"全程 `engine.db is None`"。

    这里不打桩：走的是真 `start`/`next_question`/`skip`，只有这条路才会去碰库，才测得出"没碰"。
    """
    sid = _make_session(db_session, normal_user)

    with ws_client.websocket_connect(f"/ws/interview/{sid}", subprotocols=["jwt", _token_for(normal_user)]) as ws:
        first = ws.receive_json()
        assert first["type"] == "question", f"没拿到第一题：{first}"
        engine = next(iter(interview_ws._active_engines))
        assert engine.db is None, "循环线程开了 Session：它会替这条面试长期占着一根池连接"

        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"

        ws.send_json({"type": "skip"})
        assert ws.receive_json()["type"] == "system"  # 那条"已跳过"的消息必须还在
        assert ws.receive_json()["type"] == "question"

        assert engine.db is None, "跑完 skip（两步同一个 worker）之后循环线程又开了 Session"
