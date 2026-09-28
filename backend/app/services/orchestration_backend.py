"""Orchestration backend abstraction.

默认使用线程池保持现有行为；当 `ORCHESTRATION_BACKEND=redis_queue` 且可用 Redis 时，
提交任务到 Redis 列表，由独立 worker 进程消费并复用现有编排执行逻辑。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TaskPayload:
    strategy_name: str
    task_id: int
    resume_id: int
    jd_id: int
    user_id: int | None = None
    run_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "task_id": self.task_id,
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "user_id": self.user_id,
            "run_id": self.run_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> TaskPayload:
        return cls.from_dict(json.loads(raw))

    @classmethod
    def from_dict(cls, data: dict) -> TaskPayload:
        return cls(
            strategy_name=data["strategy_name"],
            task_id=int(data["task_id"]),
            resume_id=int(data["resume_id"]),
            jd_id=int(data["jd_id"]),
            user_id=data.get("user_id"),
            run_id=data.get("run_id"),
        )


class OrchestrationBackend:
    def submit(
        self,
        payload: TaskPayload,
        runner: Callable[[TaskPayload], None],
    ) -> None:
        raise NotImplementedError

    def shutdown(self) -> None:
        return None


class ThreadOrchestrationBackend(OrchestrationBackend):
    def __init__(self):
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()

    def _get_executor(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=max(1, int(settings.ORCHESTRATION_MAX_WORKERS or 4)),
                    thread_name_prefix="agent-orchestration",
                )
            return self._executor

    def submit(self, payload: TaskPayload, runner: Callable[[TaskPayload], None]) -> None:
        self._get_executor().submit(runner, payload)

    def shutdown(self) -> None:
        with self._lock:
            executor = self._executor
            self._executor = None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=False)


class RedisQueueOrchestrationBackend(OrchestrationBackend):
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        import redis

        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required for redis_queue backend")
        self._client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._client

    def submit(self, payload: TaskPayload, runner: Callable[[TaskPayload], None]) -> None:
        # runner 在这里被刻意忽略：闭包过不了 Redis 这道进程边界。
        # 所以 payload 必须自带执行所需的一切（含 run_id），worker 端统一走
        # _run_task_payload。把额外行为藏进闭包里，只会让两种后端跑出两种结果。
        client = self._get_client()
        # 入头 + BRPOPLPUSH 出尾 = FIFO。用 rpush 的话消费者会从尾巴上拿最新的一条，
        # 排在前面的老任务会被饿死。
        client.lpush(self._names()[0], _envelope(payload, attempts=0))

    # ---- 队列命名：四个键共用同一个前缀，运维只看名字就能对上 ----

    def _names(self) -> tuple[str, str, str, str]:
        base = settings.ORCHESTRATION_QUEUE_NAME
        return base, f"{base}:processing", f"{base}:dead-letter", f"{base}:inflight-deadlines"

    def queue_health(self) -> dict[str, Any]:
        client = self._get_client()
        queue, processing, dead, deadlines = self._names()
        try:
            return {
                "ok": bool(client.ping()),
                "backend": "redis_queue",
                "queue_name": queue,
                "queue_length": int(client.llen(queue)),
                # 在途与死信必须看得见：这两位数不是 0 而没人报警，就是"任务被静默吞掉"的现场。
                "processing_length": int(client.llen(processing)),
                "dead_letter_length": int(client.llen(dead)),
                "inflight_tracked": int(client.zcard(deadlines)),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "queue_name": queue}

    def worker_loop(
        self,
        runner: Callable[[TaskPayload], None],
        stop_event: Event | None = None,
    ) -> None:
        """至少一次投递：交接用 BRPOPLPUSH，跑完才 ack，超时的在途项由下一个 sweep 重投。

        三条边界都是这次改动要买的东西：worker 被杀不再丢任务（以前 `blpop` 先删后跑，
        进程一死元素就没了）、毒消息不会永远重放（attempts 上限 → 死信）、
        崩在交接与登记之间的元素会被**领养**而不是永久卡在 processing。
        """
        client = self._get_client()
        queue, processing, _dead, deadlines = self._names()
        poll_seconds = max(1, int(round(float(settings.ORCHESTRATION_QUEUE_POLL_SECONDS or 1.0))))
        while True:
            if stop_event and stop_event.is_set():
                return
            try:
                self.reclaim_stale(client)
                raw = client.brpoplpush(queue, processing, timeout=poll_seconds)
                if not raw:
                    continue
                try:
                    payload_data, attempts = _unwrap(raw)
                except ValueError:
                    # 认不出的元素重投多少次都还是认不出 —— 直接进死信，别占着重试预算。
                    logger.error("Redis worker 收到无法解析的元素，转入死信队列")
                    self._discard(client, raw)
                    client.rpush(self._names()[2], raw)
                    continue
                client.zadd(deadlines, {raw: _deadline()})
                try:
                    runner(TaskPayload.from_dict(payload_data))
                except KeyboardInterrupt:
                    # 收到停止信号时任务才跑了一半：ack 会把这条彻底吞掉，留在 processing 里
                    # 又要把等满可见性超时才重投。所以原样回队、**不消耗重试预算** ——
                    # 这不是任务的错，是部署动作打断的。
                    self._redistribute(
                        client, raw, payload_data, attempts, reason="worker shutdown", charge_attempt=False
                    )
                    return
                except Exception as exc:
                    logger.exception("Redis orchestration task failed: %s", exc)
                    self._redistribute(client, raw, payload_data, attempts, reason=str(exc))
                    continue
                self._discard(client, raw)  # 成功才 ack
            except KeyboardInterrupt:
                return
            except Exception as exc:
                logger.exception("Redis orchestration worker failed: %s", exc)
                time.sleep(max(0.1, float(settings.ORCHESTRATION_QUEUE_POLL_SECONDS or 1.0)))

    def reclaim_stale(self, client) -> None:
        """把"该重投的在途元素"处理掉：先领养没有期限的，再重投过期的。"""
        _queue, processing, dead, deadlines = self._names()
        now = time.time()
        in_flight = list(client.lrange(processing, 0, -1) or [])
        tracked = set(client.zrange(deadlines, 0, -1) or [])

        for raw in in_flight:
            if raw not in tracked:
                client.zadd(deadlines, {raw: _deadline()})  # 交接后崩在 zadd 之前，由这里接手

        for raw in list(client.zrangebyscore(deadlines, "-inf", now) or []):
            client.zrem(deadlines, raw)
            if raw not in in_flight:
                continue  # 已经跑完，只是崩在 zrem 之前 —— 重投就等于把同一个任务再跑一遍
            try:
                payload_data, attempts = _unwrap(raw)
            except ValueError:
                self._discard(client, raw)
                client.rpush(dead, raw)
                continue
            logger.warning("Redis worker 在途超时，重投或转死信：task_id=%s", payload_data.get("task_id"))
            self._redistribute(client, raw, payload_data, attempts, reason="visibility timeout")

    def _discard(self, client, raw: str) -> None:
        """ack：从 processing 与期限表里摘掉。幂等，重复调用无副作用。"""
        _queue, processing, _dead, deadlines = self._names()
        client.lrem(processing, 1, raw)
        client.zrem(deadlines, raw)

    def _redistribute(
        self, client, raw: str, payload_data: dict, attempts: int, reason: str, charge_attempt: bool = True
    ) -> None:
        """失败/超时后的去向：还有预算就回主队列，否则带原因进死信。"""
        _queue, _processing, dead, _deadlines = self._names()
        self._discard(client, raw)
        next_attempt = attempts + (1 if charge_attempt else 0)
        max_attempts = max(1, int(settings.ORCHESTRATION_MAX_ATTEMPTS or 3))
        if next_attempt >= max_attempts:
            logger.error("任务已尝试 %d 回仍失败，转入死信队列：%s", next_attempt, reason[:200])
            client.rpush(dead, _envelope(payload_data, attempts=next_attempt, reason=reason))
            return
        client.lpush(_queue, _envelope(payload_data, attempts=next_attempt))


def _deadline() -> float:
    return time.time() + max(1.0, float(settings.ORCHESTRATION_VISIBILITY_SECONDS or 3600.0))


def _envelope(payload, attempts: int, reason: str | None = None) -> str:
    """队列元素 = payload 本体 + 第几回尝试。

    交接之后**不改写元素**（改写会让 processing 与期限表里的键对不上），所以重投是
    "摘掉旧元素 + 推一个新 attempts 的元素"，重试次数随元素本身走。
    """
    data = payload.to_dict() if isinstance(payload, TaskPayload) else dict(payload)
    envelope = {"v": 1, "attempts": attempts, "payload": data}
    if reason:
        envelope["reason"] = reason[:500]
    return json.dumps(envelope, ensure_ascii=False)


def _unwrap(raw: str) -> tuple[dict, int]:
    """解析队列元素；返回 (payload 字典, 已尝试次数)。

    兼容升级前就排在队列里的平铺元素（没有 `payload` 键）—— 那类元素 attempts 记 0。
    """
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("queue element is not an object")
    if "payload" in data:
        payload = data["payload"]
        if not isinstance(payload, dict) or "task_id" not in payload:
            raise ValueError("envelope payload is not a TaskPayload")
        return payload, int(data.get("attempts", 0))
    if "task_id" in data:
        return data, 0
    raise ValueError("queue element is not a TaskPayload envelope")


def get_orchestration_backend() -> OrchestrationBackend:
    backend_name = str(settings.ORCHESTRATION_BACKEND or "thread").strip().lower()
    if backend_name == "redis_queue":
        try:
            return RedisQueueOrchestrationBackend()
        except Exception as exc:
            logger.warning("Falling back to thread backend: %s", exc)
    return ThreadOrchestrationBackend()


def health_snapshot() -> dict[str, Any]:
    backend = get_orchestration_backend()
    if isinstance(backend, RedisQueueOrchestrationBackend):
        snapshot = backend.queue_health()
        snapshot["backend"] = "redis_queue"
        return snapshot
    return {"ok": True, "backend": "thread", "queue_name": None, "queue_length": 0}
