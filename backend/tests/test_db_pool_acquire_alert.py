"""D218：连接池排队进运维告警（把 D217 那根 histogram 变成有人被叫醒的事）。

D215 量到的形状是"掺进 2 个后台作业，22 次取连接有 2 次排队、最差 11.73s"，而当时**没有**
任何一条规则会因此变红：池子只用到 16/20（不是贴住 capacity 那种形状），HTTP 错误率也没动。
这里盯的是那截等待本身，两条规则后果不同所以分开判：

* `db_pool_acquire_slow`（warning）—— p95 越过阈值：请求还在成功，但都在等。
* `db_pool_acquire_timeout`（critical）—— 有样本越过 `DB_POOL_TIMEOUT`：那几次抛的是
  TimeoutError，对应接口 500 / 后台作业 failed。

窗口是 `db_pool_window()` 两次读取之间的增量（拿累计桶判阈值会在第一次越过之后永远红）。
"""

from __future__ import annotations

import inspect
import threading
import time

from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from app.core.config import settings
from app.core.prometheus_metrics import db_pool_window, instrument_db_pool_connect, reset_db_pool_window
from app.services.operational_alert_service import collect_operational_alerts

_BENIGN = {
    "model_runtime": {"ready": True, "llm": {"mode": "live"}, "embedding": {"mode": "live"}},
    "queue_health": {"ok": True, "backend": "thread", "queue_length": 0},
    "runtime_metrics": {"total_requests": 0, "error_requests": 0},
}


def _window(**over) -> dict:
    """一个"什么都没发生"的窗口：20 根连接里占了 16 根，但等待全在最低的桶里。"""
    base = {
        "samples": 400,
        "window_seconds": 300.0,
        "p95_seconds": 0.0009,
        "avg_seconds": 0.002,
        "over_pool_timeout_samples": 0,
        "pool_timeout_seconds": 30.0,
        "checked_out": 16,
        "overflow": 6,
        "capacity": 20,
    }
    base.update(over)
    return base


def _alerts(db_session, db_pool: dict) -> dict[str, dict]:
    return {a["alert_key"]: a for a in collect_operational_alerts(db_session, db_pool=db_pool, **_BENIGN)}


def _snapshot_keys() -> list[str]:
    from app.api.system import build_operational_alert_snapshot

    return list(build_operational_alert_snapshot())


def test_a_queued_pool_alerts_on_the_wait(db_session):
    """p95 越过阈值 ⇒ 恰好一条 warning，且把占用比带进上下文（否则读者还得另开一张图）。"""
    found = _alerts(db_session, _window(p95_seconds=2.4))

    assert list(found) == ["db_pool_acquire_slow"], found
    alert = found["db_pool_acquire_slow"]
    assert alert["severity"] == "warning"
    assert alert["context"]["p95_seconds"] == 2.4
    assert alert["context"]["checked_out"] == 16
    assert alert["context"]["capacity"] == 20
    assert alert["context"]["threshold_seconds"] == settings.OPERATIONS_ALERT_DB_ACQUIRE_P95_SECONDS


def test_a_window_that_stays_under_the_threshold_is_quiet(db_session):
    """防空转：把"非零"当成唯一会红的值不算门。阈值 1.0 之下 0.9 必须不响，哪怕样本很多。"""
    assert _alerts(db_session, _window(p95_seconds=0.9, samples=5000)) == {}


def test_a_lone_slow_acquire_does_not_become_a_p95(db_session):
    """p95 是小样本统计量：窗口里只有 3 次取连接时它就等于那次的最大值，不构成门。"""
    thin = settings.OPERATIONS_ALERT_DB_ACQUIRE_MIN_SAMPLES - 1
    assert _alerts(db_session, _window(p95_seconds=9.0, samples=thin)) == {}


def test_a_wait_past_db_pool_timeout_is_critical(db_session):
    """越过 DB_POOL_TIMEOUT 一次就醒（critical），且不被 p95 那条互相吞掉。"""
    found = _alerts(db_session, _window(p95_seconds=45.0, over_pool_timeout_samples=1))

    assert set(found) == {"db_pool_acquire_slow", "db_pool_acquire_timeout"}
    assert found["db_pool_acquire_timeout"]["severity"] == "critical"
    assert found["db_pool_acquire_timeout"]["context"]["over_pool_timeout_samples"] == 1
    assert found["db_pool_acquire_timeout"]["context"]["pool_timeout_seconds"] == 30.0


def test_the_snapshot_builder_feeds_every_rule_input():
    """接线守卫：规则多一个必填入参而 builder 忘了给，调度器每一拍都会 TypeError。

    这条不判业务，只判两处键名还一致——本仓在"同一件事写两处然后分叉"上栽过不止一轮。
    """
    parameters = inspect.signature(collect_operational_alerts).parameters
    required = {
        name
        for name, parameter in parameters.items()
        if parameter.kind is parameter.KEYWORD_ONLY and parameter.default is parameter.empty
    }

    assert "db_pool" in required, "D218 的入参被改成可选了：builder 漏给时不会再有任何声音"
    assert (
        set(_snapshot_keys()) == required
    ), f"builder 给的是 {sorted(_snapshot_keys())}，规则要的是 {sorted(required)}"


def test_the_scheduler_path_survives_the_real_snapshot(db_session):
    """调度器那一拍走的就是 `evaluate_operational_alerts(db, **build_operational_alert_snapshot())`。

    上面那条接线守卫判的是键名一致，这条判真跑一遍：builder 现在从真池子里读窗口，规则要拿到的是
    一个真 dict 而不是缺参。分叉的症状是每 5 分钟一次 TypeError——日志里有，告警表里没有。
    """
    from app.api.system import build_operational_alert_snapshot
    from app.services.operational_alert_service import evaluate_operational_alerts

    rows = evaluate_operational_alerts(db_session, **build_operational_alert_snapshot())
    assert all(row.alert_key for row in rows)
    # 同一份输入再评估一次不该新增行（去重按 alert_key，D218 的两条也走这条路）
    again = evaluate_operational_alerts(db_session, **build_operational_alert_snapshot())
    assert {r.alert_key for r in again} == {r.alert_key for r in rows}


def test_the_real_instrument_reaches_the_rule(db_session, monkeypatch):
    """整条链一次跑通：包住池子 → 真排队 → 窗口读出增量 → 规则真响。

    上面几条喂的都是手搓的 dict；这条喂真 histogram，防的是"仪器和规则各自绿但中间断了一截"。
    池子故意 1 根、不给 overflow，另起线程去抢，就有一段确定的 0.3s 排队（D217 同款夹具）。
    """
    monkeypatch.setattr(settings, "OPERATIONS_ALERT_DB_ACQUIRE_MIN_SAMPLES", 1)
    monkeypatch.setattr(settings, "OPERATIONS_ALERT_DB_ACQUIRE_P95_SECONDS", 0.05)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=5,
        connect_args={"check_same_thread": False},
    )
    assert instrument_db_pool_connect(engine) is True

    reset_db_pool_window()
    db_pool_window()  # 取一次基线：下面那一段窗口里只该有本条自己造出来的样本

    held = engine.connect()
    held.execute(text("SELECT 1"))

    def racer():
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
        conn.close()

    thread = threading.Thread(target=racer)
    thread.start()
    time.sleep(0.3)
    held.close()
    thread.join()

    window = db_pool_window()
    assert window["samples"] >= 2, window
    assert window["window_seconds"] is not None, "读到的是累计而不是增量：窗口基线没生效"
    # 那截排队落在 (0.25, 0.5] 这一档，桶内插值只能报这一档里的数
    assert 0.25 <= window["p95_seconds"] <= 0.5, window
    assert window["over_pool_timeout_samples"] == 0, window

    found = _alerts(db_session, window)
    assert list(found) == ["db_pool_acquire_slow"], found
    assert found["db_pool_acquire_slow"]["context"]["samples"] == window["samples"]
