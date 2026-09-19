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

    def to_json(self) -> str:
        return json.dumps(
            {
                "strategy_name": self.strategy_name,
                "task_id": self.task_id,
                "resume_id": self.resume_id,
                "jd_id": self.jd_id,
                "user_id": self.user_id,
                "run_id": self.run_id,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> TaskPayload:
        data = json.loads(raw)
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
        client.rpush(settings.ORCHESTRATION_QUEUE_NAME, payload.to_json())

    def queue_health(self) -> dict[str, Any]:
        client = self._get_client()
        try:
            ping = bool(client.ping())
            length = int(client.llen(settings.ORCHESTRATION_QUEUE_NAME))
            return {"ok": ping, "queue_length": length, "queue_name": settings.ORCHESTRATION_QUEUE_NAME}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "queue_name": settings.ORCHESTRATION_QUEUE_NAME}

    def worker_loop(
        self,
        runner: Callable[[TaskPayload], None],
        stop_event: Event | None = None,
    ) -> None:
        client = self._get_client()
        poll_seconds = max(1, int(round(float(settings.ORCHESTRATION_QUEUE_POLL_SECONDS or 1.0))))
        while True:
            if stop_event and stop_event.is_set():
                return
            try:
                item = client.blpop(settings.ORCHESTRATION_QUEUE_NAME, timeout=poll_seconds)
                if not item:
                    continue
                _, raw = item
                runner(TaskPayload.from_json(raw))
            except KeyboardInterrupt:
                return
            except Exception as exc:
                logger.exception("Redis orchestration worker failed: %s", exc)
                time.sleep(max(0.1, float(settings.ORCHESTRATION_QUEUE_POLL_SECONDS or 1.0)))


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
