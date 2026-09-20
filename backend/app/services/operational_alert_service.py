"""Evaluate, persist, and resolve administrator-facing operational alerts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentTask
from app.models.operational_alert import OperationalAlert
from app.models.prompt_trace import PromptTrace
from app.utils.time_helper import utc_now


def collect_operational_alerts(
    db: Session,
    *,
    model_runtime: dict[str, Any],
    queue_health: dict[str, Any],
    runtime_metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return the currently breached alert conditions without writing state."""
    now = utc_now()
    since = now - timedelta(minutes=settings.OPERATIONS_ALERT_WINDOW_MINUTES)
    alerts: list[dict[str, Any]] = []

    if not model_runtime.get("ready", False):
        alerts.append(
            _alert(
                "model_runtime_unavailable",
                "critical",
                "模型运行配置不可用",
                "LLM 或 Embedding 服务配置不完整，AI 相关请求可能无法完成。",
                {
                    "llm_mode": model_runtime.get("llm", {}).get("mode"),
                    "embedding_mode": model_runtime.get("embedding", {}).get("mode"),
                },
            )
        )

    if not queue_health.get("ok", False):
        alerts.append(
            _alert(
                "orchestration_queue_unavailable",
                "critical",
                "异步任务队列不可用",
                "编排队列当前无法连接，新的异步分析任务可能无法被消费。",
                {"backend": queue_health.get("backend"), "error": queue_health.get("error", "")[:200]},
            )
        )

    queue_length = int(queue_health.get("queue_length") or 0)
    if queue_length >= settings.OPERATIONS_ALERT_QUEUE_BACKLOG_THRESHOLD:
        alerts.append(
            _alert(
                "orchestration_queue_backlog",
                "warning",
                "异步任务队列积压",
                "待处理任务数量超过阈值，请检查 worker 容量和下游依赖。",
                {"queue_length": queue_length, "threshold": settings.OPERATIONS_ALERT_QUEUE_BACKLOG_THRESHOLD},
            )
        )

    failed_tasks = db.query(AgentTask).filter(AgentTask.status == "failed", AgentTask.end_time >= since).count()
    if failed_tasks >= settings.OPERATIONS_ALERT_TASK_FAILURE_THRESHOLD:
        alerts.append(
            _alert(
                "orchestration_task_failures",
                "warning",
                "工作流任务失败率异常",
                "近期失败的工作流任务数量超过阈值，请检查任务日志和模型依赖。",
                {
                    "failed_tasks": failed_tasks,
                    "window_minutes": settings.OPERATIONS_ALERT_WINDOW_MINUTES,
                    "threshold": settings.OPERATIONS_ALERT_TASK_FAILURE_THRESHOLD,
                },
            )
        )

    failed_llm_calls = (
        db.query(PromptTrace).filter(PromptTrace.status != "success", PromptTrace.created_at >= since).count()
    )
    if failed_llm_calls >= settings.OPERATIONS_ALERT_LLM_FAILURE_THRESHOLD:
        alerts.append(
            _alert(
                "llm_call_failures",
                "warning",
                "模型调用失败激增",
                "近期模型调用失败数量超过阈值，请检查供应商状态、限流和提示词追踪。",
                {
                    "failed_calls": failed_llm_calls,
                    "window_minutes": settings.OPERATIONS_ALERT_WINDOW_MINUTES,
                    "threshold": settings.OPERATIONS_ALERT_LLM_FAILURE_THRESHOLD,
                },
            )
        )

    # Degraded responses succeed, so they are invisible to the failure alert
    # above. They are the ones where a candidate sees template or truncated
    # content presented as model analysis.
    degraded_rows = (
        db.query(PromptTrace.response_source, func.count(PromptTrace.id))
        .filter(PromptTrace.degraded == 1, PromptTrace.status == "success", PromptTrace.created_at >= since)
        .group_by(PromptTrace.response_source)
        .all()
    )
    degraded_calls = sum(int(count or 0) for _, count in degraded_rows)
    by_source = {str(src): int(count) for src, count in degraded_rows}
    mock_calls = by_source.get("mock", 0)
    window = settings.OPERATIONS_ALERT_WINDOW_MINUTES
    if mock_calls >= settings.OPERATIONS_ALERT_LLM_MOCK_THRESHOLD:
        alerts.append(
            _alert(
                "llm_mock_responses_served",
                "critical",
                "已向用户返回 mock 模板内容",
                "有 AI 结果由本地 mock 模板生成而非模型输出。候选人侧不显示降级提示，"
                "请立即核对供应商配置、限流与 LLM_ALLOW_MOCK_FALLBACK。",
                {
                    "mock_calls": mock_calls,
                    "degraded_calls": degraded_calls,
                    "by_source": by_source,
                    "window_minutes": window,
                    "threshold": settings.OPERATIONS_ALERT_LLM_MOCK_THRESHOLD,
                },
            )
        )
    elif degraded_calls >= settings.OPERATIONS_ALERT_LLM_DEGRADED_THRESHOLD:
        alerts.append(
            _alert(
                "llm_degraded_responses",
                "warning",
                "模型应答降级",
                "近期有 AI 结果并非由配置的主模型生成（截断提示 / 备用模型），"
                "内容仍来自模型但质量可能下降，请以提示词追踪核对受影响功能。",
                {
                    "degraded_calls": degraded_calls,
                    "by_source": by_source,
                    "window_minutes": window,
                    "threshold": settings.OPERATIONS_ALERT_LLM_DEGRADED_THRESHOLD,
                },
            )
        )

    total_requests = int(runtime_metrics.get("total_requests") or 0)
    error_requests = int(runtime_metrics.get("error_requests") or 0)
    error_rate = error_requests / total_requests if total_requests else 0.0
    if (
        total_requests >= settings.OPERATIONS_ALERT_MIN_REQUESTS
        and error_rate >= settings.OPERATIONS_ALERT_HTTP_ERROR_RATE_THRESHOLD
    ):
        alerts.append(
            _alert(
                "http_error_rate_high",
                "warning",
                "接口错误率异常",
                "进程内 HTTP 错误率超过阈值，请结合请求日志定位异常接口。",
                {
                    "total_requests": total_requests,
                    "error_requests": error_requests,
                    "error_rate": round(error_rate, 4),
                    "threshold": settings.OPERATIONS_ALERT_HTTP_ERROR_RATE_THRESHOLD,
                },
            )
        )
    return alerts


def evaluate_operational_alerts(db: Session, **snapshot: dict[str, Any]) -> list[OperationalAlert]:
    """Upsert active conditions and mark no-longer-breached alerts resolved."""
    candidates = collect_operational_alerts(db, **snapshot)
    active_keys = {candidate["alert_key"] for candidate in candidates}
    now = utc_now()

    for candidate in candidates:
        alert = db.query(OperationalAlert).filter(OperationalAlert.alert_key == candidate["alert_key"]).one_or_none()
        if alert is None:
            db.add(OperationalAlert(**candidate, first_seen_at=now, last_seen_at=now))
            continue
        alert.severity = candidate["severity"]
        alert.title = candidate["title"]
        alert.description = candidate["description"]
        alert.context = candidate["context"]
        alert.last_seen_at = now
        alert.resolved_at = None
        alert.occurrences = int(alert.occurrences or 0) + 1
        if alert.status == "resolved":
            alert.status = "open"
            alert.acknowledged_at = None
            alert.acknowledged_by = None

    active_alerts = db.query(OperationalAlert).filter(OperationalAlert.resolved_at.is_(None)).all()
    for alert in active_alerts:
        if alert.alert_key not in active_keys:
            alert.status = "resolved"
            alert.resolved_at = now

    db.commit()
    return (
        db.query(OperationalAlert)
        .filter(OperationalAlert.resolved_at.is_(None))
        .order_by(OperationalAlert.last_seen_at.desc())
        .all()
    )


def _alert(alert_key: str, severity: str, title: str, description: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "alert_key": alert_key,
        "severity": severity,
        "status": "open",
        "title": title,
        "description": description,
        "context": context,
        "occurrences": 1,
    }
