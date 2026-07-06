# -*- coding: utf-8 -*-
"""System status and runtime capability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.runtime_metrics import get_runtime_metrics
from app.core.user_roles import RECRUITER_ROLE
from app.models.candidate_screening import CandidateScreeningSession
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.interview_session import InterviewSession
from app.models.job_data_source import JobDataSource, JobSyncLog
from app.models.knowledge import KnowledgeDocument
from app.models.user import User
from app.services.embedding_service import get_embedding_daily_stats, get_embedding_stats
from app.services.orchestration_runner import get_queue_health
from app.utils.file_parser import is_ocr_available
from app.utils.http_errors import api_error
from app.utils.response import ERR_AUTH, ok

router = APIRouter()


def _is_mock(provider: str | None) -> bool:
    return str(provider or "").strip().lower() == "mock"


def _can_view_system_overview(user: User) -> bool:
    return user.role == RECRUITER_ROLE or user.username in settings.admin_usernames_list


@router.get("/status", summary="Get runtime system status")
async def get_system_status(_current_user: User = Depends(get_current_user)):
    llm_provider = str(settings.LLM_PROVIDER or "").strip().lower()
    embedding_provider = str(settings.EMBEDDING_PROVIDER or "").strip().lower()
    reranker_provider = str(settings.RERANKER_PROVIDER or "").strip().lower()

    status = {
        "app_env": settings.APP_ENV,
        "log_level": settings.LOG_LEVEL,
        "orchestration_strategy": settings.ORCHESTRATION_STRATEGY,
        "orchestration_engine": settings.ORCHESTRATION_ENGINE,
        "orchestration_backend": settings.ORCHESTRATION_BACKEND,
        "llm_provider": llm_provider,
        "embedding_provider": embedding_provider,
        "reranker_provider": reranker_provider,
        "demo_mode": any((_is_mock(llm_provider), _is_mock(embedding_provider))),
        "capabilities": {
            "tool_calling": not _is_mock(llm_provider),
            "social_login": False,
            "password_reset": True,
            "ocr_resume_parse": is_ocr_available(),
        },
        "runtime_notes": {
            "llm_mode": "demo" if _is_mock(llm_provider) else "live",
            "embedding_mode": "demo" if _is_mock(embedding_provider) else "live",
            "data_source_api_ready": True,
            "data_source_api_note": "HTTP API data sources support auth refresh, pagination, rate limiting, and retry backoff.",
            "orchestration_backend_note": f"current backend={settings.ORCHESTRATION_BACKEND}; redis_queue is available when REDIS_URL is configured.",
            "knowledge_seed_ready": True,
            "queue_health": get_queue_health(),
        },
    }
    return ok(status)


@router.get("/overview", summary="Get project overview metrics")
async def get_system_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅招聘者或管理员可查看系统概览", ERR_AUTH)

    overview = {
        "users": db.query(User).count(),
        "resumes": db.query(Resume).count(),
        "jds": db.query(JobDescription).count(),
        "analysis_records": db.query(AnalysisRecord).count(),
        "interviews": db.query(InterviewSession).count(),
        "screening_sessions": db.query(CandidateScreeningSession).count(),
        "knowledge_documents": db.query(KnowledgeDocument).count(),
        "data_sources": db.query(JobDataSource).count(),
        "sync_logs": db.query(JobSyncLog).count(),
        "runtime_metrics": get_runtime_metrics(),
        "embedding_metrics": {
            "current": get_embedding_stats(),
            "daily": get_embedding_daily_stats(days=7),
        },
    }
    return ok(overview)
