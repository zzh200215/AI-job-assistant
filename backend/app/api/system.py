"""System status and runtime capability endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import engine, get_db
from app.core.prometheus_metrics import get_metrics_response
from app.core.runtime_metrics import get_runtime_metrics
from app.core.user_roles import ADMIN_ROLE
from app.models.ai_release import AIRelease
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.interview_session import InterviewSession
from app.models.job_pipeline import JobApplicationPipeline
from app.models.knowledge import KnowledgeDocument
from app.models.operational_alert import OperationalAlert
from app.models.prompt_trace import PromptTrace
from app.models.user import User
from app.services.ai_release_service import evaluate_release_gate
from app.services.audit_service import write_audit_log
from app.services.embedding_service import get_embedding_daily_stats, get_embedding_stats
from app.services.operational_alert_service import evaluate_operational_alerts
from app.services.orchestration_runner import get_queue_health
from app.utils.file_parser import is_ocr_available
from app.utils.http_errors import api_error
from app.utils.response import ERR_AUTH, ERR_PARAM, ok

router = APIRouter()


def _is_mock(provider: str | None) -> bool:
    return str(provider or "").strip().lower() == "mock"


def _feishu_sso_configured() -> bool:
    return bool(settings.FEISHU_APP_ID and settings.FEISHU_APP_SECRET and settings.FEISHU_REDIRECT_URI)


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


def build_operational_alert_snapshot() -> dict:
    """Collect the non-persistent inputs used by the alert evaluator."""
    return {
        "model_runtime": _model_runtime_status(),
        "queue_health": get_queue_health(),
        "runtime_metrics": get_runtime_metrics(),
    }


def _load_release_reports(report_ids: list[str]) -> tuple[list[tuple[dict, dict]], list[str]]:
    """Load selected immutable report inputs, without exposing arbitrary file paths."""
    from app.api.evaluation import _load_report_detail

    details: list[tuple[dict, dict]] = []
    missing: list[str] = []
    for report_id in report_ids:
        summary, raw = _load_report_detail(report_id)
        if not summary or not raw:
            missing.append(report_id)
        else:
            details.append((summary, raw))
    return details, missing


def _release_report_ids(release: AIRelease) -> list[str]:
    return [str(item.get("report_id")) for item in (release.evaluation_reports or []) if item.get("report_id")]


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
            "social_login": _feishu_sso_configured(),
            "feishu_sso": _feishu_sso_configured(),
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
        "operational_alerts": {
            "open": db.query(OperationalAlert).filter(OperationalAlert.status == "open").count(),
            "acknowledged": db.query(OperationalAlert).filter(OperationalAlert.status == "acknowledged").count(),
        },
    }
    return ok(overview)


@router.get("/ai-costs", summary="Get AI cost attribution")
async def get_ai_cost_attribution(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可查看 AI 成本归因", ERR_AUTH)

    rows = (
        db.query(
            PromptTrace.provider,
            PromptTrace.model,
            PromptTrace.prompt_version,
            func.count(PromptTrace.id),
            func.coalesce(func.sum(PromptTrace.total_tokens), 0),
            func.coalesce(func.sum(PromptTrace.cost_cents), 0.0),
        )
        .group_by(PromptTrace.provider, PromptTrace.model, PromptTrace.prompt_version)
        .order_by(func.sum(PromptTrace.cost_cents).desc())
        .limit(100)
        .all()
    )
    items = [
        {
            "provider": provider or "unknown",
            "model": model or "unknown",
            "prompt_version": prompt_version or "unknown",
            "calls": int(calls or 0),
            "total_tokens": int(total_tokens or 0),
            "cost_cents": round(float(cost_cents or 0.0), 6),
        }
        for provider, model, prompt_version, calls, total_tokens, cost_cents in rows
    ]
    return ok(
        {
            "items": items,
            "total_calls": sum(item["calls"] for item in items),
            "total_tokens": sum(item["total_tokens"] for item in items),
            "total_cost_cents": round(sum(item["cost_cents"] for item in items), 6),
        }
    )


@router.get("/ai-releases", summary="List AI release records")
async def list_ai_releases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可查看 AI 发布记录", ERR_AUTH)
    releases = db.query(AIRelease).order_by(AIRelease.created_at.desc()).limit(100).all()
    return ok({"items": [release.to_dict() for release in releases]})


@router.post("/ai-releases", summary="Create an AI release candidate")
async def create_ai_release(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可创建 AI 发布记录", ERR_AUTH)

    release_key = str(payload.get("release_key") or "").strip()
    prompt_versions = [str(item).strip() for item in payload.get("prompt_versions", []) if str(item).strip()]
    report_ids = [str(item).strip() for item in payload.get("evaluation_report_ids", []) if str(item).strip()]
    if not release_key or not prompt_versions or not report_ids:
        raise api_error(400, "release_key、prompt_versions 和 evaluation_report_ids 均为必填", ERR_PARAM)
    if len(release_key) > 100 or len(report_ids) > 10:
        raise api_error(400, "发布标识或评测报告数量不合法", ERR_PARAM)
    if db.query(AIRelease).filter(AIRelease.release_key == release_key).first():
        raise api_error(409, "发布标识已存在", ERR_PARAM)

    details, missing = _load_release_reports(report_ids)
    if missing:
        raise api_error(400, f"评测报告不存在: {', '.join(missing)}", ERR_PARAM)
    gate_result, evidence = evaluate_release_gate(details)
    release = AIRelease(
        release_key=release_key,
        provider=str(payload.get("provider") or settings.LLM_PROVIDER).strip(),
        model=str(payload.get("model") or settings.LLM_MODEL).strip(),
        prompt_versions=sorted(set(prompt_versions)),
        evaluation_reports=evidence,
        gate_result=gate_result,
        status="ready" if gate_result["passed"] else "blocked",
        notes=str(payload.get("notes") or "").strip()[:4000],
        created_by=current_user.id,
    )
    db.add(release)
    db.commit()
    db.refresh(release)
    write_audit_log(
        db,
        current_user,
        "ai_release.create",
        resource_type="ai_release",
        resource_id=str(release.id),
        detail={"release_key": release.release_key, "gate_passed": gate_result["passed"]},
    )
    return ok(release.to_dict(), message="AI 发布候选已创建")


@router.post("/ai-releases/{release_id}/evaluate", summary="Re-evaluate an AI release gate")
async def evaluate_ai_release(
    release_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可评估 AI 发布门禁", ERR_AUTH)
    release = db.get(AIRelease, release_id)
    if release is None:
        raise api_error(404, "AI 发布记录不存在", ERR_PARAM)
    details, missing = _load_release_reports(_release_report_ids(release))
    if missing:
        raise api_error(400, f"评测报告不存在: {', '.join(missing)}", ERR_PARAM)
    gate_result, evidence = evaluate_release_gate(details)
    release.evaluation_reports = evidence
    release.gate_result = gate_result
    release.status = "ready" if gate_result["passed"] else "blocked"
    release.approved_by = None
    release.approved_at = None
    db.commit()
    db.refresh(release)
    return ok(release.to_dict())


@router.post("/ai-releases/{release_id}/approve", summary="Approve a gated AI release")
async def approve_ai_release(
    release_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可审批 AI 发布", ERR_AUTH)
    release = db.get(AIRelease, release_id)
    if release is None:
        raise api_error(404, "AI 发布记录不存在", ERR_PARAM)
    if not release.gate_result.get("passed"):
        raise api_error(409, "发布门禁未通过，不能审批", ERR_PARAM)
    release.status = "approved"
    release.approved_by = current_user.id
    release.approved_at = datetime.now(timezone.utc)
    db.commit()
    write_audit_log(
        db,
        current_user,
        "ai_release.approve",
        resource_type="ai_release",
        resource_id=str(release.id),
        detail={"release_key": release.release_key},
    )
    db.refresh(release)
    return ok(release.to_dict())


@router.post("/alerts/evaluate", summary="Evaluate operational alert thresholds")
async def evaluate_system_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可评估运维告警", ERR_AUTH)

    alerts = evaluate_operational_alerts(db, **build_operational_alert_snapshot())
    return ok({"alerts": [alert.to_dict() for alert in alerts], "evaluated_at": datetime.now(timezone.utc).isoformat()})


@router.get("/alerts", summary="List operational alerts")
async def list_system_alerts(
    include_resolved: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可查看运维告警", ERR_AUTH)

    query = db.query(OperationalAlert)
    if not include_resolved:
        query = query.filter(OperationalAlert.resolved_at.is_(None))
    alerts = query.order_by(OperationalAlert.last_seen_at.desc()).limit(100).all()
    return ok({"alerts": [alert.to_dict() for alert in alerts]})


@router.post("/alerts/{alert_id}/acknowledge", summary="Acknowledge an operational alert")
async def acknowledge_system_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _can_view_system_overview(current_user):
        raise api_error(403, "仅管理员可确认运维告警", ERR_AUTH)

    alert = db.get(OperationalAlert, alert_id)
    if alert is None:
        raise api_error(404, "运维告警不存在", ERR_PARAM)
    if alert.resolved_at is not None:
        raise api_error(409, "已恢复的告警无需确认", ERR_PARAM)
    if alert.status != "acknowledged":
        alert.status = "acknowledged"
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = current_user.id
        db.commit()
        write_audit_log(
            db,
            current_user,
            "operational_alert.acknowledge",
            resource_type="operational_alert",
            resource_id=str(alert.id),
            detail={"alert_key": alert.alert_key, "severity": alert.severity},
        )
        db.refresh(alert)
    return ok(alert.to_dict())


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
