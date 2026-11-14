"""收单守门与"从没开始"的收口（D6）。

现场（2026-11-14 真 provider 实测）：`backend/.env` 写着 `ORCHESTRATION_BACKEND=redis_queue`，
机器上没有任何 worker 进程。`POST /api/analysis/full` 回了 200 + task_id，任务在 Redis 队列里
躺了 733 秒：`steps=0`、`prompt_trace=0`、`progress=0`，候选人屏幕上只有一个永远转的圈，
而 `/system/status` 里 `queue_health` 是 `ok=True / queue_length=2 / dead_letter=0` —— 一切正常。

三件事要钉住：

1. **可观测**：worker 写心跳，"队列有没有活人"从一个看不出来的事实变成一个数；
2. **守门**：没有活人时入口直接 503，不落任务行、不发任务号；
3. **收口**：万一任务已经发出去了，读任务状态的那一跳把它判成 failed 并说明原因。

第 3 条的判据刻意很窄，测试里也守着它窄在哪：**从没开始 + 确认没有活着的消费者**。
worker 活着时排队中的任务不许判死 —— 那会在几分钟后与真正的完成撞车。
"""

from __future__ import annotations

from datetime import timedelta
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.agent import router as agent_router
from app.api.auth import router as auth_router
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.agent import AgentStepLog, AgentTask
from app.models.user import User
from app.services import orchestration_runner
from app.services.operational_alert_service import collect_operational_alerts
from app.services.orchestration_backend import (
    OrchestrationUnavailable,
    RedisQueueOrchestrationBackend,
    ThreadOrchestrationBackend,
    worker_heartbeat_key,
)
from app.services.orchestration_runner import converge_running_task, run_strategy_async
from app.utils.time_helper import utc_now_naive

QUEUE = "guard-q"
HEARTBEAT = worker_heartbeat_key(QUEUE)


# ------------------------------------------------------------------ 夹具与替身


class FakeRedis:
    """只实现心跳与健康快照用到的命令；语义按 redis.io 来，别把假客户端写松。"""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.expiry: dict[str, int | None] = {}
        self.lists: dict[str, list[str]] = {}
        self.on_brpoplpush = None

    def set(self, name, value, ex=None):
        self.kv[name] = value
        self.expiry[name] = ex
        return True

    def get(self, name):
        return self.kv.get(name)

    def ping(self):
        return True

    def llen(self, name):
        return len(self.lists.get(name, []))

    def lrange(self, name, start, stop):
        items = self.lists.get(name, [])
        return items[start:] if stop == -1 else items[start : stop + 1]

    def zcard(self, name):
        return 0

    def zrange(self, name, start, stop):
        return []

    def zrangebyscore(self, name, low, high):
        return []

    def brpoplpush(self, source, target, timeout=0):
        if self.on_brpoplpush:
            self.on_brpoplpush()
        return None


def _redis_backend(monkeypatch, fake: FakeRedis) -> RedisQueueOrchestrationBackend:
    monkeypatch.setattr("app.services.orchestration_backend.settings.ORCHESTRATION_QUEUE_NAME", QUEUE)
    monkeypatch.setattr("app.services.orchestration_backend.settings.ORCHESTRATION_QUEUE_POLL_SECONDS", 1.0)
    backend = RedisQueueOrchestrationBackend()
    monkeypatch.setattr(backend, "_get_client", lambda: fake)
    return backend


class _HealthBackend(RedisQueueOrchestrationBackend):
    """把健康快照写死的 redis 后端：收口/守门的判断不依赖真 Redis。"""

    def __init__(self, *, alive: bool, ok: bool = True, queue_length: int = 2) -> None:
        super().__init__()
        self._health = {
            "ok": ok,
            "backend": "redis_queue",
            "queue_name": QUEUE,
            "queue_length": queue_length,
            "worker_alive": alive,
            "worker_last_seen_seconds": 1.0 if alive else None,
        }
        self.submitted: list = []

    def queue_health(self):
        return dict(self._health)

    def submit(self, payload, runner):
        self.submitted.append(payload)


class _SubmitBoomBackend(_HealthBackend):
    def __init__(self) -> None:
        super().__init__(alive=True)

    def submit(self, payload, runner):
        raise RuntimeError("redis 在投递这一跳断了")


@pytest.fixture
def dispatch_db(db_session, monkeypatch):
    """把 `orchestration_runner` 自建的 `SessionLocal` 接到 `db_session` 那一份库上。

    这些用例要断言"有没有留下任务行"，而 `create_task()` / `fail_task()` 走的是它们自己的
    `SessionLocal()`（app 引擎）——与 `db_session` 不是同一个内存库。不接上的话
    `db_session.query(AgentTask).count()` 永远是 0，"没有留行"这条断言就成了空话。
    """

    class _KeepOpen:
        """代理一次会话，只把 `close()` 吃掉：调用方 owns_session=True 会关它。"""

        def __init__(self, session):
            self._session = session

        def __getattr__(self, name):
            return getattr(self._session, name)

        def close(self):
            return None

    monkeypatch.setattr(orchestration_runner, "SessionLocal", lambda: _KeepOpen(db_session))
    return db_session


@pytest.fixture
def agent_client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(agent_router, prefix="/agent")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


def _create_user(db_session, username: str) -> User:
    user = User(username=username, email=f"{username}@example.com", password=hash_password("abc12345"))
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}


def _running_task(db_session, *, user_id: int, age_minutes: float, steps: int = 0) -> AgentTask:
    task = AgentTask(
        user_id=user_id,
        resume_id=1,
        jd_id=1,
        status="running",
        start_time=utc_now_naive() - timedelta(minutes=age_minutes),
        plan=[{"step": "intent"}, {"step": "match"}],
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    for index in range(1, steps + 1):
        db_session.add(AgentStepLog(task_id=task.id, step_name="IntentAgent", step_index=index, status="running"))
    if steps:
        db_session.commit()
    return task


# ------------------------------------------------------------------ ① 心跳可观测


def test_a_live_worker_is_visible_in_queue_health(monkeypatch):
    fake = FakeRedis()
    backend = _redis_backend(monkeypatch, fake)

    backend.beat()

    health = backend.queue_health()
    assert health["worker_alive"] is True
    assert health["worker_last_seen_seconds"] is not None
    assert health["worker_last_seen_seconds"] >= 0
    assert fake.expiry[HEARTBEAT] == backend.heartbeat_ttl_seconds(), "心跳没有 TTL：worker 一死这个键会永远在"


def test_a_missing_heartbeat_is_reported_even_though_every_old_number_looks_fine(monkeypatch):
    """反证：这正是 D6 的现场形状 —— 队列 ok、有积压、死信 0，而根本没有消费者。

    只看 `ok / queue_length / dead_letter_length` 这三个数的仪表对这一类事故是瞎的，
    所以 `worker_alive` 必须是独立的一列，不能从别处推。
    """
    fake = FakeRedis()
    fake.lists[QUEUE] = ["one", "two"]
    backend = _redis_backend(monkeypatch, fake)

    health = backend.queue_health()

    assert health["ok"] is True
    assert health["queue_length"] == 2
    assert health["dead_letter_length"] == 0
    assert health["worker_alive"] is False, "没有心跳必须判成没有消费者"
    assert health["worker_last_seen_seconds"] is None


def test_the_worker_beats_before_it_starts_blocking(monkeypatch):
    """第一拍必须在进阻塞循环之前写下去：否则 worker 起来后要空等一个 TTL 才有人接单。"""
    fake = FakeRedis()
    backend = _redis_backend(monkeypatch, fake)
    stop = Event()

    def assert_beaten():
        assert HEARTBEAT in fake.kv, "worker 还没写心跳就开始等任务了"
        stop.set()

    fake.on_brpoplpush = assert_beaten
    backend.worker_loop(lambda payload: None, stop_event=stop)

    assert HEARTBEAT in fake.kv


# ------------------------------------------------------------------ ② 守门：没有人就不发任务号


def test_dispatch_is_refused_and_creates_no_task_when_no_worker_is_alive(dispatch_db, monkeypatch):
    backend = _HealthBackend(alive=False)
    monkeypatch.setattr(orchestration_runner, "_BACKEND", backend)
    before = dispatch_db.query(AgentTask).count()

    with pytest.raises(OrchestrationUnavailable) as excinfo:
        run_strategy_async("linear", resume_id=1, jd_id=1, user_id=1)

    assert "worker" in str(excinfo.value)
    assert dispatch_db.query(AgentTask).count() == before, "被拒绝的请求不该留下任务行"
    assert backend.submitted == []


def test_dispatch_is_refused_when_the_queue_itself_is_unreachable(dispatch_db, monkeypatch):
    backend = _HealthBackend(alive=False, ok=False)
    monkeypatch.setattr(orchestration_runner, "_BACKEND", backend)

    with pytest.raises(OrchestrationUnavailable) as excinfo:
        run_strategy_async("linear", resume_id=1, jd_id=1, user_id=1)

    assert "队列" in str(excinfo.value)


def test_dispatch_proceeds_when_a_worker_is_heartbeating(dispatch_db, monkeypatch):
    backend = _HealthBackend(alive=True)
    monkeypatch.setattr(orchestration_runner, "_BACKEND", backend)

    task_id = run_strategy_async("linear", resume_id=1, jd_id=1, user_id=1)

    assert backend.submitted[0].task_id == task_id
    assert dispatch_db.get(AgentTask, task_id).status == "running"


def test_a_submit_failure_does_not_leave_a_task_stuck_in_running(dispatch_db, monkeypatch):
    backend = _SubmitBoomBackend()
    monkeypatch.setattr(orchestration_runner, "_BACKEND", backend)

    with pytest.raises(OrchestrationUnavailable):
        run_strategy_async("linear", resume_id=1, jd_id=1, user_id=1)

    task = dispatch_db.query(AgentTask).one()
    assert task.status == "failed", "投递失败却留着 running，就是一个新的永远转圈"
    assert "投递失败" in task.error_msg


def test_the_thread_backend_never_asks_about_a_consumer(dispatch_db, monkeypatch):
    """线程后端的消费者就是本进程：它不该因为'没有心跳'被拒绝。"""
    backend = ThreadOrchestrationBackend()
    submitted = []
    monkeypatch.setattr(orchestration_runner, "_BACKEND", backend)
    monkeypatch.setattr(backend, "submit", lambda payload, runner: submitted.append(payload))

    task_id = run_strategy_async("linear", resume_id=1, jd_id=1, user_id=1)

    assert submitted[0].task_id == task_id


# ------------------------------------------------------------------ ③ 收口：从没开始的任务


def test_a_task_that_never_started_is_converged_with_a_reason(db_session):
    user = _create_user(db_session, "converge_owner")
    task = _running_task(db_session, user_id=user.id, age_minutes=5)

    reason = converge_running_task(task, db_session, backend=_HealthBackend(alive=False))

    assert reason and "排队" in reason
    db_session.refresh(task)
    assert task.status == "failed"
    assert task.error_msg == reason
    assert task.end_time is not None


def test_a_queued_task_is_left_alone_while_a_worker_is_alive(db_session):
    """判据必须窄在这里：worker 活着时它只是排在别人后面。

    判死的后果不是"多了一条 failed 记录"，而是**两处说法不一致**：任务被标 failed，
    几分钟后真正跑完又落了一条 AnalysisRecord。
    """
    user = _create_user(db_session, "queue_owner")
    task = _running_task(db_session, user_id=user.id, age_minutes=5)

    assert converge_running_task(task, db_session, backend=_HealthBackend(alive=True)) is None
    db_session.refresh(task)
    assert task.status == "running"


def test_a_task_that_already_has_steps_is_left_to_the_stale_sweep(db_session):
    """已经开始的任务由"最后一次活动超过 30 分钟"那条判据管，不该被启动超时误伤。"""
    user = _create_user(db_session, "started_owner")
    task = _running_task(db_session, user_id=user.id, age_minutes=5, steps=1)

    assert converge_running_task(task, db_session, backend=_HealthBackend(alive=False)) is None
    db_session.refresh(task)
    assert task.status == "running"


def test_a_young_task_is_never_converged(db_session):
    user = _create_user(db_session, "young_owner")
    task = _running_task(db_session, user_id=user.id, age_minutes=0)

    assert converge_running_task(task, db_session, backend=_HealthBackend(alive=False)) is None
    db_session.refresh(task)
    assert task.status == "running"


def test_the_polled_task_endpoint_turns_the_spinner_into_a_readable_failure(db_session, agent_client, monkeypatch):
    """这条是验收：前端每 2 秒轮询的那一跳，会在下一次轮询里拿到带原因的 failed。"""
    monkeypatch.setattr(orchestration_runner, "_BACKEND", _HealthBackend(alive=False))
    user = _create_user(db_session, "poll_owner")
    task = _running_task(db_session, user_id=user.id, age_minutes=5)

    response = agent_client.get(f"/agent/task/{task.id}", headers=_auth_headers(user))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert "排队" in data["error_msg"]
    assert data["progress"]["progress_percent"] == 0, "从没开始的任务进度就是 0，这里不该被改成 100"


def test_the_task_list_converges_the_same_way(db_session, agent_client, monkeypatch):
    monkeypatch.setattr(orchestration_runner, "_BACKEND", _HealthBackend(alive=False))
    user = _create_user(db_session, "list_owner")
    task = _running_task(db_session, user_id=user.id, age_minutes=5)

    response = agent_client.get("/agent/tasks", headers=_auth_headers(user))

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["status"] for item in items if item["id"] == task.id] == ["failed"]


# ------------------------------------------------------------------ ④ 运维告警


def _snapshot(queue_health: dict) -> dict:
    return {
        "model_runtime": {"ready": True, "llm": {"mode": "live"}, "embedding": {"mode": "live"}},
        "queue_health": queue_health,
        "runtime_metrics": {"total_requests": 0, "error_requests": 0},
        "db_pool": {"samples": 0, "p95_seconds": None, "over_pool_timeout_samples": 0},
    }


def _alert_keys(db_session, queue_health: dict) -> set[str]:
    return {alert["alert_key"] for alert in collect_operational_alerts(db_session, **_snapshot(queue_health))}


def test_a_queue_without_consumers_is_its_own_alert(db_session):
    keys = _alert_keys(
        db_session,
        {
            "ok": True,
            "backend": "redis_queue",
            "queue_name": QUEUE,
            "queue_length": 2,
            "worker_alive": False,
            "worker_last_seen_seconds": None,
        },
    )

    assert "orchestration_queue_no_worker" in keys
    # 反证：只靠旧的三个数，这个现场一条都不会红 —— 所以这条规则不能省。
    assert "orchestration_queue_backlog" not in keys
    assert "orchestration_queue_unavailable" not in keys


def test_a_heartbeating_worker_clears_the_alert(db_session):
    keys = _alert_keys(
        db_session,
        {
            "ok": True,
            "backend": "redis_queue",
            "queue_length": 2,
            "worker_alive": True,
            "worker_last_seen_seconds": 1.0,
        },
    )

    assert "orchestration_queue_no_worker" not in keys


def test_the_thread_backend_is_not_applicable_and_does_not_alert(db_session):
    """`worker_alive=None` 是"不适用"，不能被当成"没有"。判据用 `is False` 就是为了这个。"""
    keys = _alert_keys(db_session, {"ok": True, "backend": "thread", "queue_length": 0, "worker_alive": None})

    assert "orchestration_queue_no_worker" not in keys
