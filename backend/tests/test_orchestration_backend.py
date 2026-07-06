# -*- coding: utf-8 -*-
from __future__ import annotations

from threading import Event

from app.services.orchestration_backend import (
    TaskPayload,
    ThreadOrchestrationBackend,
    RedisQueueOrchestrationBackend,
    health_snapshot,
)


def test_thread_backend_submits_payload(monkeypatch):
    captured = {}

    class FakeExecutor:
        def submit(self, fn, payload):
            captured["fn"] = fn
            captured["payload"] = payload

    backend = ThreadOrchestrationBackend()
    monkeypatch.setattr(backend, "_get_executor", lambda: FakeExecutor())

    payload = TaskPayload("linear", 1, 2, 3, user_id=4)
    backend.submit(payload, lambda p: None)

    assert captured["payload"].task_id == 1
    assert captured["payload"].strategy_name == "linear"


def test_redis_backend_enqueues_payload(monkeypatch):
    calls = []

    class FakeRedis:
        def rpush(self, queue_name, payload):
            calls.append(("rpush", queue_name, payload))

    monkeypatch.setattr("app.services.orchestration_backend.settings.REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr("app.services.orchestration_backend.settings.ORCHESTRATION_QUEUE_NAME", "test-q")
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: FakeRedis())

    backend = RedisQueueOrchestrationBackend()
    payload = TaskPayload("linear", 7, 8, 9)
    backend.submit(payload, lambda p: None)

    assert calls[0][0] == "rpush"
    assert calls[0][1] == "test-q"


def test_redis_worker_loop_consumes_once(monkeypatch):
    consumed = []

    class FakeRedis:
        def __init__(self):
            self.calls = 0

        def blpop(self, queue_name, timeout=0):
            self.calls += 1
            if self.calls == 1:
                return (queue_name, TaskPayload("linear", 5, 6, 7).to_json())
            raise KeyboardInterrupt()

    monkeypatch.setattr("app.services.orchestration_backend.settings.REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr("app.services.orchestration_backend.settings.ORCHESTRATION_QUEUE_NAME", "test-q")
    monkeypatch.setattr("app.services.orchestration_backend.settings.ORCHESTRATION_QUEUE_POLL_SECONDS", 0.1)
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: FakeRedis())

    backend = RedisQueueOrchestrationBackend()

    def runner(payload):
        consumed.append(payload.task_id)
        raise KeyboardInterrupt()

    backend.worker_loop(runner, stop_event=Event())

    assert consumed == [5]


def test_queue_health_snapshot_returns_status():
    health = health_snapshot()
    assert "ok" in health
    assert health["backend"] in {"thread", "redis_queue"}
