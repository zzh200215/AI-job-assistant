# -*- coding: utf-8 -*-
"""Offline evaluation report APIs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from app.api.auth import get_current_user
from app.models.user import User
from app.utils.response import ERR_PARAM, fail, ok

router = APIRouter()

REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"
SUPPORTED_REPORT_TYPES = {"rag", "agent", "recommend"}


def _ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _report_id_from_path(path: Path) -> str:
    return path.name


def _resolve_report_path(report_id: str) -> Path | None:
    candidate = (REPORTS_DIR / Path(report_id).name).resolve()
    try:
        candidate.relative_to(REPORTS_DIR.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _infer_report_type(path: Path, payload: dict[str, Any]) -> str | None:
    report_type = payload.get("report_type")
    if report_type in SUPPORTED_REPORT_TYPES:
        return report_type
    name = path.name.lower()
    if name.startswith("rag_eval"):
        return "rag"
    if name.startswith("agent_eval"):
        return "agent"
    if name.startswith("recommend_eval"):
        return "recommend"
    if any(str(key).startswith("recall@") for key in payload):
        return "rag"
    if "mae" in payload and "spearman_rho" in payload:
        return "agent"
    if "skill_match_accuracy" in payload and "jd_explanation_consistency" in payload:
        return "recommend"
    return None


def _rag_recall_key(payload: dict[str, Any]) -> str | None:
    keys = sorted(str(key) for key in payload if str(key).startswith("recall@"))
    return keys[0] if keys else None


def _normalize_report(path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    report_type = _infer_report_type(path, payload)
    if report_type not in SUPPORTED_REPORT_TYPES:
        return None

    run_meta = payload.get("run_meta") if isinstance(payload.get("run_meta"), dict) else {}
    generated_at = _parse_datetime(run_meta.get("generated_at")) or datetime.fromtimestamp(
        path.stat().st_mtime,
        tz=timezone.utc,
    )

    base = {
        "report_id": _report_id_from_path(path),
        "filename": path.name,
        "report_type": report_type,
        "generated_at": generated_at.isoformat(),
        "eval_set": run_meta.get("eval_set"),
        "sample": run_meta.get("sample"),
        "thresholds": run_meta.get("thresholds") if isinstance(run_meta.get("thresholds"), dict) else {},
        "total": int(payload.get("total") or 0),
    }

    if report_type == "rag":
        recall_key = _rag_recall_key(payload)
        metrics = {
            "recall": payload.get(recall_key) if recall_key else None,
            "recall_label": recall_key,
            "mrr": payload.get("mrr"),
            "keyword_hit_rate": payload.get("keyword_hit_rate"),
        }
        return {
            **base,
            "metrics": metrics,
            "top_k": run_meta.get("top_k"),
            "per_doc_type_recall": payload.get("per_doc_type_recall") or {},
            "details_count": len(payload.get("details") or []),
        }

    if report_type == "recommend":
        linkage = (
            payload.get("online_feedback_linkage")
            if isinstance(payload.get("online_feedback_linkage"), dict)
            else {}
        )
        metrics = {
            "skill_match_accuracy": payload.get("skill_match_accuracy"),
            "jd_explanation_consistency": payload.get("jd_explanation_consistency"),
            "recommendation_explainability": payload.get("recommendation_explainability"),
            "interview_score_stability": payload.get("interview_score_stability"),
            "feedback_agreement_rate": payload.get("feedback_agreement_rate"),
        }
        return {
            **base,
            "metrics": metrics,
            "linked_feedback_count": int(linkage.get("linked_feedback_count") or 0),
            "linked_pair_count": int(linkage.get("linked_pair_count") or 0),
            "details_count": len(payload.get("details") or []),
        }

    score_dist = payload.get("score_dist") if isinstance(payload.get("score_dist"), dict) else {}
    metrics = {
        "mae": payload.get("mae"),
        "spearman_rho": payload.get("spearman_rho"),
        "hit_tol10": score_dist.get("hit_tol10"),
        "over": score_dist.get("over"),
        "under": score_dist.get("under"),
    }
    return {
        **base,
        "metrics": metrics,
        "score_dist": score_dist,
        "details_count": len(payload.get("details") or []),
    }


def _list_reports(report_type: Optional[str] = None) -> list[dict[str, Any]]:
    _ensure_reports_dir()
    items: list[dict[str, Any]] = []
    for path in REPORTS_DIR.glob("*.json"):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        item = _normalize_report(path, payload)
        if not item:
            continue
        if report_type and item["report_type"] != report_type:
            continue
        items.append(item)
    items.sort(key=lambda item: (item["generated_at"], item["filename"]), reverse=True)
    return items


def _load_report_detail(report_id: str) -> tuple[dict[str, Any], dict[str, Any]] | tuple[None, None]:
    path = _resolve_report_path(report_id)
    if not path:
        return None, None
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return None, None
    summary = _normalize_report(path, payload)
    if not summary:
        return None, None
    return summary, payload


def _compare_reports(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    report_type = left["report_type"]
    if report_type == "rag":
        return {
            "recall": _delta(left["metrics"].get("recall"), right["metrics"].get("recall")),
            "mrr": _delta(left["metrics"].get("mrr"), right["metrics"].get("mrr")),
            "keyword_hit_rate": _delta(
                left["metrics"].get("keyword_hit_rate"),
                right["metrics"].get("keyword_hit_rate"),
            ),
        }
    if report_type == "recommend":
        return {
            "skill_match_accuracy": _delta(
                left["metrics"].get("skill_match_accuracy"),
                right["metrics"].get("skill_match_accuracy"),
            ),
            "jd_explanation_consistency": _delta(
                left["metrics"].get("jd_explanation_consistency"),
                right["metrics"].get("jd_explanation_consistency"),
            ),
            "recommendation_explainability": _delta(
                left["metrics"].get("recommendation_explainability"),
                right["metrics"].get("recommendation_explainability"),
            ),
            "interview_score_stability": _delta(
                left["metrics"].get("interview_score_stability"),
                right["metrics"].get("interview_score_stability"),
            ),
            "feedback_agreement_rate": _delta(
                left["metrics"].get("feedback_agreement_rate"),
                right["metrics"].get("feedback_agreement_rate"),
            ),
        }
    return {
        "mae": _delta(left["metrics"].get("mae"), right["metrics"].get("mae")),
        "spearman_rho": _delta(left["metrics"].get("spearman_rho"), right["metrics"].get("spearman_rho")),
        "hit_tol10": _delta(left["metrics"].get("hit_tol10"), right["metrics"].get("hit_tol10")),
        "over": _delta(left["metrics"].get("over"), right["metrics"].get("over")),
        "under": _delta(left["metrics"].get("under"), right["metrics"].get("under")),
    }


def _delta(left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    try:
        return round(float(right) - float(left), 6)
    except (TypeError, ValueError):
        return None


@router.get("/summary", summary="Offline evaluation report summary")
async def evaluation_summary(
    report_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    if report_type and report_type not in SUPPORTED_REPORT_TYPES:
        return fail(message="unsupported report_type", code=ERR_PARAM)

    items = _list_reports(report_type=report_type)
    latest_by_type: dict[str, dict[str, Any]] = {}
    counts = {key: 0 for key in sorted(SUPPORTED_REPORT_TYPES)}
    for item in items:
        counts[item["report_type"]] += 1
        latest_by_type.setdefault(item["report_type"], item)

    return ok(
        {
            "total": len(items),
            "counts": counts,
            "latest_by_type": latest_by_type,
            "types": sorted(SUPPORTED_REPORT_TYPES),
        }
    )


@router.get("/list", summary="List offline evaluation reports")
async def list_evaluation_reports(
    report_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    if report_type and report_type not in SUPPORTED_REPORT_TYPES:
        return fail(message="unsupported report_type", code=ERR_PARAM)
    items = _list_reports(report_type=report_type)
    return ok({"items": items, "total": len(items)})


@router.get("/compare", summary="Compare two offline evaluation reports")
async def compare_evaluation_reports(
    report_a: str = Query(..., min_length=1),
    report_b: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    left_summary, left_raw = _load_report_detail(report_a)
    right_summary, right_raw = _load_report_detail(report_b)
    if not left_summary or not right_summary:
        return fail(message="report not found", code=ERR_PARAM)
    if left_summary["report_type"] != right_summary["report_type"]:
        return fail(message="report types do not match", code=ERR_PARAM)

    return ok(
        {
            "report_type": left_summary["report_type"],
            "report_a": {"summary": left_summary, "raw": left_raw},
            "report_b": {"summary": right_summary, "raw": right_raw},
            "delta": _compare_reports(left_summary, right_summary),
        }
    )


@router.get("/{report_id}", summary="Get offline evaluation report detail")
async def get_evaluation_report_detail(
    report_id: str,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    summary, payload = _load_report_detail(report_id)
    if not summary or not payload:
        return fail(message="report not found", code=ERR_PARAM)
    return ok({"summary": summary, "raw": payload})
