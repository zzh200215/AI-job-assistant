"""Legacy agent workflow endpoints kept for backward compatibility."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.agent import AgentStepLog, RetrievalLog, SelfCheckLog
from app.models.history import Resume
from app.models.user import User
from app.schemas.agent import AgentStartReq
from app.services.agent_workflow import run_workflow
from app.services.analysis_service import get_configured_strategy_name
from app.services.orchestration_runner import cancel_task, retry_task
from app.services.task_center_service import get_task_with_progress, get_user_task_summary, list_user_tasks
from app.utils.http_errors import api_error
from app.utils.job_access import get_accessible_job
from app.utils.response import ERR_COMMON, ERR_PARAM, ok

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/start", summary="[Deprecated] Start agent workflow", deprecated=True)
async def start_analysis(
    payload: AgentStartReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.resume_id or not payload.jd_id:
        raise api_error(400, "resume_id and jd_id are required", ERR_PARAM)

    resume = (
        db.query(Resume)
        .filter(
            Resume.id == payload.resume_id,
            Resume.user_id == current_user.id,
            Resume.is_deleted == 0,
        )
        .first()
    )
    jd = get_accessible_job(db, payload.jd_id, current_user)
    if not resume or not jd:
        raise api_error(404, "resume or job description not found", ERR_PARAM)

    try:
        task_id = run_workflow(payload.resume_id, payload.jd_id, user_id=current_user.id)
        return ok(data={"task_id": task_id}, message="workflow started")
    except Exception as exc:
        logger.exception("Failed to start legacy workflow resume_id=%s jd_id=%s", payload.resume_id, payload.jd_id)
        raise api_error(500, f"failed to start workflow: {exc}", ERR_COMMON) from exc


@router.get("/tasks", summary="List current user's agent tasks")
async def get_task_list(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ok(data=list_user_tasks(db, user_id=current_user.id, status=status, limit=limit, offset=offset))


@router.get("/tasks/summary", summary="Get current user's agent task summary")
async def get_task_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ok(data=get_user_task_summary(db, user_id=current_user.id))


@router.post("/task/{task_id}/cancel", summary="Cancel a running task")
async def cancel_agent_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = cancel_task(task_id, current_user.id, db=db)
    if not task:
        raise api_error(404, "task not found", ERR_PARAM)
    return ok(data=task.to_dict(), message="task cancelled")


@router.post("/task/{task_id}/retry", summary="Retry a finished task")
async def retry_agent_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = retry_task(
        task_id,
        current_user.id,
        fallback_strategy=get_configured_strategy_name(),
        db=db,
    )
    if not task:
        raise api_error(404, "task not found", ERR_PARAM)
    if task.id == task_id and task.status in {"pending", "running"}:
        raise api_error(409, "task is still running", ERR_PARAM)
    return ok(data=task.to_dict(), message="retry task started")


@router.get("/task/{task_id}", summary="Get task status")
async def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task, payload = get_task_with_progress(db, task_id=task_id, user_id=current_user.id)
    if not task or not payload:
        raise api_error(404, "task not found", ERR_PARAM)
    return ok(data=payload)


@router.get("/task/{task_id}/steps", summary="Get task step details")
async def get_task_steps(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task, payload = get_task_with_progress(db, task_id=task_id, user_id=current_user.id)
    if not task or not payload:
        raise api_error(404, "task not found", ERR_PARAM)

    steps = db.query(AgentStepLog).filter(AgentStepLog.task_id == task_id).order_by(AgentStepLog.step_index).all()
    retrievals = db.query(RetrievalLog).filter(RetrievalLog.task_id == task_id).all()
    checks = db.query(SelfCheckLog).filter(SelfCheckLog.task_id == task_id).all()

    return ok(
        data={
            "task": payload,
            "steps": [s.to_dict() for s in steps],
            "retrievals": [r.to_dict() for r in retrievals],
            "checks": [c.to_dict() for c in checks],
        }
    )
