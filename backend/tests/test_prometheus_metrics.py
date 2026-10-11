"""Tests for Prometheus metrics recording."""

from __future__ import annotations

import contextlib

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
