"""Helpers for deriving async task progress and task center summaries."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.agent import AgentStepLog, AgentTask
from app.models.agent_run import AgentMessage, AgentRun
from app.orchestration.protocol import get_step_label, normalize_step_name, normalize_step_status, normalize_task_status
from app.utils.time_helper import utc_now

_TERMINAL_STEP_STATUSES = {"completed", "failed", "skipped"}


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _normalize_datetime(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _duration_ms(task: AgentTask) -> int | None:
    if not task.start_time:
        return None
    start = _normalize_datetime(task.start_time)
    end = _normalize_datetime(task.end_time) or utc_now()
    if start is None:
        return None
    return max(int((end - start).total_seconds() * 1000), 0)


def build_task_progress(task: AgentTask, steps: Iterable[AgentStepLog]) -> dict:
    step_rows = list(steps)
    counters = {
        "total": 0,
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0,
    }
    current_step = None
    latest_step = None

    for step in step_rows:
        latest_step = step
        status = normalize_step_status(step.status)
        counters["total"] += 1
        counters[status] = counters.get(status, 0) + 1

        if status == "running":
            current_step = step

    if current_step is None:
        for step in step_rows:
            status = normalize_step_status(step.status)
            if status not in _TERMINAL_STEP_STATUSES:
                current_step = step
                break

    if current_step is None:
        current_step = latest_step

    plan_steps = len(task.plan or [])
    total_steps = max(counters["total"], plan_steps)
    finished_steps = counters["completed"] + counters["failed"] + counters["skipped"]
    task_status = normalize_task_status(task.status)

    if task_status in {"completed", "partial"}:
        progress_percent = 100
    elif total_steps <= 0:
        progress_percent = 0
    else:
        progress_percent = int(round((finished_steps / total_steps) * 100))

    return {
        "task_status": task_status,
        "progress_percent": progress_percent,
        "step_counts": counters,
        "total_steps": total_steps,
        "finished_steps": finished_steps,
        "current_step": {
            "name": normalize_step_name(current_step.step_name),
            "label": get_step_label(normalize_step_name(current_step.step_name)),
            "status": normalize_step_status(current_step.status),
            "step_index": current_step.step_index,
            "started_at": _iso(current_step.started_at),
            "completed_at": _iso(current_step.completed_at),
        }
        if current_step
        else None,
        "duration_ms": _duration_ms(task),
        "started_at": _iso(task.start_time),
        "ended_at": _iso(task.end_time),
    }


def _usage_from_steps(steps: Iterable[AgentStepLog]) -> dict:
    tokens = 0
    cost = 0.0
    for step in steps:
        output = step.output_data or {}
        if not isinstance(output, dict):
            continue
        usage = output.get("_usage") or {}
        if not isinstance(usage, dict):
            continue
        tokens += int(usage.get("total_tokens") or usage.get("tokens_used") or 0)
        cost += float(usage.get("cost_cents") or 0.0)
    return {"tokens_used": tokens, "cost_cents": cost}


def serialize_task(task: AgentTask, steps: Iterable[AgentStepLog]) -> dict:
    step_rows = list(steps)
    payload = task.to_dict()
    payload["progress"] = build_task_progress(task, step_rows)
    usage = (task.final_report or {}).get("_usage") if isinstance(task.final_report, dict) else None
    payload["usage"] = usage or _usage_from_steps(step_rows)
    return payload


def _usage_by_task(db: Session, tasks: list[AgentTask]) -> dict[int, dict]:
    if not tasks:
        return {}
    task_ids = [task.id for task in tasks]
    rows = (
        db.query(
            AgentRun.user_request,
            func.coalesce(func.sum(AgentMessage.tokens_used), 0),
            func.coalesce(func.sum(AgentMessage.cost_cents), 0.0),
        )
        .join(AgentMessage, AgentMessage.run_id == AgentRun.id)
        .filter(AgentRun.user_request.in_([f"task:{task_id}" for task_id in task_ids]))
        .group_by(AgentRun.user_request)
        .all()
    )
    usage = {}
    for marker, tokens, cost in rows:
        try:
            task_id = int(str(marker).split(":", 1)[1])
        except (IndexError, ValueError):
            continue
        usage[task_id] = {"tokens_used": int(tokens or 0), "cost_cents": float(cost or 0.0)}
    return usage


def list_user_tasks(
    db: Session,
    *,
    user_id: int,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    query = db.query(AgentTask).filter(AgentTask.user_id == user_id)
    if status:
        query = query.filter(AgentTask.status == status)

    total = query.count()
    tasks = (
        query.order_by(AgentTask.create_time.desc(), AgentTask.id.desc())
        .offset(max(offset, 0))
        .limit(max(min(limit, 100), 1))
        .all()
    )
    task_ids = [task.id for task in tasks]
    step_rows = (
        db.query(AgentStepLog)
        .filter(AgentStepLog.task_id.in_(task_ids))
        .order_by(AgentStepLog.task_id.asc(), AgentStepLog.step_index.asc())
        .all()
        if task_ids
        else []
    )

    steps_by_task: dict[int, list[AgentStepLog]] = {}
    for step in step_rows:
        steps_by_task.setdefault(step.task_id, []).append(step)

    usage_by_task = _usage_by_task(db, tasks)
    items = []
    for task in tasks:
        item = serialize_task(task, steps_by_task.get(task.id, []))
        if task.id in usage_by_task:
            item["usage"] = usage_by_task[task.id]
        items.append(item)
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_task_with_progress(db: Session, *, task_id: int, user_id: int) -> tuple[AgentTask | None, dict | None]:
    task = db.query(AgentTask).filter(AgentTask.id == task_id, AgentTask.user_id == user_id).first()
    if not task:
        return None, None

    steps = db.query(AgentStepLog).filter(AgentStepLog.task_id == task_id).order_by(AgentStepLog.step_index.asc()).all()
    payload = serialize_task(task, steps)
    usage = _usage_by_task(db, [task]).get(task.id)
    if usage:
        payload["usage"] = usage
    return task, payload


def get_user_task_summary(db: Session, *, user_id: int) -> dict:
    rows = (
        db.query(AgentTask.status, func.count(AgentTask.id))
        .filter(AgentTask.user_id == user_id)
        .group_by(AgentTask.status)
        .all()
    )

    counts = {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "partial": 0,
        "cancelled": 0,
    }
    for raw_status, total in rows:
        counts[normalize_task_status(raw_status)] = total

    recent = list_user_tasks(db, user_id=user_id, limit=5, offset=0)["items"]
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "recent": recent,
    }
