# -*- coding: utf-8 -*-
"""Prompt trace APIs for lightweight LLMOps observability."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.prompt_trace import PromptTrace
from app.models.user import User
from app.services.prompt_trace_service import update_prompt_feedback
from app.utils.response import ERR_PARAM, fail, ok

router = APIRouter()


def _round_or_none(values: list[float | int | None], digits: int = 2) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return round(sum(filtered) / len(filtered), digits)


def _safe_iso(value) -> str | None:
    return value.isoformat() if value else None


def _metrics_from_rows(rows: list[PromptTrace]) -> dict:
    total = len(rows)
    success_count = sum(1 for row in rows if row.status == "success")
    failed_count = sum(1 for row in rows if row.status != "success")
    cache_hit_count = sum(1 for row in rows if row.cache_hit)

    return {
        "total": total,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": round(success_count / total, 4) if total else 0,
        "cache_hit_count": cache_hit_count,
        "cache_hit_rate": round(cache_hit_count / total, 4) if total else 0,
        "avg_duration_ms": _round_or_none([row.duration_ms for row in rows]),
        "avg_prompt_chars": _round_or_none([row.prompt_chars for row in rows]),
        "avg_total_tokens": _round_or_none([row.total_tokens for row in rows]),
        "avg_cost_cents": _round_or_none([row.cost_cents for row in rows], digits=6),
        "first_seen": _safe_iso(min((row.created_at for row in rows if row.created_at), default=None)),
        "last_seen": _safe_iso(max((row.created_at for row in rows if row.created_at), default=None)),
    }


def _build_group_item(key: str, rows: list[PromptTrace], *, group_type: str, source: str | None = None) -> dict:
    item = {
        group_type: key,
        **_metrics_from_rows(rows),
    }
    if source is not None:
        item["source"] = source
    return item


def _query_rows(
    db: Session,
    *,
    user_id: int,
    source: Optional[str] = None,
    prompt_version: Optional[str] = None,
    status: Optional[str] = None,
    request_id: Optional[str] = None,
    task_id: Optional[int] = None,
    analysis_record_id: Optional[int] = None,
    model: Optional[str] = None,
) -> list[PromptTrace]:
    query = db.query(PromptTrace).filter(PromptTrace.user_id == user_id)
    if source:
        query = query.filter(PromptTrace.source == source)
    if prompt_version:
        query = query.filter(PromptTrace.prompt_version == prompt_version)
    if status:
        query = query.filter(PromptTrace.status == status)
    if request_id:
        query = query.filter(PromptTrace.request_id == request_id)
    if task_id is not None:
        query = query.filter(PromptTrace.task_id == task_id)
    if analysis_record_id is not None:
        query = query.filter(PromptTrace.analysis_record_id == analysis_record_id)
    if model:
        query = query.filter(PromptTrace.model == model)
    return query.order_by(PromptTrace.created_at.desc(), PromptTrace.id.desc()).all()


@router.get("/summary", summary="Prompt trace summary")
async def prompt_trace_summary(
    source: Optional[str] = Query(None),
    prompt_version: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None),
    task_id: Optional[int] = Query(None),
    analysis_record_id: Optional[int] = Query(None),
    model: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = _query_rows(
        db,
        user_id=current_user.id,
        source=source,
        prompt_version=prompt_version,
        status=status,
        request_id=request_id,
        task_id=task_id,
        analysis_record_id=analysis_record_id,
        model=model,
    )

    by_source: dict[str, list[PromptTrace]] = {}
    by_version: dict[tuple[str, str], list[PromptTrace]] = {}
    for row in rows:
        source_key = row.source or "unknown"
        version_key = row.prompt_version or "unknown"
        by_source.setdefault(source_key, []).append(row)
        by_version.setdefault((source_key, version_key), []).append(row)

    source_groups = [
        _build_group_item(group_source, group_rows, group_type="source")
        for group_source, group_rows in by_source.items()
    ]
    source_groups.sort(key=lambda item: (item["total"], item["success_count"]), reverse=True)

    version_groups = []
    for (group_source, version), group_rows in by_version.items():
        version_groups.append(
            _build_group_item(version, group_rows, group_type="prompt_version", source=group_source)
        )
    version_groups.sort(key=lambda item: (item["total"], item["last_seen"] or ""), reverse=True)

    versions = sorted({item["prompt_version"] for item in version_groups})
    sources = sorted({item["source"] for item in source_groups})
    models = sorted({row.model for row in rows if row.model})

    return ok(
        {
            **_metrics_from_rows(rows),
            "sources": sources,
            "versions": versions,
            "models": models,
            "source_groups": source_groups[:10],
            "version_groups": version_groups[:20],
        }
    )


@router.get("/list", summary="List prompt traces")
async def list_prompt_traces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: Optional[str] = Query(None),
    prompt_version: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None),
    task_id: Optional[int] = Query(None),
    analysis_record_id: Optional[int] = Query(None),
    model: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = _query_rows(
        db,
        user_id=current_user.id,
        source=source,
        prompt_version=prompt_version,
        status=status,
        request_id=request_id,
        task_id=task_id,
        analysis_record_id=analysis_record_id,
        model=model,
    )
    total = len(rows)
    start = (page - 1) * page_size
    items = rows[start:start + page_size]
    return ok(
        {
            "items": [item.to_summary_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/compare", summary="Compare prompt versions")
async def compare_prompt_versions(
    version_a: str = Query(..., min_length=1),
    version_b: str = Query(..., min_length=1),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows_a = _query_rows(
        db,
        user_id=current_user.id,
        source=source,
        prompt_version=version_a,
    )
    rows_b = _query_rows(
        db,
        user_id=current_user.id,
        source=source,
        prompt_version=version_b,
    )
    if not rows_a or not rows_b:
        return fail(message="compare versions not found", code=ERR_PARAM)

    metrics_a = _metrics_from_rows(rows_a)
    metrics_b = _metrics_from_rows(rows_b)

    def _delta(key: str) -> float | None:
        left = metrics_a.get(key)
        right = metrics_b.get(key)
        if left is None or right is None:
            return None
        return round(float(right) - float(left), 6)

    return ok(
        {
            "source": source or rows_a[0].source or rows_b[0].source,
            "version_a": {
                "prompt_version": version_a,
                "metrics": metrics_a,
                "recent_samples": [item.to_summary_dict() for item in rows_a[:5]],
            },
            "version_b": {
                "prompt_version": version_b,
                "metrics": metrics_b,
                "recent_samples": [item.to_summary_dict() for item in rows_b[:5]],
            },
            "delta": {
                "success_rate": _delta("success_rate"),
                "cache_hit_rate": _delta("cache_hit_rate"),
                "avg_duration_ms": _delta("avg_duration_ms"),
                "avg_prompt_chars": _delta("avg_prompt_chars"),
                "avg_total_tokens": _delta("avg_total_tokens"),
                "avg_cost_cents": _delta("avg_cost_cents"),
            },
        }
    )


@router.get("/{trace_id}", summary="Prompt trace detail")
async def get_prompt_trace_detail(
    trace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trace = (
        db.query(PromptTrace)
        .filter(PromptTrace.id == trace_id, PromptTrace.user_id == current_user.id)
        .first()
    )
    if not trace:
        return fail(message="prompt trace not found", code=ERR_PARAM)
    return ok(trace.to_dict())


@router.post("/{trace_id}/feedback", summary="Update prompt trace feedback")
async def update_prompt_trace_feedback(
    trace_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trace = (
        db.query(PromptTrace)
        .filter(PromptTrace.id == trace_id, PromptTrace.user_id == current_user.id)
        .first()
    )
    if not trace:
        return fail(message="prompt trace not found", code=ERR_PARAM)

    feedback_label = str(payload.get("feedback_label") or "").strip()
    if not feedback_label:
        return fail(message="feedback_label is required", code=ERR_PARAM)

    updated = update_prompt_feedback(
        db,
        trace_id=trace_id,
        feedback_label=feedback_label,
        feedback_note=payload.get("feedback_note"),
        feedback_score=payload.get("feedback_score"),
    )
    return ok(updated.to_dict(), message="feedback updated")
