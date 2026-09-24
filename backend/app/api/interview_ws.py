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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.core.tenant_context import TenantContext, reset_current_tenant, set_current_tenant
from app.models.interview_session import InterviewSession
from app.services.interview_engine import InterviewEngine
from app.utils.time_helper import utc_now

logger = logging.getLogger(__name__)
router = APIRouter()

# 只为容量上限服务：每条在途连接一个引擎，断开即移除。数量可从 `live_interview_count()` 读到。
_active_engines: set[InterviewEngine] = set()


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


def _new_server_messages(engine: InterviewEngine, previous_count: int) -> list[dict]:
    messages = (engine.session.messages if engine.session else []) or []
    return [
        item for item in messages[previous_count:] if not (item.get("role") == "user" and item.get("type") == "answer")
    ]


async def _emit_engine_messages(
    websocket: WebSocket,
    engine: InterviewEngine,
    previous_count: int,
    fallback: dict | None = None,
):
    emitted = False
    for message in _new_server_messages(engine, previous_count):
        await websocket.send_json(_payload_from_message(message))
        emitted = True
    if not emitted and fallback:
        await websocket.send_json(fallback)


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

    db = SessionLocal()
    try:
        session = db.get(InterviewSession, session_id)
        if not session:
            await websocket.close(code=4004, reason="面试会话不存在")
            return
        if session.user_id != user_id:
            await websocket.close(code=4003, reason="无权访问此面试")
            return
        if session.status == "completed":
            await websocket.close(code=4000, reason="面试已结束")
            return
    finally:
        db.close()

    if live_interview_count() >= settings.WS_MAX_LIVE_INTERVIEWS:
        logger.warning("面试 WS 容量已满：%s 条在途，拒绝 session_id=%s", live_interview_count(), session_id)
        await websocket.close(code=4005, reason="并发面试已达上限")
        return

    # WS 不经过 HTTP 租户中间件（中间件仅 HTTP scope），手动注入会话所属租户上下文，
    # 保证后续评分规则读取 / tenant_filter / 知识检索都落在正确租户上。
    tenant_token = set_current_tenant(TenantContext(tenant_id=session.tenant_id or 1))
    try:
        return await _handle_ws_loop(websocket, session_id, session, accept_subprotocol)
    finally:
        reset_current_tenant(tenant_token)


async def _handle_ws_loop(
    websocket: WebSocket,
    session_id: int,
    session: InterviewSession,
    accept_subprotocol: str | None,
):
    await websocket.accept(subprotocol=accept_subprotocol)
    logger.info("WS connected: session_id=%s user_id=%s", session_id, session.user_id)

    # 引擎按连接建：工作态全部能从落库的消息里推断（见模块 docstring），进程内不留长期对象。
    engine = InterviewEngine(session_id)
    _active_engines.add(engine)
    engine.init()
    current_task: asyncio.Task | None = None

    async def timeout_timer(round_num: int):
        await asyncio.sleep(InterviewEngine.TIMEOUT_SECONDS)
        engine._load_session()
        if engine.session and engine.session.status == "ongoing" and engine.current_index == round_num - 1:
            logger.info("Timeout: session=%s round=%s", session_id, round_num)
            before_count = len(engine.session.messages or [])
            result = engine.handle_timeout()
            await _emit_engine_messages(websocket, engine, before_count, fallback=result)
            if result.get("type") == "end":
                await websocket.close(code=1000, reason="interview finished")

    try:
        engine._load_session()
        result: dict | None = None
        if engine.session.status == "ongoing":
            result = engine.resume()
            if result:
                await websocket.send_json(result)
            else:
                before_count = len(engine.session.messages or [])
                result = engine.next_question()
                await _emit_engine_messages(websocket, engine, before_count, fallback=result)
        else:
            before_count = len(engine.session.messages or [])
            result = engine.start()
            await _emit_engine_messages(websocket, engine, before_count, fallback=result)

        if result and result.get("type") == "question":
            current_task = asyncio.create_task(timeout_timer(result["metadata"]["round"]))

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

            before_count = len(engine.session.messages or [])

            if msg_type == "answer":
                result = engine.handle_answer(content, defer_evaluation=True)
                await _emit_engine_messages(websocket, engine, before_count, fallback=result)

            elif msg_type == "skip":
                engine.save_message(
                    {
                        "role": "system",
                        "type": "system",
                        "content": f"第 {engine.current_index + 1} 题已跳过，进入下一题。",
                        "metadata": {"round": engine.current_index + 1},
                        "timestamp": utc_now().isoformat(),
                    }
                )
                result = engine.next_question()
                await _emit_engine_messages(websocket, engine, before_count, fallback=result)

            elif msg_type == "end":
                result = engine.finish()
                await _emit_engine_messages(websocket, engine, before_count, fallback=result)

            else:
                await websocket.send_json({"type": "error", "content": f"未知消息类型: {msg_type}"})
                continue

            if result.get("type") == "question":
                current_task = asyncio.create_task(timeout_timer(result["metadata"]["round"]))
            elif result.get("type") == "end":
                await websocket.close(code=1000, reason="interview finished")
                break

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
