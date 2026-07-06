# -*- coding: utf-8 -*-
"""
WebSocket 面试路由
ws://localhost:8000/ws/interview/{session_id}
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import SessionLocal
from app.core.security import decode_access_token
from app.models.interview_session import InterviewSession
from app.services.interview_engine import InterviewEngine
from app.utils.time_helper import utc_now

logger = logging.getLogger(__name__)
router = APIRouter()

_engine_pool: dict[int, InterviewEngine] = {}


def _get_engine(session_id: int) -> InterviewEngine:
    if session_id not in _engine_pool:
        engine = InterviewEngine(session_id)
        engine.init()
        _engine_pool[session_id] = engine
    return _engine_pool[session_id]


def _cleanup_engine(session_id: int):
    if session_id in _engine_pool:
        engine = _engine_pool.pop(session_id)
        engine.cleanup()


def _verify_ws_token(token: str) -> Optional[int]:
    payload = decode_access_token(token)
    if payload:
        return int(payload.get("sub", 0))
    return None


def _payload_from_message(message: dict) -> dict:
    return {
        "type": message.get("type", ""),
        "content": message.get("content", ""),
        "metadata": message.get("metadata", {}),
    }


def _new_server_messages(engine: InterviewEngine, previous_count: int) -> list[dict]:
    messages = (engine.session.messages if engine.session else []) or []
    return [
        item for item in messages[previous_count:]
        if not (item.get("role") == "user" and item.get("type") == "answer")
    ]


async def _emit_engine_messages(
    websocket: WebSocket,
    engine: InterviewEngine,
    previous_count: int,
    fallback: Optional[dict] = None,
):
    emitted = False
    for message in _new_server_messages(engine, previous_count):
        await websocket.send_json(_payload_from_message(message))
        emitted = True
    if not emitted and fallback:
        await websocket.send_json(fallback)


@router.websocket("/ws/interview/{session_id}")
async def interview_websocket(websocket: WebSocket, session_id: int):
    token = ""
    accept_subprotocol: Optional[str] = None
    proto_header = websocket.headers.get("sec-websocket-protocol", "")
    if proto_header:
        parts = [item.strip() for item in proto_header.split(",") if item.strip()]
        if len(parts) >= 2 and parts[0] == "jwt":
            token = parts[1]
            accept_subprotocol = "jwt"
    if not token:
        token = websocket.query_params.get("token", "")

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

    await websocket.accept(subprotocol=accept_subprotocol)
    logger.info("WS connected: session_id=%s user_id=%s", session_id, user_id)

    engine = _get_engine(session_id)
    current_task: Optional[asyncio.Task] = None

    async def timeout_timer(round_num: int):
        await asyncio.sleep(InterviewEngine.TIMEOUT_SECONDS)
        engine._load_session()
        if engine.session and engine.session.status == "ongoing" and engine.current_index == round_num - 1:
            logger.info("Timeout: session=%s round=%s", session_id, round_num)
            before_count = len((engine.session.messages or []))
            result = engine.handle_timeout()
            await _emit_engine_messages(websocket, engine, before_count, fallback=result)
            if result.get("type") == "end":
                _cleanup_engine(session_id)
                await websocket.close(code=1000, reason="interview finished")

    try:
        engine._load_session()
        if engine.session.status == "ongoing":
            result = engine.resume()
            if result:
                await websocket.send_json(result)
        else:
            before_count = len((engine.session.messages or []))
            result = engine.start()
            await _emit_engine_messages(websocket, engine, before_count, fallback=result)

        if result.get("type") == "question":
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

            before_count = len((engine.session.messages or []))

            if msg_type == "answer":
                result = engine.handle_answer(content)
                await _emit_engine_messages(websocket, engine, before_count, fallback=result)

            elif msg_type == "skip":
                engine.save_message({
                    "role": "system",
                    "type": "system",
                    "content": f"第 {engine.current_index + 1} 题已跳过，进入下一题。",
                    "metadata": {"round": engine.current_index + 1},
                    "timestamp": utc_now().isoformat(),
                })
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
                _cleanup_engine(session_id)
                await websocket.close(code=1000, reason="interview finished")
                break

    except WebSocketDisconnect:
        logger.info("WS disconnected: session_id=%s", session_id)
        if current_task and not current_task.done():
            current_task.cancel()
    except Exception as exc:
        logger.error("WS error: session_id=%s error=%s", session_id, exc, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "content": f"服务端内部错误: {str(exc)[:100]}"})
        except Exception:
            pass
        _cleanup_engine(session_id)
