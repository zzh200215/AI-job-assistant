"""Prometheus metrics registry and recording helpers."""

from __future__ import annotations

import math
import time
from threading import Lock
from typing import Any

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


def _configured_pool_capacity() -> int:
    """池子容量。按设置算，不借用 `configured_thread_limit()`：D215 的结论正是"这两个数今天相等，
    但那是巧合不是定义"。谁以后把线程顶改成 `20 − 后台并发`，这里仍要说池子的真话。
    """
    return max(1, int(settings.DB_POOL_SIZE)) + max(0, int(settings.DB_MAX_OVERFLOW))


def refresh_db_pool_gauges() -> None:
    """每次抓取前刷新池子三个数。`prometheus_client` 没有 GaugeFunc，set 是它的等价物。

    StaticPool（测试与内存 sqlite 那条路）没有 `checkedout()`/`overflow()`，这里写 **-1 而不是 0**：
    "看不见"和"看见是 0"是两件事，后者会让人以为池子空着。
    """
    db_pool_checked_out.set(_pool_stat("checkedout"))
    db_pool_overflow.set(_pool_stat("overflow"))
    db_pool_capacity.set(_configured_pool_capacity())


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


# ------------------------------------------------------------------- D218：把等待变成告警
#
# 判阈值不能用累计值：histogram 的桶只增不减，"p95 > 1s"对累计成立的话会在第一次越过之后
# 永远红。所以这里维护一份"上一次读取"的基线，报的是**两次读取之间**的形状。

_acquire_window_lock = Lock()
_acquire_window_state: dict[str, Any] | None = None


def _acquire_cumulative() -> tuple[dict[float, float], float, float]:
    """把那只 Histogram 读成 `{桶上界: 累计计数}`、总计数、总耗时。

    走 `collect()`（就是 /metrics 出口那套公开格式）而不是 `_sum`/`_bucket` 私有属性，也不在这里
    复制第二份 buckets 列表：桶改了这里自动跟着走。`float("+Inf")` 在 Python 里就是 `inf`。
    """
    buckets: dict[float, float] = {}
    count = 0.0
    total_seconds = 0.0
    for metric in db_pool_connection_acquire_seconds.collect():
        for sample in metric.samples:
            if sample.name.endswith("_bucket"):
                buckets[float(sample.labels["le"])] = float(sample.value)
            elif sample.name.endswith("_count"):
                count = float(sample.value)
            elif sample.name.endswith("_sum"):
                total_seconds = float(sample.value)
    return buckets, count, total_seconds


def _quantile_from_cumulative(bounds: list[float], cumulative: list[float], q: float) -> float | None:
    """桶内线性插值求分位数，和 Prometheus 的 `histogram_quantile` 同一个算法。

    落进 `+Inf` 那一档时报的是它的**下界**（"至少这么久"）——那一档没有上界，插不出值，
    假装能插会得到一个看起来精确的假数。
    """
    if not bounds or cumulative[-1] <= 0:
        return None
    total = cumulative[-1]
    rank = q * total
    before = 0.0
    lower = 0.0
    for bound, cum in zip(bounds, cumulative, strict=True):
        if cum >= rank:
            in_bucket = cum - before
            if math.isinf(bound):
                return lower
            if in_bucket <= 0:
                return bound
            value = lower + (bound - lower) * (rank - before) / in_bucket
            return round(value, 4)
        before = cum
        lower = bound
    return None


def db_pool_window() -> dict[str, Any]:
    """上一次读取之后的取连接等待形状，外加池子当下的占用——运维告警的输入。

    窗口 = **本函数两次调用之间**，不是写死的 5 分钟：调度器那一拍和管理员手点
    `POST /system/alerts/evaluate` 共用同一份基线，谁读走算谁的。第一次读、以及读到计数变小
    （进程重启或指标被重建）时没有基线可减，报的是自进程启动以来的累计，此时 `window_seconds`
    为 None，把这个不确定性说给告警读者看。

    射程要说清楚两件事：
    * 这根 histogram 是**进程内**的。编排跑 `redis_queue` 后端时在
      `scripts/run_orchestration_worker.py` 那个独立进程里（各自一份池子），那边没有调度器也没有
      `/metrics`，所以 worker 的排队不在本函数射程内。"API 进程 = 全部 HTTP 流量"这个前提由
      `tests/test_single_process_shape_is_pinned.py` 盯着（backend 只有 1 个进程时才绿）。
    * `over_pool_timeout_samples` 用的是"最后一个 `le <= DB_POOL_TIMEOUT` 的桶"，所以它报的是
      "等待超过 ≤30s 的最高那个桶界"。今天桶界正好有 30.0，与 `DB_POOL_TIMEOUT` 严丝合缝。
    """
    global _acquire_window_state
    buckets, count, total_seconds = _acquire_cumulative()
    bounds = sorted(buckets)
    now = time.monotonic()
    with _acquire_window_lock:
        previous = _acquire_window_state
        _acquire_window_state = {"buckets": dict(buckets), "count": count, "sum": total_seconds, "at": now}

    stale = (
        previous is None
        # 桶表变了就整份当"没有基线"：下面那条按基线取数的式子要求两边的桶一一对得上，
        # 而对不上是可能发生的（指标被重建、桶表被改）。调度器里抛 KeyError 的话，
        # 症状是每 5 分钟失败一次而告警表一个字不动——比漏报更糟。
        or set(buckets) != set(previous["buckets"])
        or count < previous["count"]
        or any(buckets[bound] < previous["buckets"][bound] for bound in bounds)
    )
    if stale:
        window_cumulative = [buckets[bound] for bound in bounds]
        sum_delta = total_seconds
        samples = int(count)
        window_seconds: float | None = None
    else:
        window_seconds = round(now - previous["at"], 3)
        window_cumulative = [max(0.0, buckets[bound] - previous["buckets"][bound]) for bound in bounds]
        sum_delta = max(0.0, total_seconds - previous["sum"])
        samples = int(max(0.0, count - previous["count"]))

    timeout_seconds = float(settings.DB_POOL_TIMEOUT)
    # 桶是累计的，所以"到 timeout 为止一共多少个"就是所有 bound <= timeout 里最大的那个累计值。
    covered = sum(cum for bound, cum in zip(bounds, window_cumulative, strict=True) if bound <= timeout_seconds)
    return {
        "samples": samples,
        "window_seconds": window_seconds,
        "p95_seconds": _quantile_from_cumulative(bounds, window_cumulative, 0.95),
        "avg_seconds": round(sum_delta / samples, 4) if samples else 0.0,
        "over_pool_timeout_samples": max(0, samples - int(covered)),
        "pool_timeout_seconds": timeout_seconds,
        "checked_out": _pool_stat("checkedout"),
        "overflow": _pool_stat("overflow"),
        "capacity": _configured_pool_capacity(),
    }


def reset_db_pool_window() -> None:
    """丢掉基线：下一次 `db_pool_window()` 从头算。测试用，生产没有调用点。"""
    global _acquire_window_state
    with _acquire_window_lock:
        _acquire_window_state = None


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
