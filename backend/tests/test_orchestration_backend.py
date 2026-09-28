"""`redis_queue` 后端的投递语义（E24）。

改前的形状：`submit` 用 `rpush`，worker 用 **`blpop` 先删再跑** —— 于是 worker 进程一死，
元素就没了：没有 ack、没有重投、没有死信。DB 侧不是完全瞎（`_run_task_payload` 会把异常写成
`failed`，E12 的静默判定会把残留 `running` 扫成失败），但那只是"最终会被标失败"，不是"不会被丢"。

现在这一组测试盯的是四个承诺：**跑完才 ack**、**在途超时会重投**、**重试有上限、超了进死信**、
**崩在半路的元素既不会被丢也不会被重跑两遍**。
"""

from __future__ import annotations

import json
from collections import defaultdict
from threading import Event

import pytest

from app.services.orchestration_backend import (
    RedisQueueOrchestrationBackend,
    TaskPayload,
    ThreadOrchestrationBackend,
    health_snapshot,
)

QUEUE = "test-q"
PROCESSING = "test-q:processing"
DEAD = "test-q:dead-letter"
DEADLINES = "test-q:inflight-deadlines"


class FakeRedis:
    """只实现这次用到的命令，但按 Redis 的真实语义实现。

    假客户端要是把语义写松了（比如 lrem 不真删、zrangebyscore 不看分数），这些测试就只是在
    给实现背书，所以每条都对着 redis.io 的行为来：`LPUSH` 进头部、`BRPOPLPUSH` 从尾部弹出并
    压入目标头部、zset 按分数排序。
    """

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = defaultdict(list)
        self.zsets: dict[str, dict[str, float]] = defaultdict(dict)
        # 真 Redis 的 BRPOPLPUSH 会阻塞 timeout 秒，所以产品的 `if not raw: continue` 不会空转；
        # 假客户端立刻返回 None，就得由这个钩子告诉测试"队列空了，可以停了"。
        # 没有它，凡是"元素没走到 runner"的用例（比如坏数据直接进死信）都会自旋到超时。
        self.when_idle = None

    # ---- lists ----
    def lpush(self, name, *values):
        for value in values:
            self.lists[name].insert(0, value)
        return len(self.lists[name])

    def rpush(self, name, *values):
        self.lists[name].extend(values)
        return len(self.lists[name])

    def llen(self, name):
        return len(self.lists[name])

    def lrange(self, name, start, stop):
        items = self.lists[name]
        return items[start:] if stop == -1 else items[start : stop + 1]

    def lrem(self, name, count, value):
        items = self.lists[name]
        if value in items:
            items.remove(value)
            return 1
        return 0

    def brpoplpush(self, source, target, timeout=0):
        if not self.lists[source]:
            if self.when_idle:
                self.when_idle()
            return None
        raw = self.lists[source].pop()  # 尾部弹出
        self.lists[target].insert(0, raw)  # 目标头部压入
        return raw

    # ---- sorted sets ----
    def zadd(self, name, mapping):
        self.zsets[name].update(mapping)
        return len(mapping)

    def zrem(self, name, member):
        return 1 if self.zsets[name].pop(member, None) is not None else 0

    def zcard(self, name):
        return len(self.zsets[name])

    def zrange(self, name, start, stop):
        return list(self.zsets[name])

    def zrangebyscore(self, name, low, high):
        limit = float("inf") if str(high) in {"+inf", "inf"} else float(high)
        ordered = sorted(self.zsets[name].items(), key=lambda kv: kv[1])
        return [member for member, score in ordered if score <= limit]

    def ping(self):
        return True


@pytest.fixture
def redis(monkeypatch):
    fake = FakeRedis()
    for name, value in (
        ("REDIS_URL", "redis://localhost:6379/0"),
        ("ORCHESTRATION_QUEUE_NAME", QUEUE),
        ("ORCHESTRATION_QUEUE_POLL_SECONDS", 0.01),
        ("ORCHESTRATION_MAX_ATTEMPTS", 3),
        ("ORCHESTRATION_VISIBILITY_SECONDS", 3600.0),
    ):
        monkeypatch.setattr("app.services.orchestration_backend.settings." + name, value)
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake)
    return fake


def _backend(redis):  # noqa: ARG001 - 参数只是把 fixture 拉进作用域
    return RedisQueueOrchestrationBackend()


def _run_one(backend, redis, runner):  # noqa: ARG001 - 参数只是把 fixture 拉进作用域
    """跑一次 worker_loop，直到队列排空或 runner 自己把 stop 立起来。

    两个退出条件都要：坏数据那类用例根本走不到 runner，只靠队列空转停止。
    """
    stop = Event()
    redis.when_idle = stop.set

    def wrapped(payload):
        try:
            runner(payload)
        finally:
            stop.set()

    backend.worker_loop(wrapped, stop_event=stop)


def _envelope_of(raw: str) -> dict:
    return json.loads(raw)


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


def test_submit_enqueues_a_fresh_envelope(redis):
    """ "新任务"必须带着 attempts=0 进队列，且**入头**（消费者从尾部取，才有 FIFO）。"""
    redis.lpush(QUEUE, json.dumps({"v": 1, "attempts": 0, "payload": {"task_id": 0}}))  # 已有一个在排
    _backend(redis).submit(TaskPayload("linear", 7, 8, 9, user_id=3, run_id=11), lambda p: None)

    assert redis.llen(QUEUE) == 2
    newest, oldest = redis.lrange(QUEUE, 0, -1)
    assert _envelope_of(newest)["payload"]["task_id"] == 7, "新任务没排在头部"
    assert _envelope_of(newest)["attempts"] == 0
    assert _envelope_of(oldest)["payload"]["task_id"] == 0


def test_the_worker_acks_only_after_the_runner_finishes(redis):
    """跑成功 → processing 与期限表都清空，主队列不再出现这条。"""
    backend = _backend(redis)
    backend.submit(TaskPayload("linear", 5, 6, 7), lambda p: None)

    seen = []
    _run_one(backend, redis, lambda payload: seen.append(payload.task_id))

    assert seen == [5]
    assert redis.llen(QUEUE) == 0
    assert redis.llen(PROCESSING) == 0
    assert redis.zcard(DEADLINES) == 0
    assert redis.llen(DEAD) == 0


def test_a_failing_task_is_requeued_with_a_bumped_attempt_count(redis):
    """抛异常 ≠ 丢任务：元素必须回到主队列，且 attempts 变成 1。"""
    backend = _backend(redis)
    backend.submit(TaskPayload("linear", 5, 6, 7), lambda p: None)

    def boom(_payload):
        raise RuntimeError("provider exploded")

    _run_one(backend, redis, boom)

    assert redis.llen(QUEUE) == 1, "失败的任务没被重投"
    assert redis.llen(PROCESSING) == 0
    assert _envelope_of(redis.lrange(QUEUE, 0, -1)[0])["attempts"] == 1


def test_the_retry_budget_ends_in_the_dead_letter_queue(redis):
    """毒消息不能永远重放：跑满 ORCHESTRATION_MAX_ATTEMPTS 后要落在死信里，且带着原因。"""
    backend = _backend(redis)
    redis.rpush(QUEUE, json.dumps({"v": 1, "attempts": 2, "payload": TaskPayload("linear", 5, 6, 7).to_dict()}))

    def boom(_payload):
        raise RuntimeError("provider exploded")

    _run_one(backend, redis, boom)

    assert redis.llen(QUEUE) == 0, "已经跑满预算还回主队列"
    assert redis.llen(DEAD) == 1
    dead = _envelope_of(redis.lrange(DEAD, 0, -1)[0])
    assert dead["attempts"] == 3
    assert "provider exploded" in dead["reason"]


def test_an_abandoned_inflight_item_is_requeued_once_its_deadline_passes(redis):
    """worker 交接之后被杀：元素停在 processing 里，期限一过就必须被下一个 worker 重投。"""
    backend = _backend(redis)
    raw = json.dumps({"v": 1, "attempts": 0, "payload": TaskPayload("linear", 5, 6, 7).to_dict()})
    redis.rpush(PROCESSING, raw)
    redis.zadd(DEADLINES, {raw: 0.0})  # 早就过期的期限

    backend.reclaim_stale(redis)

    assert redis.llen(QUEUE) == 1
    assert redis.llen(PROCESSING) == 0
    assert _envelope_of(redis.lrange(QUEUE, 0, -1)[0])["attempts"] == 1


def test_an_item_in_processing_without_a_deadline_is_adopted(redis):
    """崩在"交接完成"与"登记期限"之间的元素不能被忘在 processing 里 —— 先给它补一个期限。"""
    backend = _backend(redis)
    raw = json.dumps({"v": 1, "attempts": 0, "payload": TaskPayload("linear", 5, 6, 7).to_dict()})
    redis.rpush(PROCESSING, raw)

    backend.reclaim_stale(redis)

    assert redis.zcard(DEADLINES) == 1, "没被领养"
    assert redis.llen(QUEUE) == 0, "刚领养就重投 = 同一个任务跑两遍"
    assert redis.llen(PROCESSING) == 1


def test_an_acked_item_with_a_lingering_deadline_is_not_requeued(redis):
    """崩在"从 processing 摘掉"与"从期限表摘掉"之间：这条已经跑完了，**绝不能**再投一次。

    没有这条，"至少一次"会退化成"至少两次"——而每多跑一遍都是真金白银的 LLM 调用。
    """
    backend = _backend(redis)
    raw = json.dumps({"v": 1, "attempts": 0, "payload": TaskPayload("linear", 5, 6, 7).to_dict()})
    redis.zadd(DEADLINES, {raw: 0.0})  # 过期的期限，但 processing 里没有它

    backend.reclaim_stale(redis)

    assert redis.llen(QUEUE) == 0
    assert redis.zcard(DEADLINES) == 0


def test_unparseable_elements_go_straight_to_the_dead_letter_queue(redis):
    """认不出的元素重投多少次都还是认不出：不进重试预算，直接死信，别把队列堵死。"""
    backend = _backend(redis)
    redis.rpush(QUEUE, "not json at all")

    seen = []
    _run_one(backend, redis, lambda payload: seen.append(payload))

    assert seen == []
    assert redis.llen(DEAD) == 1
    assert redis.llen(QUEUE) == 0
    assert redis.llen(PROCESSING) == 0


def test_a_shutdown_mid_task_goes_back_to_the_queue_without_consuming_a_retry(redis):
    """部署打断不是任务的错：SIGTERM 时原样回队，attempts 不变。"""
    backend = _backend(redis)
    backend.submit(TaskPayload("linear", 5, 6, 7), lambda p: None)

    backend.worker_loop(lambda _payload: (_ for _ in ()).throw(KeyboardInterrupt()), stop_event=Event())

    assert redis.llen(QUEUE) == 1
    assert _envelope_of(redis.lrange(QUEUE, 0, -1)[0])["attempts"] == 0
    assert redis.llen(PROCESSING) == 0
    assert redis.llen(DEAD) == 0


def test_queue_health_reports_every_bucket(redis):
    """在途与死信必须看得见：只有 queue_length 的仪表看不到"任务被静默吞掉"这种事故。"""
    backend = _backend(redis)
    backend.submit(TaskPayload("linear", 5, 6, 7), lambda p: None)
    redis.rpush(PROCESSING, "in-flight")
    redis.rpush(DEAD, "dead")
    redis.zadd(DEADLINES, {"in-flight": 1.0})

    health = backend.queue_health()

    assert health["ok"] is True
    assert health["queue_length"] == 1
    assert health["processing_length"] == 1
    assert health["dead_letter_length"] == 1
    assert health["inflight_tracked"] == 1


def test_legacy_flat_elements_are_still_consumed(redis):
    """升级前就排在队列里的平铺元素（没有信封）不能被当成坏数据扔进死信。"""
    backend = _backend(redis)
    redis.rpush(QUEUE, TaskPayload("linear", 5, 6, 7).to_json())

    seen = []
    _run_one(backend, redis, lambda payload: seen.append(payload.task_id))

    assert seen == [5]
    assert redis.llen(DEAD) == 0


def test_queue_health_snapshot_returns_status():
    health = health_snapshot()
    assert "ok" in health
    assert health["backend"] in {"thread", "redis_queue"}
