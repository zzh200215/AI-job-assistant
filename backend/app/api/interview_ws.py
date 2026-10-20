"""
WebSocket 面试路由
wss://<host>/ws/interview/{session_id}

凭据只接受 `Sec-WebSocket-Protocol: jwt,<token>`（浏览器侧 `new WebSocket(url, ['jwt', token])`）。
**不接受 `?token=`**：那条路径会让长期 JWT 落进 nginx/网关访问日志与浏览器历史，
而仓库自带的客户端从来没用过它（`frontend/src/api/interview.js` 用的就是子协议）。

引擎按**连接**持有而不是按 session_id 放进进程级字典：面试引擎的全部工作态都是从落库的消息里
推断的（`_infer_current_index` / `_infer_start_time` / `resume()`），所以进程内不存也必须存；
原来那份 `_engine_pool` 只在"正常结束/异常"时清理，**关标签页走的是 WebSocketDisconnect**，
于是每场被放弃的面试都永久留下一个引擎 + 一个打开的 `SessionLocal()`。
"""

import asyncio
import contextlib
import json
import logging

import anyio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.interview_session import InterviewSession
from app.services.interview_config_service import TIMEOUT_FLOOR_SECONDS
from app.services.interview_engine import InterviewEngine
from app.utils.time_helper import utc_now

logger = logging.getLogger(__name__)
router = APIRouter()

# 只为容量上限服务：每条在途连接一个引擎，断开即移除。数量可从 `live_interview_count()` 读到。
_active_engines: set[InterviewEngine] = set()


def timeout_for_payload(payload: dict | None) -> int | None:
    """这一题该给多少秒。不是题的消息返回 None（不给它起定时器）。

    三种拿不到数的情形都落到**下限 45**，不是 0、也不是老那个 30：
    本次改动之前落库的会话没有这个字段；脏值（0、负数、字符串）可能来自手改的 JSON 列。
    睡 0 秒意味着一出题就判超时——那比 30 秒更坏。
    """
    if not payload or payload.get("type") != "question":
        return None
    raw = (payload.get("metadata") or {}).get("timeout_seconds")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return TIMEOUT_FLOOR_SECONDS
    return raw


def live_interview_count() -> int:
    return len(_active_engines)


def _verify_ws_token(token: str) -> int | None:
    payload = decode_access_token(token)
    if payload:
        return int(payload.get("sub", 0))
    return None


def _read_subprotocol_token(websocket: WebSocket) -> tuple[str, str | None]:
    """从子协议头里取 (token, 要回给客户端的子协议)。"""
    proto_header = websocket.headers.get("sec-websocket-protocol", "")
    parts = [item.strip() for item in proto_header.split(",") if item.strip()]
    if len(parts) >= 2 and parts[0] == "jwt":
        return parts[1], "jwt"
    return "", None


def _payload_from_message(message: dict) -> dict:
    return {
        "type": message.get("type", ""),
        "content": message.get("content", ""),
        "metadata": message.get("metadata", {}),
    }


def _engine_steps_snapshot(session_id: int, plan: list[tuple[str, tuple, dict]]) -> tuple[list[dict], object]:
    """在**别的线程**里跑完一组引擎步骤，带回"这一组新增的服务端消息"与最后一步的 payload。

    为什么必须在别的线程（D211 现取的链）：`finish` / `handle_timeout` / `next_question`（题库耗尽
    那支）/ `handle_answer`（它自己就调 `next_question`）都会走到 `_finish` → `_generate_report` →
    `FinalReportAgent.run_impl` → `chat_json`，那是同步的 `requests`，最坏 364.5s（D189 的公式）。
    这些调用原来直接写在 `async def` 的处理函数里 ⇒ 卡的不是这条连接，是**整个进程的事件循环**。

    为什么新建引擎而不是把连接上那只递过去：SQLAlchemy 的 Session 不跨线程，而
    `InterviewEngine.db` 是 `_load_session` 懒建后挂在实例上的（`interview_engine.py:55-56`）。

    为什么第一步必须是 `resume()`：`_generate_report` 吃的是 `self.evaluations`
    （`interview_engine.py:373`），内存里那份为空就会被静默换成兜底报告。`resume()` 正是本模块
    docstring 写的那条既有机制——工作态全部从落库推断（含超时那几项，`:611-629`）。
    """
    worker = InterviewEngine(session_id)
    worker.resume()
    before = len(worker.session.messages or []) if worker.session else 0

    result: object = None
    for method, args, kwargs in plan:
        result = getattr(worker, method)(*args, **kwargs)

    messages = (worker.session.messages if worker.session else []) or []
    new_messages = [
        item for item in messages[before:] if not (item.get("role") == "user" and item.get("type") == "answer")
    ]
    worker.cleanup()
    return new_messages, result


async def _step(session_id: int, method: str, *args, **kwargs) -> tuple[list[dict], dict]:
    return await anyio.to_thread.run_sync(_engine_steps_snapshot, session_id, [(method, args, kwargs)])


async def _emit_snapshot(websocket: WebSocket, new_messages: list[dict], fallback: dict | None) -> None:
    emitted = False
    for message in new_messages:
        await websocket.send_json(_payload_from_message(message))
        emitted = True
    if not emitted and fallback:
        await websocket.send_json(fallback)


def _session_owner_and_status(session_id: int) -> tuple[int | None, str | None]:
    """建连阶段那一次读：找不到就返回 `(None, None)`。

    D213 把循环体内的每一步都搬进了 worker，但**连接阶段**这两次读还留在 `async def` 里——
    WebSocket 处理器必须保持协程，所以这里整段搬出去（D219 量的那一类：一条协程路由在事件循环
    线程上做一次数据库往返，同期所有请求都得等它）。
    """
    db = SessionLocal()
    try:
        session = db.get(InterviewSession, session_id)
        if session is None:
            return None, None
        # 标量在这条 Session 关掉之前就取出来：往下要传出去的是值，不是一只 detached ORM 对象
        # ——那东西以后被 worker 线程碰一下就 DetachedInstanceError。
        return session.user_id, session.status
    finally:
        db.close()


@router.websocket("/ws/interview/{session_id}")
async def interview_websocket(websocket: WebSocket, session_id: int):
    token, accept_subprotocol = _read_subprotocol_token(websocket)
    if not token and websocket.query_params.get("token"):
        # 只记录"有人这么试过"，绝不把 token 本身写进日志——那正是这条路径要防的事。
        logger.warning("拒绝面试 WS：token 走的是 URL 查询串（仅接受 Sec-WebSocket-Protocol: jwt,<token>）")
    elif not token:
        logger.info("拒绝面试 WS：未提供凭据")

    user_id = _verify_ws_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="认证失败: 无效 Token")
        return

    owner_id, status = await anyio.to_thread.run_sync(_session_owner_and_status, session_id)
    if owner_id is None:
        await websocket.close(code=4004, reason="面试会话不存在")
        return
    if owner_id != user_id:
        await websocket.close(code=4003, reason="无权访问此面试")
        return
    if status == "completed":
        await websocket.close(code=4000, reason="面试已结束")
        return

    if live_interview_count() >= settings.WS_MAX_LIVE_INTERVIEWS:
        logger.warning("面试 WS 容量已满：%s 条在途，拒绝 session_id=%s", live_interview_count(), session_id)
        await websocket.close(code=4005, reason="并发面试已达上限")
        return

    return await _handle_ws_loop(websocket, session_id, owner_id, status, accept_subprotocol)


async def _handle_ws_loop(
    websocket: WebSocket,
    session_id: int,
    owner_id: int,
    status: str,
    accept_subprotocol: str | None,
):
    await websocket.accept(subprotocol=accept_subprotocol)
    logger.info("WS connected: session_id=%s user_id=%s", session_id, owner_id)

    # 引擎按连接建，但**这只对象从不开 Session**：读也在 worker 线程里做（见
    # `_engine_steps_snapshot`）。原因是 D212 之后循环线程不再 commit，而 SQLAlchemy 的读事务会把
    # 那根连接一路握到 commit/rollback——真 MySQL 池实测：读完不提交 `checkedout=1`，`rollback()`
    # 之后回到 `0`。那样每条在途面试都长期钉住一根池连接，而 `WS_MAX_LIVE_INTERVIEWS=12` 对上的
    # 正是 `DB_POOL_SIZE + DB_MAX_OVERFLOW = 10 + 10`（config.py:76-77、96）。连接阶段需要的
    # `status` 已经在认证那一步读过一次并在那里归还了连接，这里只接标量。
    engine = InterviewEngine(session_id)
    _active_engines.add(engine)
    current_task: asyncio.Task | None = None
    # "这是第几题"从**发给客户端的那一问**里取：循环线程不碰库，读不到 worker 刚推进到的位置。
    current_round = 0

    def _arm(payload: dict | None) -> None:
        nonlocal current_task, current_round
        budget = timeout_for_payload(payload)
        if budget is None:
            return
        round_num = int((payload.get("metadata") or {}).get("round") or 0)
        if round_num:
            current_round = round_num
        if current_task and not current_task.done():
            current_task.cancel()
        current_task = asyncio.create_task(timeout_timer(current_round, budget))

    async def timeout_timer(round_num: int, budget: int):
        # 原来睡的是类常量 `InterviewEngine.TIMEOUT_SECONDS`（全场 30 秒），
        # 现在睡的是**这一题**随消息带下来的预算：技术题/项目题 120、场景题 90、通用题 45。
        await asyncio.sleep(budget)
        # 守卫原来读连接这只引擎的 status/current_index，而它看不到 worker 的新写入；
        # 所以这一步的读也交给 worker——`resume()` 从落库推断，`_get_state()` 就是那份推断结果。
        _, state = await _step(session_id, "_get_state")
        if state.get("status") != "ongoing" or state.get("current_index") != round_num - 1:
            return
        logger.info("Timeout: session=%s round=%s", session_id, round_num)
        new_messages, result = await _step(session_id, "handle_timeout")
        await _emit_snapshot(websocket, new_messages, result)
        if result.get("type") == "end":
            await websocket.close(code=1000, reason="interview finished")

    try:
        result: dict | None = None
        if status == "ongoing":
            _, result = await _step(session_id, "resume")
            if result and (result.get("metadata") or {}).get("resume_expired"):
                # 断线期间这一题的预算已经走完：不重发题目，直接按超时处理并推进。
                new_messages, result = await _step(session_id, "handle_timeout")
                await _emit_snapshot(websocket, new_messages, result)
            elif result:
                await websocket.send_json(result)
            else:
                new_messages, result = await _step(session_id, "next_question")
                await _emit_snapshot(websocket, new_messages, result)
        else:
            new_messages, result = await _step(session_id, "start")
            await _emit_snapshot(websocket, new_messages, result)

        _arm(result)

        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "消息格式错误，需要 JSON"})
                continue

            msg_type = data.get("type", "")
            content = data.get("content", "")

            if current_task and not current_task.done():
                current_task.cancel()
                current_task = None

            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "content": ""})
                continue

            if msg_type == "answer":
                new_messages, result = await _step(session_id, "handle_answer", content, defer_evaluation=True)
                await _emit_snapshot(websocket, new_messages, result)

            elif msg_type == "skip":
                skip_message = {
                    "role": "system",
                    "type": "system",
                    "content": f"第 {current_round} 题已跳过，进入下一题。",
                    "metadata": {"round": current_round},
                    "timestamp": utc_now().isoformat(),
                }
                # 这两步必须在**同一个** worker 引擎里连着跑：拆成两次 handoff 的话，第二次的
                # `before` 已经包含这条跳过消息，候选人就再也看不到它了。
                new_messages, result = await anyio.to_thread.run_sync(
                    _engine_steps_snapshot,
                    session_id,
                    [("save_message", (skip_message,), {}), ("next_question", (), {})],
                )
                await _emit_snapshot(websocket, new_messages, result)

            elif msg_type == "end":
                new_messages, result = await _step(session_id, "finish")
                await _emit_snapshot(websocket, new_messages, result)

            else:
                await websocket.send_json({"type": "error", "content": f"未知消息类型: {msg_type}"})
                continue

            if result.get("type") == "end":
                await websocket.close(code=1000, reason="interview finished")
                break
            _arm(result)

    except WebSocketDisconnect:
        logger.info("WS disconnected: session_id=%s", session_id)
    except Exception as exc:
        logger.error("WS error: session_id=%s error=%s", session_id, exc, exc_info=True)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "content": f"服务端内部错误: {str(exc)[:100]}"})
    finally:
        # 先停掉计时任务再关引擎：计时器醒来第一件事就是 `_load_session()`，
        # 那时 db 已被置 None，它会再开一个 Session —— 于是"清理"反而制造新的泄漏。
        if current_task and not current_task.done():
            current_task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await current_task
        _active_engines.discard(engine)
        engine.cleanup()
