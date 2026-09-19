"""Shared runners for orchestration strategies and legacy wrappers."""

from __future__ import annotations

import logging
import traceback
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.agent import AgentTask
from app.models.agent_run import AgentRun
from app.orchestration.registry import DEFAULT_REGISTRY
from app.orchestration.strategies import StrategyFactory
from app.services.orchestration_backend import (
    RedisQueueOrchestrationBackend,
    TaskPayload,
    get_orchestration_backend,
    health_snapshot,
)
from app.utils.time_helper import utc_now

logger = logging.getLogger(__name__)

_BACKEND = None


def _get_backend():
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = get_orchestration_backend()
    return _BACKEND


def _run_task_payload(payload: TaskPayload) -> None:
    """唯一的任务执行入口：线程后端和 Redis worker 跑的是同一份代码。"""
    db = SessionLocal()
    try:
        strategy = StrategyFactory.create(payload.strategy_name, DEFAULT_REGISTRY)
        result = strategy.run(
            payload.task_id,
            payload.resume_id,
            payload.jd_id,
            payload.user_id,
            db,
            run_id=payload.run_id,
        )

        if result.get("status") == "failed":
            task = db.get(AgentTask, payload.task_id)
            if task and task.status == "running":
                task.status = "failed"
                task.error_msg = result.get("error", "orchestration failed")[:500]
                task.end_time = utc_now()
                db.add(task)
                db.commit()
    except Exception as exc:
        traceback.print_exc()
        try:
            task = db.get(AgentTask, payload.task_id)
            if task and task.status == "running":
                task.status = "failed"
                task.error_msg = str(exc)[:500]
                task.end_time = utc_now()
                db.add(task)
                db.commit()
            if payload.run_id:
                # 策略在跑到收尾之前炸了：run 不能永远停在 running
                run = db.get(AgentRun, payload.run_id)
                if run and run.status not in {"completed", "failed", "cancelled"}:
                    run.status = "failed"
                    run.error_msg = str(exc)[:500]
                    run.end_time = utc_now()
                    db.add(run)
                    db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def run_redis_worker(stop_event=None) -> None:
    """Run the Redis queue worker loop in a standalone process."""
    backend = get_orchestration_backend()
    if not isinstance(backend, RedisQueueOrchestrationBackend):
        raise RuntimeError("ORCHESTRATION_BACKEND is not redis_queue")
    backend.worker_loop(_run_task_payload, stop_event=stop_event)


def get_queue_health() -> dict:
    return health_snapshot()


def create_task(
    resume_id: int,
    jd_id: int,
    user_id: int | None = None,
    *,
    strategy_name: str | None = None,
    retry_of_task_id: int | None = None,
    db: Session | None = None,
) -> int:
    """Create an AgentTask row and return its id."""
    session = db or SessionLocal()
    owns_session = db is None
    try:
        task = AgentTask(
            user_id=user_id or 0,
            resume_id=resume_id,
            jd_id=jd_id,
            strategy_name=strategy_name,
            retry_of_task_id=retry_of_task_id,
            status="running",
            start_time=utc_now(),
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        return task.id
    finally:
        if owns_session:
            session.close()


def run_strategy_async(
    strategy_name: str,
    resume_id: int,
    jd_id: int,
    user_id: int | None = None,
    *,
    retry_of_task_id: int | None = None,
) -> int:
    """Create a task and execute the given strategy using the configured backend."""
    task_id = create_task(
        resume_id,
        jd_id,
        user_id=user_id,
        strategy_name=strategy_name,
        retry_of_task_id=retry_of_task_id,
    )
    start_strategy_thread(strategy_name, task_id, resume_id, jd_id, user_id=user_id)
    return task_id


def start_strategy_thread(
    strategy_name: str,
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: int | None = None,
):
    """Run a strategy in the configured backend for an existing task."""
    payload = TaskPayload(
        strategy_name=strategy_name,
        task_id=task_id,
        resume_id=resume_id,
        jd_id=jd_id,
        user_id=user_id,
    )
    return _get_backend().submit(payload, _run_task_payload)


def create_legacy_run(
    resume_id: int,
    jd_id: int,
    user_request: str,
    task_id: int | None = None,
) -> int:
    """Create the legacy AgentRun row and return its id."""
    db = SessionLocal()
    try:
        run = AgentRun(
            resume_id=resume_id or 0,
            jd_id=jd_id or 0,
            task_id=task_id,
            user_request=user_request,
            status="running",
            start_time=utc_now(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id
    finally:
        db.close()


def start_legacy_layered_thread(
    run_id: int,
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: int | None = None,
):
    """Execute the layered strategy for a legacy AgentRun in background.

    run_id 放进 payload 而不是包进闭包：Redis 后端只搬运 payload，闭包会被丢弃，
    于是 worker 会为同一个任务另建一条 run —— 客户端轮询的那条永远停在 running、
    明细里一条消息都没有。
    """
    payload = TaskPayload(
        strategy_name="layered",
        task_id=task_id,
        resume_id=resume_id,
        jd_id=jd_id,
        user_id=user_id,
        run_id=run_id,
    )
    return _get_backend().submit(payload, _run_task_payload)


def mark_stale_running_tasks_failed(
    *,
    older_than_minutes: int | None = None,
    db: Session | None = None,
) -> int:
    """Fail tasks left running by a previous interrupted process."""
    minutes = older_than_minutes if older_than_minutes is not None else settings.ORCHESTRATION_STALE_TASK_MINUTES
    cutoff = utc_now() - timedelta(minutes=max(1, int(minutes or 30)))
    session = db or SessionLocal()
    owns_session = db is None
    try:
        tasks = session.query(AgentTask).filter(AgentTask.status == "running", AgentTask.start_time < cutoff).all()
        for task in tasks:
            task.status = "failed"
            task.error_msg = "Marked failed on startup because the previous worker stopped before completion"
            task.end_time = utc_now()
            session.add(task)
        if tasks:
            session.commit()
            logger.warning("Marked %s stale running agent tasks as failed", len(tasks))
        return len(tasks)
    finally:
        if owns_session:
            session.close()


def shutdown_orchestration_executor() -> None:
    """Stop accepting new background work during application shutdown."""
    backend = _get_backend()
    backend.shutdown()


def cancel_task(task_id: int, user_id: int, *, db: Session | None = None) -> AgentTask | None:
    """Mark a task as cancelled if it has not finished yet."""
    session = db or SessionLocal()
    owns_session = db is None
    try:
        task = session.get(AgentTask, task_id)
        if not task or task.user_id != user_id:
            return None
        if task.status in {"completed", "failed", "partial", "cancelled"}:
            return task

        task.status = "cancelled"
        task.error_msg = "Cancelled by user"
        task.end_time = utc_now()
        session.add(task)
        session.commit()
        session.refresh(task)
        return task
    finally:
        if owns_session:
            session.close()


def retry_task(
    task_id: int,
    user_id: int,
    fallback_strategy: str,
    *,
    db: Session | None = None,
) -> AgentTask | None:
    """Create a fresh retry task from an existing terminal task and start it."""
    session = db or SessionLocal()
    owns_session = db is None
    try:
        task = session.get(AgentTask, task_id)
        if not task or task.user_id != user_id:
            return None
        if task.status in {"pending", "running"}:
            return task

        strategy_name = task.strategy_name or fallback_strategy
        new_task_id = create_task(
            task.resume_id,
            task.jd_id,
            user_id=user_id,
            strategy_name=strategy_name,
            retry_of_task_id=task.id,
            db=session,
        )
        start_strategy_thread(strategy_name, new_task_id, task.resume_id, task.jd_id, user_id=user_id)
        logger.info(
            "Task retried original_task_id=%s new_task_id=%s strategy=%s",
            task.id,
            new_task_id,
            strategy_name,
        )
        return session.get(AgentTask, new_task_id)
    finally:
        if owns_session:
            session.close()
