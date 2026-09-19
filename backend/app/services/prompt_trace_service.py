"""Prompt trace persistence helpers."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.request_context import get_request_id
from app.models.prompt_trace import PromptTrace
from app.utils.time_helper import utc_now

logger = logging.getLogger(__name__)


@contextmanager
def _session_scope(existing: Session | None = None) -> Iterator[Session]:
    if existing is not None:
        yield existing
        return

    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _hash_text(text: str) -> str:
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


def build_trace_context(
    *,
    source: str,
    prompt_name: str | None = None,
    prompt_family: str | None = None,
    request_id: str | None = None,
    user_id: int | None = None,
    resume_id: int | None = None,
    jd_id: int | None = None,
    task_id: int | None = None,
    analysis_record_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = {
        "source": source,
        "prompt_name": prompt_name,
        "prompt_family": prompt_family,
        "request_id": request_id or get_request_id(),
        "user_id": user_id,
        "resume_id": resume_id,
        "jd_id": jd_id,
        "task_id": task_id,
        "analysis_record_id": analysis_record_id,
    }
    if extra:
        context.update(extra)
    return {key: value for key, value in context.items() if value is not None}


def record_prompt_trace(
    *,
    prompt: str,
    response_text: str | None,
    response_json: dict[str, Any] | None,
    provider: str,
    model: str | None,
    prompt_version: str | None = None,
    source: str | None = None,
    prompt_name: str | None = None,
    prompt_family: str | None = None,
    status: str = "success",
    cache_hit: bool = False,
    duration_ms: int | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    cost_cents: float = 0.0,
    error_message: str | None = None,
    user_id: int | None = None,
    resume_id: int | None = None,
    jd_id: int | None = None,
    task_id: int | None = None,
    analysis_record_id: int | None = None,
    trace_context: dict[str, Any] | None = None,
    prompt_metadata: dict[str, Any] | None = None,
    response_source: str = "unknown",
    degraded: bool | None = None,
    db: Session | None = None,
) -> PromptTrace:
    trace_context = trace_context or {}
    prompt_metadata = prompt_metadata or {}
    request_id = trace_context.get("request_id") or get_request_id()
    source_value = source or trace_context.get("source") or "unknown"
    prompt_version_value = prompt_version or prompt_metadata.get("prompt_version") or "unknown"
    # Anything that is not a direct answer from the configured primary model is
    # degraded, unless the caller says otherwise.
    degraded_value = int(bool(degraded)) if degraded is not None else int(response_source != "real")

    payload = {
        "request_id": request_id,
        "source": source_value,
        "prompt_version": prompt_version_value,
        "prompt_family": prompt_family or prompt_metadata.get("prompt_family"),
        "prompt_name": prompt_name or prompt_metadata.get("prompt_name"),
        "provider": provider,
        "model": model or "",
        "response_source": response_source,
        "degraded": degraded_value,
        "status": status,
        "cache_hit": int(bool(cache_hit)),
        "duration_ms": duration_ms,
        "prompt_chars": len(prompt or ""),
        "prompt_hash": _hash_text(prompt),
        "prompt_text": prompt,
        "response_text": response_text,
        "response_json": response_json,
        "error_message": error_message,
        "trace_context": trace_context,
        "prompt_metadata": prompt_metadata,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_cents": cost_cents,
        "task_id": task_id,
        "analysis_record_id": analysis_record_id,
        "user_id": user_id,
        "resume_id": resume_id,
        "jd_id": jd_id,
        "created_at": utc_now(),
    }

    trace = PromptTrace(**payload)
    if db is not None:
        db.add(trace)
        db.commit()
        db.refresh(trace)
        return trace

    with _session_scope(None) as session:
        session.add(trace)
        session.flush()
        session.refresh(trace)
        return trace


def update_prompt_feedback(
    db: Session,
    *,
    trace_id: int,
    feedback_label: str,
    feedback_note: str | None = None,
    feedback_score: float | None = None,
) -> PromptTrace:
    trace = db.get(PromptTrace, trace_id)
    if not trace:
        raise ValueError("prompt trace not found")
    trace.feedback_label = feedback_label
    trace.feedback_note = feedback_note
    trace.feedback_score = feedback_score
    db.commit()
    db.refresh(trace)
    return trace
