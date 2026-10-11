"""Tests for Prometheus metrics recording."""

from __future__ import annotations

import contextlib
import math

import pytest

from app.core.prometheus_metrics import (
    REGISTRY,
    get_metrics_response,
    record_embedding_error,
    record_embedding_request,
    record_http_request,
    record_llm_error,
    record_llm_request,
    record_login_attempt,
    record_rate_limited,
    record_sync_error,
    record_sync_job,
)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset all metrics before each test."""
    # Clear all metrics by recreating the registry
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        with contextlib.suppress(Exception):
            REGISTRY.unregister(collector)

    # Re-import to re-register
    import importlib

    import app.core.prometheus_metrics as metrics_module

    importlib.reload(metrics_module)

    yield


def test_record_http_request():
    """Verify HTTP request metrics are recorded."""
    from app.core.prometheus_metrics import http_request_duration_seconds, http_requests_total

    record_http_request(method="GET", status_code=200, path="/api/test", duration_seconds=0.123)

    # Check counter
    metric = http_requests_total.labels(method="GET", status="200", path="/api/test")
    assert metric._value.get() == 1.0

    # Check histogram
    hist_metric = http_request_duration_seconds.labels(method="GET", path="/api/test")
    assert hist_metric._sum.get() == pytest.approx(0.123, rel=1e-3)


def test_record_llm_request_and_error():
    """Verify LLM request and error metrics are recorded."""
    from app.core.prometheus_metrics import llm_errors_total, llm_requests_total

    record_llm_request(provider="openai", model="gpt-4", duration_seconds=1.5)
    record_llm_error(provider="openai", model="gpt-4", error_type="TimeoutError")

    req_metric = llm_requests_total.labels(provider="openai", model="gpt-4")
    assert req_metric._value.get() == 1.0

    err_metric = llm_errors_total.labels(provider="openai", model="gpt-4", error_type="TimeoutError")
    assert err_metric._value.get() == 1.0


def test_record_embedding_request_and_error():
    """Verify embedding request and error metrics are recorded."""
    from app.core.prometheus_metrics import embedding_errors_total, embedding_requests_total, embedding_texts_total

    record_embedding_request(provider="openai", model="text-embedding-3-small", text_count=10)
    record_embedding_error(provider="openai", model="text-embedding-3-small", error_type="AuthError")

    req_metric = embedding_requests_total.labels(provider="openai", model="text-embedding-3-small")
    assert req_metric._value.get() == 1.0

    text_metric = embedding_texts_total.labels(provider="openai", model="text-embedding-3-small")
    assert text_metric._value.get() == 10.0

    err_metric = embedding_errors_total.labels(
        provider="openai", model="text-embedding-3-small", error_type="AuthError"
    )
    assert err_metric._value.get() == 1.0


def test_record_sync_job_and_error():
    """Verify sync job and error metrics are recorded."""
    from app.core.prometheus_metrics import sync_errors_total, sync_job_duration_seconds, sync_jobs_total

    record_sync_job(source_type="api", status="success", duration_seconds=5.0)
    record_sync_error(source_type="api", error_type="timeout")

    job_metric = sync_jobs_total.labels(source_type="api", status="success")
    assert job_metric._value.get() == 1.0

    duration_metric = sync_job_duration_seconds.labels(source_type="api")
    assert duration_metric._sum.get() == pytest.approx(5.0, rel=1e-3)

    err_metric = sync_errors_total.labels(source_type="api", error_type="timeout")
    assert err_metric._value.get() == 1.0


def test_record_login_and_rate_limit():
    """Verify login attempt and rate limit metrics are recorded."""
    from app.core.prometheus_metrics import auth_login_attempts_total, auth_rate_limited_total

    record_login_attempt(status="success")
    record_login_attempt(status="failed")
    record_rate_limited(path="/auth/login")

    success_metric = auth_login_attempts_total.labels(status="success")
    assert success_metric._value.get() == 1.0

    failed_metric = auth_login_attempts_total.labels(status="failed")
    assert failed_metric._value.get() == 1.0

    rate_metric = auth_rate_limited_total.labels(path="/auth/login")
    assert rate_metric._value.get() == 1.0


def test_get_metrics_response():
    """Verify get_metrics_response returns valid Prometheus format."""
    data, status_code, headers = get_metrics_response()

    assert status_code == 200
    assert "Content-Type" in headers
    assert "text/plain" in headers["Content-Type"] or "openmetrics" in headers["Content-Type"]
    assert isinstance(data, bytes)
    assert len(data) > 0

    # Verify it contains some metric names
    content = data.decode("utf-8")
    assert "http_requests_total" in content or "python_info" in content


# ------------------------------------------------------------- D216：连接池那三个数（接 D215 的实测）


def test_db_pool_gauges_read_the_live_pool(monkeypatch):
    from prometheus_client import generate_latest

    from app.core import prometheus_metrics as m
    from app.core.config import settings

    class _ReportingPool:
        def checkedout(self):
            return 7

        def overflow(self):
            return -3

    class _Engine:
        pool = _ReportingPool()

    monkeypatch.setattr("app.core.database.engine", _Engine())
    m.refresh_db_pool_gauges()

    assert m.db_pool_checked_out._value.get() == 7
    assert m.db_pool_overflow._value.get() == -3
    assert m.db_pool_capacity._value.get() == settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW
    # 出口真吐得出来，不是只在 Python 里看得见
    assert b"db_pool_checked_out 7.0" in generate_latest(m.REGISTRY)


def test_a_pool_that_cannot_report_is_minus_one_not_zero():
    """测试库是 StaticPool——它**没有** `checkedout()`。

    写 0 会让人以为"池子空着"，那是 D215 那张表最不该被读错的一种误读，所以看不见必须留 -1。
    """
    from app.core import prometheus_metrics as m

    m.refresh_db_pool_gauges()

    assert m.db_pool_checked_out._value.get() == -1
    assert m.db_pool_overflow._value.get() == -1
    assert m.db_pool_capacity._value.get() > 0  # 容量来自设置，任何池类都该报得出


def test_the_scrape_path_refreshes_the_pool_gauges(monkeypatch):
    """不挂在抓取路径上，这三个数就是死的——所以这条测的是"每次 scrape 真的去读池子"。"""
    from app.core import prometheus_metrics as m

    seen = []
    monkeypatch.setattr(m, "refresh_db_pool_gauges", lambda: seen.append(1))

    _, status_code, _ = m.get_metrics_response()

    assert status_code == 200
    assert seen == [1]


# ------------------------------------------------------------------- D217：取连接等了多久


def test_production_engine_is_wrapped_at_import():
    """包在 `core/database.py` 建 engine 之后：谁把那行删了，指标就悄悄变成永远 0。"""
    import app.core.database as database
    from app.core import prometheus_metrics as m

    assert m.instrument_db_pool_connect(database.engine) is False, "生产 engine 没被包上"
    assert getattr(database.engine.pool.connect, "__pool_timing__", False) is True


def test_pool_connect_wrap_records_the_queue_wait():
    """仪器得先自证：包上之后，被占住的那次 `Pool.connect` 要真记下一截等待。

    没有这条，那个 histogram 可能只是个永远为 0 的装饰。池子故意设成 1 根、不给 overflow，
    另起一个线程去抢，就能造出一段确定的排队。
    """
    import threading
    import time

    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import QueuePool

    from app.core import prometheus_metrics as m

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=5,
        connect_args={"check_same_thread": False},
    )
    assert m.instrument_db_pool_connect(engine) is True
    # 幂等：嵌套两层会把同一次等待记两遍，把整个分布往右推
    assert m.instrument_db_pool_connect(engine) is False

    def samples():
        # 直读 Histogram 的内部属性不稳（`_count` 就没有），注册表的公开读法才靠谱
        return (
            m.REGISTRY.get_sample_value("db_pool_connection_acquire_seconds_count") or 0.0,
            m.REGISTRY.get_sample_value("db_pool_connection_acquire_seconds_sum") or 0.0,
        )

    before_count, _ = samples()

    # 先把那唯一一根连接占住：池子 size=1、overflow=0，第二个线程只能排队
    held = engine.connect()
    held.execute(text("SELECT 1"))
    _, baseline_sum = samples()

    def racer():
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
        conn.close()

    thread = threading.Thread(target=racer)
    thread.start()
    time.sleep(0.3)
    held.close()
    thread.join()

    after_count, after_sum = samples()
    observed = after_count - before_count
    # 等待那一截从"占住之后"的基线算起：第一次 acquire（占住那根）本身是快的，
    # 混进来会让这条断言在"完全没量到排队"时也能勉强通过。
    waited = after_sum - baseline_sum
    assert observed >= 2, f"包住之后没记下任何样本（observed={observed}）"
    assert waited >= 0.29, f"没量到那截 0.3 秒的排队：sum 只增加了 {waited:.4f}s"


# ------------------------------------------------- D218：告警要的是"两次读取之间"而不是累计


def test_the_window_is_the_delta_between_reads():
    """累计桶判阈值会在第一次越过之后永远红——这条盯的就是"不许 latch"。

    第二段时间里只有那发 5s 的等待，p95 必须回到 5s 那一档，而不是继续报上一段的结果。
    """
    from app.core import prometheus_metrics as m

    m.reset_db_pool_window()
    for _ in range(3):
        m.db_pool_connection_acquire_seconds.observe(0.0004)
    first = m.db_pool_window()

    m.db_pool_connection_acquire_seconds.observe(5.0)
    second = m.db_pool_window()

    assert first["samples"] == 3, first
    assert first["window_seconds"] is None, "第一次读没有基线，窗口长度要如实报 None"
    assert second["samples"] == 1, second
    assert second["window_seconds"] is not None and second["window_seconds"] >= 0
    assert second["p95_seconds"] > first["p95_seconds"], (first, second)
    assert 2.5 < second["p95_seconds"] <= 5.0, second


def test_a_rebuilt_histogram_does_not_read_negative(monkeypatch):
    """计数器变小 = 进程重启/指标被重建（`REGISTRY` 会被测试与热重载换掉）。

    这时候没有东西可减：把累计当增量报，而不是让 p95 变成 None 之外的任何负数形状。
    """
    from prometheus_client import Histogram

    from app.core import prometheus_metrics as m

    m.reset_db_pool_window()
    for _ in range(4):
        m.db_pool_connection_acquire_seconds.observe(0.4)
    m.db_pool_window()  # 基线里存下 4 个样本

    old = m.db_pool_connection_acquire_seconds
    # 桶界从旧的那根读出来，不在测试里抄第二份表（抄了就会和承重的那份分叉）
    bounds = [
        float(sample.labels["le"])
        for metric in old.collect()
        for sample in metric.samples
        if sample.name.endswith("_bucket")
    ]
    bounds = [bound for bound in bounds if math.isfinite(bound)]
    fresh = Histogram("db_pool_connection_acquire_seconds", "replacement", buckets=bounds, registry=None)
    fresh.observe(0.4)
    monkeypatch.setattr(m, "db_pool_connection_acquire_seconds", fresh)

    window = m.db_pool_window()
    assert window["samples"] == 1, window
    assert 0.25 < window["p95_seconds"] <= 0.5, window


def test_a_changed_bucket_table_is_treated_as_no_baseline(monkeypatch):
    """桶表变了（改桶、指标被重建）时不许 KeyError。

    这一读挂在调度器上：那里抛异常的后果是每 5 分钟静默失败一次、告警表一个字不动，
    比漏报一条告警糟得多。
    """
    from prometheus_client import Histogram

    from app.core import prometheus_metrics as m

    m.reset_db_pool_window()
    m.db_pool_connection_acquire_seconds.observe(0.4)
    m.db_pool_window()  # 基线里存下原来那张桶表

    old = m.db_pool_connection_acquire_seconds
    bounds = [
        float(sample.labels["le"])
        for metric in old.collect()
        for sample in metric.samples
        if sample.name.endswith("_bucket") and sample.labels["le"] != "+Inf"
    ]
    widened = Histogram(
        "db_pool_connection_acquire_seconds",
        "wider table",
        buckets=[*bounds, 120.0],
        registry=None,
    )
    for _ in range(5):
        widened.observe(0.4)
    monkeypatch.setattr(m, "db_pool_connection_acquire_seconds", widened)

    window = m.db_pool_window()
    assert window["samples"] == 5, window  # 没有基线可减 ⇒ 累计即增量
    assert window["window_seconds"] is None, window


def test_only_waits_past_db_pool_timeout_land_in_the_timeout_count():
    """`over_pool_timeout_samples` 的边界：29s 不算越线，45s 算。

    45s 落在 (30, 60] 那一档，而这一档的下界已经高于 `DB_POOL_TIMEOUT=30` —— 这正是"越过池超时
    的那几次"，判据取的是"最后一个 le <= 30 的桶之上"，所以桶表里 30.0 这一档是承重的。
    """
    from app.core import prometheus_metrics as m

    m.reset_db_pool_window()
    m.db_pool_connection_acquire_seconds.observe(29.0)
    assert m.db_pool_window()["over_pool_timeout_samples"] == 0

    m.reset_db_pool_window()
    m.db_pool_connection_acquire_seconds.observe(45.0)
    window = m.db_pool_window()
    assert window["over_pool_timeout_samples"] == 1, window
    assert window["pool_timeout_seconds"] == 30.0, window


def test_a_quantile_inside_the_open_bucket_reports_its_lower_bound():
    """+Inf 那一档没有上界：报下界（"至少 60s"）而不是假装能插出一个精确值。"""
    from app.core import prometheus_metrics as m

    m.reset_db_pool_window()
    m.db_pool_connection_acquire_seconds.observe(500.0)
    window = m.db_pool_window()

    assert window["p95_seconds"] == 60.0, window
    assert window["over_pool_timeout_samples"] == 1, window
