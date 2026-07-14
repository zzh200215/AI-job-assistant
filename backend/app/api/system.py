"""System status and runtime capability endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import engine, get_db
from app.core.prometheus_metrics import get_metrics_response
from app.core.runtime_metrics import get_runtime_metrics
from app.core.user_roles import ADMIN_ROLE
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.interview_session import InterviewSession
from app.models.job_pipeline import JobApplicationPipeline
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
    return user.role == ADMIN_ROLE or user.username in settings.admin_usernames_list


def _provider_runtime_status(
    provider: str | None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    kind: str,
) -> dict:
    """Return a non-sensitive runtime configuration assessment for one provider."""
    normalized = str(provider or "").strip().lower()
    if normalized == "mock":
        return {"provider": normalized, "mode": "demo", "configured": True}

    supported = {"openai", "qwen", "local"} if kind == "llm" else {"openai", "qwen", "dashscope"}

    if normalized not in supported:
        return {"provider": normalized or "unknown", "mode": "unsupported", "configured": False}

    if normalized == "local":
        configured = bool((base_url or "").strip())
    else:
        configured = bool((api_key or "").strip())
        if normalized == "qwen":
            configured = configured and bool((base_url or "").strip())

    return {
        "provider": normalized,
        "mode": "live" if configured else "misconfigured",
        "configured": configured,
    }


def _model_runtime_status() -> dict:
    llm = _provider_runtime_status(
        settings.LLM_PROVIDER,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        kind="llm",
    )
    embedding = _provider_runtime_status(
        settings.EMBEDDING_PROVIDER,
        api_key=settings.EMBEDDING_API_KEY or settings.LLM_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL,
        kind="embedding",
    )
    ready = llm["mode"] in {"demo", "live"} and embedding["mode"] in {"demo", "live"}
    return {
        "ready": ready,
        "live_ready": llm["mode"] == "live" and embedding["mode"] == "live",
        "llm": {**llm, "model": settings.LLM_MODEL},
        "embedding": {**embedding, "model": settings.EMBEDDING_MODEL},
    }


def _probe_llm() -> dict:
    """Run one small uncached structured LLM request, without exposing credentials."""
    from app.services.llm_service import chat_json, clear_llm_cache

    clear_llm_cache()
    started = perf_counter()
    try:
        response = chat_json('Return exactly this JSON object: {"status":"ok"}.')
        return {
            "ok": isinstance(response, dict) and response.get("status") == "ok",
            "latency_ms": round((perf_counter() - started) * 1000),
        }
    except Exception as exc:
        return {"ok": False, "latency_ms": round((perf_counter() - started) * 1000), "error_type": type(exc).__name__}


def _probe_embedding() -> dict:
    """Run one unique embedding request so a cached vector cannot mask a failed provider."""
    from app.services.embedding_service import embed_text

    started = perf_counter()
    try:
        vector = embed_text(f"runtime-probe-{uuid4().hex}")
        return {
            "ok": isinstance(vector, list) and len(vector) > 0,
            "latency_ms": round((perf_counter() - started) * 1000),
            "dimension": len(vector) if isinstance(vector, list) else None,
        }
    except Exception as exc:
        return {"ok": False, "latency_ms": round((perf_counter() - started) * 1000), "error_type": type(exc).__name__}


@router.get("/status", summary="Get runtime system status")
async def get_system_status(_current_user: User = Depends(get_current_user)):
    llm_provider = str(settings.LLM_PROVIDER or "").strip().lower()
    embedding_provider = str(settings.EMBEDDING_PROVIDER or "").strip().lower()
    reranker_provider = str(settings.RERANKER_PROVIDER or "").strip().lower()

    model_runtime = _model_runtime_status()
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
        "model_runtime": model_runtime,
        "capabilities": {
            "tool_calling": not _is_mock(llm_provider),
            "social_login": False,
            "password_reset": True,
            "ocr_resume_parse": is_ocr_available(),
        },
        "runtime_notes": {
            "llm_mode": model_runtime["llm"]["mode"],
            "embedding_mode": model_runtime["embedding"]["mode"],
            "orchestration_backend_note": (
                f"current backend={settings.ORCHESTRATION_BACKEND}; "
                "redis_queue is available when REDIS_URL is configured."
            ),
            "knowledge_seed_ready": True,
            "queue_health": get_queue_health(),
        },
    }
    return ok(status)


@router.post("/model-probe", summary="Probe configured LLM and embedding providers")
async def probe_model_runtime(current_user: User = Depends(get_current_user)):
    """Admin-only, on-demand provider probe. Each live probe consumes a minimal provider request."""
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可执行模型连通性检测", ERR_AUTH)

    runtime = _model_runtime_status()
    checks = {"llm": {"skipped": True}, "embedding": {"skipped": True}}
    if runtime["llm"]["mode"] in {"demo", "live"}:
        checks["llm"] = _probe_llm()
    if runtime["embedding"]["mode"] in {"demo", "live"}:
        checks["embedding"] = _probe_embedding()

    return ok(
        data={
            "runtime": runtime,
            "checks": checks,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/overview", summary="Get project overview metrics")
async def get_system_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可查看系统概览", ERR_AUTH)

    overview = {
        "users": db.query(User).count(),
        "resumes": db.query(Resume).count(),
        "jds": db.query(JobDescription).count(),
        "analysis_records": db.query(AnalysisRecord).count(),
        "interviews": db.query(InterviewSession).count(),
        "knowledge_documents": db.query(KnowledgeDocument).count(),
        "pipeline_observability": {
            "total_applications": db.query(JobApplicationPipeline).count(),
            "version_attributed_applications": db.query(JobApplicationPipeline)
            .filter(JobApplicationPipeline.resume_version_id.isnot(None))
            .count(),
            "feedback_recorded_applications": db.query(JobApplicationPipeline)
            .filter(JobApplicationPipeline.feedback_at.isnot(None))
            .count(),
        },
        "runtime_metrics": get_runtime_metrics(),
        "embedding_metrics": {
            "current": get_embedding_stats(),
            "daily": get_embedding_daily_stats(days=7),
        },
    }
    return ok(overview)


@router.get("/health", summary="Liveness probe")
async def health_check():
    return ok(data={"status": "ok", "service": "smart-recruitment-platform"})


@router.get("/ready", summary="Readiness probe")
async def readiness_check():
    checks = {
        "mysql": False,
        "chroma": False,
    }
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        checks["mysql"] = True
    except Exception as exc:
        checks["mysql_error"] = str(exc)

    try:
        from app.core.chroma_client import get_chroma_client

        client = get_chroma_client()
        client.heartbeat()
        checks["chroma"] = True
    except Exception as exc:
        checks["chroma_error"] = str(exc)

    all_ready = all(checks.values())
    payload = ok(data={"ready": all_ready, "checks": checks})
    return JSONResponse(content=payload, status_code=200 if all_ready else 503)


@router.get("/metrics", summary="Prometheus metrics")
async def metrics():
    data, status_code, headers = get_metrics_response()
    return Response(content=data, status_code=status_code, headers=headers)
