"""Deprecated compatibility wrapper for legacy multi-agent endpoints."""

import warnings

from app.agents.career_agent import CareerAgent
from app.agents.interview_agent import InterviewAgent
from app.agents.job_agent import JobAgent
from app.agents.match_agent import MatchAgent

# Backward-compatible exports for legacy imports.
from app.agents.resume_agent import ResumeAgent
from app.agents.summary_agent import SummaryAgent
from app.core.database import SessionLocal
from app.models.agent import AgentTask
from app.models.agent_run import AgentRun
from app.orchestration.context import AgentContext
from app.services.orchestration_runner import create_legacy_run, create_task, start_legacy_layered_thread
from app.utils.time_helper import utc_now

AGENT_REGISTRY = {
    "ResumeAgent": ResumeAgent,
    "JobAgent": JobAgent,
    "MatchAgent": MatchAgent,
    "InterviewAgent": InterviewAgent,
    "CareerAgent": CareerAgent,
    "SummaryAgent": SummaryAgent,
}

C_END_AGENTS = ["ResumeAgent", "JobAgent", "MatchAgent", "InterviewAgent", "CareerAgent"]


def run_multi_agents(resume_id: int, jd_id: int, user_id: int | None = None) -> int:
    """Start the legacy full multi-agent flow via the shared layered runner."""
    warnings.warn(
        "run_multi_agents 已废弃，请使用 run_smart_analysis → smart_orchestrator",
        DeprecationWarning,
        stacklevel=2,
    )
    run_id = create_legacy_run(resume_id, jd_id, "run_multi_agents")
    task_id = create_task(resume_id, jd_id, user_id=user_id)
    _update_run_metadata(
        run_id,
        intent="full_analysis",
        selected_agents=C_END_AGENTS,
        dispatch_reason="legacy full multi-agent entrypoint",
    )
    start_legacy_layered_thread(run_id, task_id, resume_id, jd_id, user_id=user_id)
    return run_id


def run_auto_agents(
    user_request: str,
    resume_id: int | None = None,
    jd_id: int | None = None,
    user_id: int | None = None,
) -> int:
    """Start the legacy auto-dispatch flow and persist intent metadata."""
    warnings.warn(
        "run_auto_agents 已废弃，请使用 run_smart_analysis → smart_orchestrator",
        DeprecationWarning,
        stacklevel=2,
    )
    run_id = create_legacy_run(resume_id or 0, jd_id or 0, user_request)
    task_id = create_task(resume_id or 0, jd_id or 0, user_id=user_id)

    try:
        db = SessionLocal()
        try:
            from app.agents.intent_agent import IntentAgent

            decision = IntentAgent(db=db).run_impl(
                AgentContext.for_analysis(
                    resume_id or 0,
                    jd_id or 0,
                    user_id=user_id,
                    db=db,
                    user_request=user_request,
                )
            )
        finally:
            db.close()
    except Exception as exc:
        _mark_legacy_failed(run_id, task_id, str(exc))
        raise

    _update_run_metadata(
        run_id,
        intent=decision.get("intent"),
        selected_agents=decision.get("selected_agents") or C_END_AGENTS,
        dispatch_reason=decision.get("dispatch_reason") or decision.get("reason"),
    )
    start_legacy_layered_thread(run_id, task_id, resume_id or 0, jd_id or 0, user_id=user_id)
    return run_id


def _update_run_metadata(
    run_id: int,
    intent: str | None = None,
    selected_agents: list | None = None,
    dispatch_reason: str | None = None,
):
    db = SessionLocal()
    try:
        run = db.get(AgentRun, run_id)
        if not run:
            return
        run.intent = intent
        run.selected_agents = selected_agents
        run.dispatch_reason = dispatch_reason
        db.add(run)
        db.commit()
    finally:
        db.close()


def _mark_legacy_failed(run_id: int, task_id: int, error_msg: str):
    db = SessionLocal()
    try:
        run = db.get(AgentRun, run_id)
        if run:
            run.status = "failed"
            run.error_msg = error_msg[:500]
            run.end_time = utc_now()
            db.add(run)

        task = db.get(AgentTask, task_id)
        if task:
            task.status = "failed"
            task.error_msg = error_msg[:500]
            task.end_time = utc_now()
            db.add(task)

        db.commit()
    finally:
        db.close()
