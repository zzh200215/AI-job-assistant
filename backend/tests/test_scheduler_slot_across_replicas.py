"""D175：调度槽位——同一拍跨副本只让一个进程跑，且这七条真的走它。

背景（现量）：两份 compose 各只有 1 个 backend，`backend/Dockerfile` 的 CMD 不带 `--workers`，
所以"副本 >1 就每人跑一遍"今天还没发生；这条是他点名的"现在装"。装完之后扩副本**仍然**被
`backend/chroma_db` 那份嵌入式向量库拦着（见 `test_single_process_shape_is_pinned.py`），
所以本文件不等于"可以加副本了"。

两条取舍各配一个反面证据：① 抢到锁的那一发**不释放**（释放就把同一拍的窗口重开给晚到的副本）；
② Redis 连不上时 **fail-open**（单副本是今天的形状，fail-closed 会让一次抖动把 7 条任务全停掉）。
"""

from __future__ import annotations

import logging
from functools import partial

import pytest
from apscheduler.triggers.interval import IntervalTrigger

from app.core import scheduler as sched
from app.core import scheduler_slot as slot

JOB_NAMES = [
    "reminder_check",
    "new_jd_push",
    "target_stats_refresh",
    "operational_alert_evaluation",
    "external_api_monthly_billing",
    "job_embedding_sync",
    "interview_evaluation_requeue",
]


class FakeRedis:
    """只实现 `set(nx=True, ex=...)` 与 `delete`——槽位这条路径只用得到这两个。"""

    def __init__(self, *, deny=False, error=None):
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}
        self.deleted: list[str] = []
        self.deny = deny
        self.error = error

    def set(self, key, value, *, nx=False, ex=None):
        if self.error is not None:
            raise self.error
        if self.deny:
            return None
        if nx and key in self.store:
            return None
        self.store[key] = value
        self.ttl[key] = ex
        return True

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)


# ---------------------------------------------------------------- ① 同一拍只有一个副本跑


@pytest.fixture(autouse=True)
def _never_touch_the_live_redis(monkeypatch):
    """整份文件都不许落到真连接上。

    开发机 `backend/.env` 是配了 `REDIS_URL` 的，而这份文件第一版没有这道闸：`client=None`
    被当成"没传"解析回了活体 Redis，于是测试往开发机的 Redis 里写了 `sched-slot:*`，
    并且**只在第一次跑是绿的**（TTL 300s 之内第二次就被自己上一跑留下的键拒掉）。
    闸装在 fixture 层而不是靠每条用例自觉注入。
    """
    monkeypatch.setattr(slot, "get_slot_client", lambda: None)


def test_explicit_none_means_no_redis_not_resolve(monkeypatch):
    """`client=None` 是"这台机器没有 redis"（fail-open），不是"替我去取一条连接"。"""
    denying = FakeRedis(deny=True)
    denying.store[f"{slot.SLOT_KEY_PREFIX}:reminder_check"] = "someone"
    monkeypatch.setattr(slot, "get_slot_client", lambda: denying)

    ran = []
    assert slot.run_exclusive("reminder_check", 600, lambda: ran.append(1), client=None) is True
    assert ran == [1], "显式传 None 被解析回了 get_slot_client——那条路会碰活体 Redis"


def test_two_replicas_on_the_same_tick_run_the_job_once():
    client = FakeRedis()
    calls: list[str] = []

    first = slot.run_exclusive("reminder_check", 600, lambda: calls.append("A"), client=client)
    second = slot.run_exclusive("reminder_check", 600, lambda: calls.append("B"), client=client)

    assert first is True and second is False
    assert calls == ["A"], "两个副本都跑了：槽位没拦住晚到的那一个"
    assert client.ttl[f"{slot.SLOT_KEY_PREFIX}:reminder_check"] == 600, "TTL 没落到 SET 上，这把锁永远不会过期"


def test_the_winner_does_not_release_the_slot():
    """跑完不释放：释放等于把『同一拍』的窗口重开给晚启动或晚触发的副本。"""
    client = FakeRedis()
    ran: list[str] = []

    assert slot.run_exclusive("new_jd_push", 900, lambda: ran.append("x"), client=client) is True
    assert client.deleted == [], "有人加了释放——『不释放』这条取舍已经从代码里消失了"
    assert slot.run_exclusive("new_jd_push", 900, lambda: ran.append("y"), client=client) is False
    assert ran == ["x"]

    # 反向：一旦真被释放了，同拍的第二次调用就会重跑。这一步证明上面那句断言不是空话。
    client.delete(f"{slot.SLOT_KEY_PREFIX}:new_jd_push")
    assert slot.run_exclusive("new_jd_push", 900, lambda: ran.append("z"), client=client) is True
    assert ran == ["x", "z"]


# ---------------------------------------------------------------- ② Redis 不在就照跑


def test_missing_redis_fails_open():
    """调度器注册的那条路（不传 client）在 Redis 缺席时照跑——autouse 闸把 `get_slot_client` 换成 None。"""
    ran = []
    assert slot.run_exclusive("job_embedding_sync", 300, lambda: ran.append(1)) is True
    assert ran == [1], "REDIS_URL 没配（单副本的常态）时把任务停掉了——那是 fail-closed，方向反了"


def test_down_redis_fails_open_and_says_so(caplog):
    client = FakeRedis(error=ConnectionError("Connection refused"))
    ran = []
    with caplog.at_level(logging.WARNING, logger="app.core.scheduler_slot"):
        assert slot.run_exclusive("reminder_check", 600, lambda: ran.append(1), client=client) is True
    assert ran == [1]
    assert any("fail-open" in r.getMessage() for r in caplog.records), "降级没有痕迹：查不到这一拍到底跑了几个副本"


# ---------------------------------------------------------------- ③ 窗口从触发器算，不手写第二个数


def test_slot_window_is_derived_and_never_blocks_the_next_tick():
    specs = sched.scheduled_job_specs()
    assert [spec.job_id for spec in specs] == JOB_NAMES, "任务清单变了：名字与顺序是这条守卫的锚点"
    assert len({id(spec.trigger) for spec in specs}) == len(specs), "两条任务共用了同一个触发器对象"

    for spec in specs:
        gap = slot.trigger_gap_seconds(spec.trigger)
        ttl = slot.slot_ttl_seconds(spec.trigger)
        assert slot.slot_violations(spec.job_id, spec.trigger) == []
        assert 0 < ttl < gap, f"{spec.job_id}: 窗口 {ttl}s 没落在间隔 {gap}s 之内"

    # 现量的七个数：动 MIN/MAX/FRACTION 任何一个都会撞这里，逼着人来确认射程。
    assert {spec.job_id: slot.slot_ttl_seconds(spec.trigger) for spec in specs} == {
        "reminder_check": 720,
        "new_jd_push": 900,
        "target_stats_refresh": 900,
        "operational_alert_evaluation": 60,
        "external_api_monthly_billing": 900,
        "job_embedding_sync": 360,
        "interview_evaluation_requeue": 120,
    }


def test_a_window_as_long_as_the_interval_is_a_violation():
    """反向证据：手写一个等于间隔的窗口，判据必须拒绝——那把锁会吃掉下一拍。"""
    trigger = IntervalTrigger(minutes=5)
    assert slot.slot_ttl_seconds(trigger) == 60
    assert slot.slot_violations("operational_alert_evaluation", trigger, ttl_seconds=60) == []
    assert slot.slot_violations("operational_alert_evaluation", trigger, ttl_seconds=300) == [
        "operational_alert_evaluation: 槽位窗口 300s 不小于间隔 300.0s，一把锁会把下一拍一起挡掉"
    ]
    assert slot.slot_violations("operational_alert_evaluation", trigger, ttl_seconds=0) == [
        "operational_alert_evaluation: 槽位窗口 0s 不是正数"
    ]


# ---------------------------------------------------------------- ④ 七条注册项真的走槽位


class RecorderScheduler:
    def __init__(self):
        self.jobs: dict[str, object] = {}

    def add_job(self, func, *, trigger=None, id=None, name=None, replace_existing=False):
        self.jobs[id] = func

    def start(self):
        return None

    def get_jobs(self):
        return list(self.jobs)


@pytest.fixture
def wired(monkeypatch):
    """把 `start_scheduler` 接到一台假调度器上，并把 7 个任务体换成探针。

    `scheduled_job_specs()` 是在 `start_scheduler()` 里按全局名取函数的，所以先 patch 再启动，
    注册进调度器的那个 `partial` 就绑到探针上——断言因此打在『真的走没走槽位』，不是打在配置表上。
    """
    recorder = RecorderScheduler()
    monkeypatch.setattr(sched, "get_scheduler", lambda: recorder)
    monkeypatch.setattr(sched.settings, "RUN_SCHEDULER", True)
    hits: list[str] = []
    spies = [name for name in dir(sched) if name.startswith("_run_")]
    assert len(spies) == len(JOB_NAMES), f"任务体数量与清单不齐：{spies}"
    for name in spies:
        monkeypatch.setattr(sched, name, partial(hits.append, name))
    sched.start_scheduler()
    return recorder, hits, spies


def test_every_registered_job_consults_the_slot(wired, monkeypatch, caplog):
    recorder, hits, spies = wired
    assert sorted(recorder.jobs) == sorted(JOB_NAMES)

    # 注册项里带的是"从触发器算出来的那个窗口"，不是某个手写的常数——一个全局 3600 会把
    # 5 分钟那条任务的下一拍直接吃掉，而上面所有断言都看不出这件事。
    by_id = {spec.job_id: spec for spec in sched.scheduled_job_specs()}
    for job_id, func in recorder.jobs.items():
        assert func.args[1] == slot.slot_ttl_seconds(by_id[job_id].trigger), f"{job_id} 的窗口不是推导出来的"

    denied = FakeRedis(deny=True)
    monkeypatch.setattr(slot, "get_slot_client", lambda: denied)
    with caplog.at_level(logging.INFO, logger="app.core.scheduler_slot"):
        for func in recorder.jobs.values():
            func()

    assert hits == [], "槽位说『别人领走了』而任务体还是跑了：包装根本没接进注册项"
    skipped = [r.getMessage() for r in caplog.records if "别的副本领走" in r.getMessage()]
    assert len(skipped) == 7, skipped

    granted = FakeRedis()
    monkeypatch.setattr(slot, "get_slot_client", lambda: granted)
    for func in recorder.jobs.values():
        func()
    assert sorted(hits) == sorted(spies), "放行那一拍没把七条都跑起来：注册项里有假的"
