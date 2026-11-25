"""Evaluate, persist, and resolve administrator-facing operational alerts."""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentTask
from app.models.operational_alert import OperationalAlert
from app.models.prompt_trace import PromptTrace
from app.utils.time_helper import utc_now

logger = logging.getLogger(__name__)


def collect_operational_alerts(
    db: Session,
    *,
    model_runtime: dict[str, Any],
    queue_health: dict[str, Any],
    runtime_metrics: dict[str, Any],
    db_pool: dict[str, Any],
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

    # 队列 ok + 长度>0 + 死信 0 + 在途 0 是一种"看起来完全正常"的形状，而 D6 的实测现场
    # 正是它：两条任务在队列里排了 11 分钟，机器上根本没有 worker 进程。上面那三条规则
    # 一条都不会红（ping 通、长度 2 远低于阈值、死信为空）。所以必须有这一条，
    # 而且判据只能是"有没有活人"，不能是"队列连不连得上"。
    if queue_health.get("backend") == "redis_queue" and queue_health.get("worker_alive") is False:
        alerts.append(
            _alert(
                "orchestration_queue_no_worker",
                "critical",
                "异步任务队列没有消费者",
                "队列连得上、也没有积压告警，但没有 worker 在消费：此后创建的分析任务不会被执行"
                f"（当前 {queue_length} 条排在队列里）。"
                "启动 worker（`cd backend && ./.venv/Scripts/python.exe -m scripts.run_orchestration_worker`）"
                "后本告警自动恢复；在此之前 `/api/analysis/full` 会直接 503 拒绝接单。",
                {
                    "queue_length": queue_length,
                    "worker_alive": queue_health.get("worker_alive"),
                    "worker_last_seen_seconds": queue_health.get("worker_last_seen_seconds"),
                    "queue_name": queue_health.get("queue_name"),
                },
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

    # D218：连接池排队。两条分开判，因为后果不同——p95 高是"用户在等但会成功"，
    # 越过 `DB_POOL_TIMEOUT` 是"已经抛 TimeoutError 了"（路由 500 / 后台作业 failed）。
    # D215 实测掺进 2 个后台作业后最差等待 11.73s，而当时**没有任何一条规则会因此变红**：
    # 池子只用到 16/20（不是贴住 capacity 那种形状），HTTP 错误率也没动。这一对就是补那个盲区。
    pool_samples = int(db_pool.get("samples") or 0)
    p95 = db_pool.get("p95_seconds")
    pool_threshold = settings.OPERATIONS_ALERT_DB_ACQUIRE_P95_SECONDS
    if p95 is not None and pool_samples >= settings.OPERATIONS_ALERT_DB_ACQUIRE_MIN_SAMPLES and p95 >= pool_threshold:
        alerts.append(
            _alert(
                "db_pool_acquire_slow",
                "warning",
                "数据库连接池取连接排队",
                f"最近一段窗口里，取连接等待的 p95 已达 {p95}s（阈值 {pool_threshold}s）。"
                "请求还没失败但都在等：先核 DB_POOL_SIZE + DB_MAX_OVERFLOW 与同进程内的后台并发"
                "（rewrite / 逐题评分 / 面试 WS 抢的是同一口池子）。",
                {
                    "p95_seconds": p95,
                    "avg_seconds": db_pool.get("avg_seconds"),
                    "samples": pool_samples,
                    "window_seconds": db_pool.get("window_seconds"),
                    "checked_out": db_pool.get("checked_out"),
                    "capacity": db_pool.get("capacity"),
                    "threshold_seconds": pool_threshold,
                    "min_samples": settings.OPERATIONS_ALERT_DB_ACQUIRE_MIN_SAMPLES,
                },
            )
        )

    timeout_samples = int(db_pool.get("over_pool_timeout_samples") or 0)
    timeout_seconds = db_pool.get("pool_timeout_seconds")
    if timeout_samples >= settings.OPERATIONS_ALERT_DB_TIMEOUT_SAMPLES:
        alerts.append(
            _alert(
                "db_pool_acquire_timeout",
                "critical",
                "取连接等待越过池超时阈值",
                f"最近一段窗口里有 {timeout_samples} 次取连接等待超过 DB_POOL_TIMEOUT={timeout_seconds} —— "
                "那几次直接抛 TimeoutError，对应的是接口 500 或后台作业 failed，不是慢。"
                "先按 D215 那张表核对谁在占连接：rewrite / 逐题评分 / 面试 WS 与 HTTP 抢的是同一口池子。",
                {
                    "over_pool_timeout_samples": timeout_samples,
                    "pool_timeout_seconds": timeout_seconds,
                    "samples": pool_samples,
                    "p95_seconds": p95,
                    "window_seconds": db_pool.get("window_seconds"),
                    "checked_out": db_pool.get("checked_out"),
                    "capacity": db_pool.get("capacity"),
                    "threshold": settings.OPERATIONS_ALERT_DB_TIMEOUT_SAMPLES,
                },
            )
        )
    return alerts


def _post_alert_webhook(alert: dict[str, Any]) -> None:
    url = (settings.OPERATIONS_ALERT_WEBHOOK_URL or "").strip()
    if not url:
        return
    payload = {
        "event": "operational_alert.opened",
        "alert_key": alert["alert_key"],
        "severity": alert["severity"],
        "title": alert["title"],
        "description": alert["description"],
        "context": alert.get("context") or {},
        "occurrences": alert.get("occurrences", 1),
        "first_seen_at": alert.get("first_seen_at"),
        "last_seen_at": alert.get("last_seen_at"),
        "app_env": settings.APP_ENV,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("User-Agent", "career-signal-alerts/1.0")
    try:
        with urllib.request.urlopen(req, timeout=settings.OPERATIONS_ALERT_WEBHOOK_TIMEOUT_SECONDS) as resp:
            resp.read()
    except Exception as exc:  # noqa: BLE001 - 外发失败不能把已落库的告警评估拖崩
        logger.warning("Operational alert webhook failed: %s", exc)


def evaluate_operational_alerts(db: Session, **snapshot: dict[str, Any]) -> list[OperationalAlert]:
    """Upsert active conditions and mark no-longer-breached alerts resolved."""
    candidates = collect_operational_alerts(db, **snapshot)
    active_keys = {candidate["alert_key"] for candidate in candidates}
    now = utc_now()
    new_alerts: list[dict[str, Any]] = []

    for candidate in candidates:
        alert = db.query(OperationalAlert).filter(OperationalAlert.alert_key == candidate["alert_key"]).one_or_none()
        if alert is None:
            db.add(OperationalAlert(**candidate, first_seen_at=now, last_seen_at=now))
            new_alerts.append(
                {
                    **candidate,
                    "first_seen_at": now.isoformat(),
                    "last_seen_at": now.isoformat(),
                    "occurrences": 1,
                }
            )
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
    for new_alert in new_alerts:
        _post_alert_webhook(new_alert)
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
