"""Prometheus metrics registry and recording helpers."""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from app.core.config import settings

REGISTRY = CollectorRegistry()

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "status", "path"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY,
)

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests",
    ["provider", "model"],
    registry=REGISTRY,
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration in seconds",
    ["provider", "model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY,
)

llm_errors_total = Counter(
    "llm_errors_total",
    "Total LLM errors",
    ["provider", "model", "error_type"],
    registry=REGISTRY,
)

llm_degraded_responses_total = Counter(
    "llm_degraded_responses_total",
    "LLM responses that did not come from the configured primary model",
    ["provider", "model", "response_source"],
    registry=REGISTRY,
)

recommend_vector_degraded_total = Counter(
    "recommend_vector_degraded_total",
    "Recommendation requests where the embedding channel was unavailable and ranking fell back to rules",
    ["reason"],
    registry=REGISTRY,
)

prompt_trace_write_failures_total = Counter(
    "prompt_trace_write_failures_total",
    "Prompt trace writes that failed; while these are non-zero the trace table is NOT a reliable audit trail",
    ["stage"],
    registry=REGISTRY,
)

embedding_requests_total = Counter(
    "embedding_requests_total",
    "Total embedding API requests",
    ["provider", "model"],
    registry=REGISTRY,
)

embedding_texts_total = Counter(
    "embedding_texts_total",
    "Total texts sent to embedding API",
    ["provider", "model"],
    registry=REGISTRY,
)

embedding_errors_total = Counter(
    "embedding_errors_total",
    "Total embedding API errors",
    ["provider", "model", "error_type"],
    registry=REGISTRY,
)

sync_jobs_total = Counter(
    "sync_jobs_total",
    "Total job data source sync jobs",
    ["source_type", "status"],
    registry=REGISTRY,
)

sync_job_duration_seconds = Histogram(
    "sync_job_duration_seconds",
    "Job data source sync duration in seconds",
    ["source_type"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    registry=REGISTRY,
)

sync_errors_total = Counter(
    "sync_errors_total",
    "Total job data source sync errors",
    ["source_type", "error_type"],
    registry=REGISTRY,
)

auth_login_attempts_total = Counter(
    "auth_login_attempts_total",
    "Total login attempts",
    ["status"],
    registry=REGISTRY,
)

auth_rate_limited_total = Counter(
    "auth_rate_limited_total",
    "Total rate limited requests",
    ["path"],
    registry=REGISTRY,
)

# D215：连接池那三个数。量出来的是"anyio 那 20 根顶 = 池子"这个等式只在**只有 HTTP 用它**时成立——
# 同进程里 rewrite(2) + 逐题评分(2) + 面试 WS（一步一根，D213 之后一步结束就还）抢的是同一口
# `DB_POOL_SIZE + DB_MAX_OVERFLOW`。实测 20 根 HTTP 单独跑是 0 个排队，掺进 2 个后台作业就变成
# 2/22 排队、最差 11.73s。要不要动尺寸，得看真并发下这两个数贴得多近，而不是再推一轮。
db_pool_checked_out = Gauge(
    "db_pool_checked_out",
    "DB connections checked out now; -1 means this pool class does not report it (StaticPool on "
    "sqlite) — it is not the same as 0",
    registry=REGISTRY,
)
db_pool_overflow = Gauge(
    "db_pool_overflow",
    "DB pool overflow counter (negative = spare capacity inside DB_POOL_SIZE); -1 = not reported " "by this pool class",
    registry=REGISTRY,
)
db_pool_capacity = Gauge(
    "db_pool_capacity",
    "DB_POOL_SIZE + DB_MAX_OVERFLOW — the number core/threadpool.py pins the HTTP thread limit to",
    registry=REGISTRY,
)

# D217：那三根 Gauge 只说得出"贴没贴近 capacity"，说不出"等了多久"（D215 的 11.73s 就是这么量的，
# 一次性脚本）。排队发生在 `Pool.connect()` 里面，SQLAlchemy 2.0 没有公开的"取连接耗时"事件，
# 所以在 `core/database.py` 建完 engine 后把它包一层（`instrument_db_pool_connect`）。
# `le="30"` 那一档是有意义的：`DB_POOL_TIMEOUT=30`，越过它就是 `TimeoutError`（路由 500 / 作业 failed）。
db_pool_connection_acquire_seconds = Histogram(
    "db_pool_connection_acquire_seconds",
    "Time to hand a thread a DB connection: queue wait when the pool is saturated, plus connect "
    "handshake when it is not",
    buckets=[0.001, 0.005, 0.025, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    registry=REGISTRY,
)


def _pool_stat(name: str) -> int:
    # 惰性 import 是有用的而不是洁癖：`app.core.database` 在建 engine 时会读 settings，
    # 让指标模块去顶层拉它，等于把"导入 metrics"变成"导入数据库"。
    from app.core.database import engine

    fn = getattr(engine.pool, name, None)
    return int(fn()) if callable(fn) else -1


def refresh_db_pool_gauges() -> None:
    """每次抓取前刷新池子三个数。`prometheus_client` 没有 GaugeFunc，set 是它的等价物。

    StaticPool（测试与内存 sqlite 那条路）没有 `checkedout()`/`overflow()`，这里写 **-1 而不是 0**：
    "看不见"和"看见是 0"是两件事，后者会让人以为池子空着。
    """
    db_pool_checked_out.set(_pool_stat("checkedout"))
    db_pool_overflow.set(_pool_stat("overflow"))
    # 容量按设置算，不借用 `configured_thread_limit()`：D215 的结论正是"这两个数今天相等，
    # 但那是巧合不是定义"。谁以后把线程顶改成 `20 − 后台并发`，这根仍要说池子的真话。
    db_pool_capacity.set(max(1, int(settings.DB_POOL_SIZE)) + max(0, int(settings.DB_MAX_OVERFLOW)))


def instrument_db_pool_connect(engine) -> bool:
    """把 `engine.pool.connect` 包一层，记下"拿到一根连接要多久"。返回 False = 已经包过了。

    为什么是 `Pool.connect`：SQLAlchemy 2.0 的 `Pool` 已经没有公开的 `checkout()`（现取报
    `'QueuePool' object has no attribute 'checkout'`），而 `Pool.connect()` 是 Connection 取
    `_ConnectionFairy` 的公开入口，排队就在它里面。实测（`pool_size=1` 的小池子，另起线程去抢）：
    空闲时 0.0003s、被占住时 **0.3008s**——多出来的那一截正是 D215 用一次性脚本量的那种等待。

    为什么要幂等：`core/database.py` 只在导入时调一次，但测试会重复调；嵌套两层会把同一次等待
    记两遍，把整个分布往右推——那是比"没有这个指标"更糟的结果。
    """
    pool = getattr(engine, "pool", None)
    original = getattr(pool, "connect", None)
    if original is None or getattr(original, "__pool_timing__", False):
        return False

    def timed_connect(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            # 拿不到也要记：`pool_timeout` 到点抛的是 TimeoutError，那正是最该在图上看见的一档
            db_pool_connection_acquire_seconds.observe(time.perf_counter() - started)

    timed_connect.__pool_timing__ = True
    pool.connect = timed_connect
    return True


def record_http_request(method: str, status_code: int, path: str, duration_seconds: float) -> None:
    http_requests_total.labels(method=method, status=str(status_code), path=path).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration_seconds)


def record_llm_request(provider: str, model: str, duration_seconds: float) -> None:
    llm_requests_total.labels(provider=provider, model=model).inc()
    llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration_seconds)


def record_llm_error(provider: str, model: str, error_type: str) -> None:
    llm_errors_total.labels(provider=provider, model=model, error_type=error_type).inc()


def record_llm_degraded_response(provider: str, model: str, response_source: str) -> None:
    llm_degraded_responses_total.labels(provider=provider, model=model, response_source=response_source).inc()


def record_recommend_vector_degraded(reason: str) -> None:
    recommend_vector_degraded_total.labels(reason=reason).inc()


def record_prompt_trace_write_failure(stage: str) -> None:
    prompt_trace_write_failures_total.labels(stage=stage).inc()


def record_embedding_request(provider: str, model: str, text_count: int) -> None:
    embedding_requests_total.labels(provider=provider, model=model).inc()
    embedding_texts_total.labels(provider=provider, model=model).inc(text_count)


def record_embedding_error(provider: str, model: str, error_type: str) -> None:
    embedding_errors_total.labels(provider=provider, model=model, error_type=error_type).inc()


def record_sync_job(source_type: str, status: str, duration_seconds: float) -> None:
    sync_jobs_total.labels(source_type=source_type, status=status).inc()
    sync_job_duration_seconds.labels(source_type=source_type).observe(duration_seconds)


def record_sync_error(source_type: str, error_type: str) -> None:
    sync_errors_total.labels(source_type=source_type, error_type=error_type).inc()


def record_login_attempt(status: str) -> None:
    auth_login_attempts_total.labels(status=status).inc()


def record_rate_limited(path: str) -> None:
    auth_rate_limited_total.labels(path=path).inc()


def get_metrics_response() -> tuple:
    refresh_db_pool_gauges()
    return generate_latest(REGISTRY), 200, {"Content-Type": CONTENT_TYPE_LATEST}
