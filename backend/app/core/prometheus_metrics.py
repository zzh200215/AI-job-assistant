"""Prometheus metrics registry and recording helpers."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

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


def record_http_request(method: str, status_code: int, path: str, duration_seconds: float) -> None:
    http_requests_total.labels(method=method, status=str(status_code), path=path).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration_seconds)


def record_llm_request(provider: str, model: str, duration_seconds: float) -> None:
    llm_requests_total.labels(provider=provider, model=model).inc()
    llm_request_duration_seconds.labels(provider=provider, model=model).observe(duration_seconds)


def record_llm_error(provider: str, model: str, error_type: str) -> None:
    llm_errors_total.labels(provider=provider, model=model, error_type=error_type).inc()


def record_llm_degraded_response(provider: str, model: str, response_source: str) -> None:
    llm_degraded_responses_total.labels(
        provider=provider, model=model, response_source=response_source
    ).inc()


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
    return generate_latest(REGISTRY), 200, {"Content-Type": CONTENT_TYPE_LATEST}
