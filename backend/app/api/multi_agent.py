# -*- coding: utf-8 -*-
"""Deprecated compatibility endpoints for legacy multi-agent flows."""

import traceback

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.agent_orchestrator import run_auto_agents, run_multi_agents
from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.agent_run import AgentMessage, AgentResult, AgentRun
from app.models.history import JobDescription, Resume
from app.models.user import User
from app.schemas.agent_run import AutoStartReq, MultiAgentStartReq
from app.utils.job_access import accessible_job_query, get_accessible_job
from app.utils.response import ERR_COMMON, ERR_PARAM, fail, ok

router = APIRouter()


def _get_owned_resume(db: Session, resume_id: int, user_id: int) -> Resume | None:
    return (
        db.query(Resume)
        .filter(
            Resume.id == resume_id,
            Resume.user_id == user_id,
            Resume.is_deleted == 0,
        )
        .first()
    )


def _get_user_run(db: Session, run_id: int, user_id: int) -> AgentRun | None:
    return (
        db.query(AgentRun)
        .join(Resume, Resume.id == AgentRun.resume_id)
        .filter(
            AgentRun.id == run_id,
            Resume.user_id == user_id,
            Resume.is_deleted == 0,
        )
        .first()
    )


@router.post("/auto", summary="Deprecated auto-dispatch multi-agent entry", deprecated=True)
async def auto_analyze(
    payload: AutoStartReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume_id = payload.resume_id
    jd_id = payload.jd_id

    if not resume_id:
        latest_resume = (
            db.query(Resume)
            .filter(Resume.is_deleted == 0, Resume.user_id == current_user.id)
            .order_by(Resume.create_time.desc())
            .first()
        )
        resume_id = latest_resume.id if latest_resume else None

    if not jd_id:
        latest_jd = (
            accessible_job_query(db, current_user)
            .order_by(JobDescription.create_time.desc())
            .first()
        )
        jd_id = latest_jd.id if latest_jd else None

    if not resume_id or not _get_owned_resume(db, resume_id, current_user.id):
        return fail(message="resume not found", code=ERR_PARAM)
    if jd_id and not get_accessible_job(db, jd_id, current_user):
        return fail(message="job not found", code=ERR_PARAM)

    try:
        run_id = run_auto_agents(payload.user_request or "", resume_id, jd_id, user_id=current_user.id)
        return ok(
            data={"run_id": run_id, "resume_id": resume_id, "jd_id": jd_id},
            message="multi-agent run started",
        )
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"start failed: {str(exc)[:120]}", code=ERR_COMMON)


@router.post("/start", summary="Deprecated full multi-agent entry", deprecated=True)
async def start_multi_agents(
    payload: MultiAgentStartReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.resume_id or not payload.jd_id:
        return fail(message="resume_id and jd_id are required", code=ERR_PARAM)
    if not _get_owned_resume(db, payload.resume_id, current_user.id):
        return fail(message="resume not found", code=ERR_PARAM)
    if not get_accessible_job(db, payload.jd_id, current_user):
        return fail(message="job not found", code=ERR_PARAM)

    try:
        run_id = run_multi_agents(payload.resume_id, payload.jd_id, user_id=current_user.id)
        return ok(data={"run_id": run_id}, message="multi-agent run started")
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"start failed: {str(exc)[:120]}", code=ERR_COMMON)


@router.get("/run/{run_id}", summary="Get legacy multi-agent run")
async def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _get_user_run(db, run_id, current_user.id)
    if not run:
        return fail(message="run not found", code=ERR_PARAM)
    return ok(data=run.to_dict())


@router.get("/run/{run_id}/detail", summary="Get legacy multi-agent run detail")
async def get_run_detail(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _get_user_run(db, run_id, current_user.id)
    if not run:
        return fail(message="run not found", code=ERR_PARAM)

    messages = (
        db.query(AgentMessage)
        .filter(AgentMessage.run_id == run_id)
        .order_by(AgentMessage.id)
        .all()
    )
    results = (
        db.query(AgentResult)
        .filter(AgentResult.run_id == run_id)
        .order_by(AgentResult.id)
        .all()
    )

    return ok(
        data={
            "run": run.to_dict(),
            "messages": [item.to_dict() for item in messages],
            "results": [item.to_dict() for item in results],
        }
    )
