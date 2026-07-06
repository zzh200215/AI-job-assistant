# -*- coding: utf-8 -*-
"""Candidate screening service for enterprise-style batch comparison."""

from __future__ import annotations

import csv
import io
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.models.candidate_screening import CandidateScreeningSession
from app.models.history import JobDescription, Resume
from app.services.match_explainer_service import MatchExplainer


def _safe_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _candidate_name(resume: Resume) -> str:
    parsed = resume.parsed_json or {}
    return parsed.get("name") or resume.name or resume.file_name or f"候选人#{resume.id}"


def _candidate_skills(resume: Resume) -> list[str]:
    parsed = resume.parsed_json or {}
    return _safe_list(parsed.get("skills"))


def _dimension_score_map(explain_result) -> dict[str, dict[str, Any]]:
    mapping = {}
    for item in explain_result.to_dict().get("dimensions", []):
        mapping[item.get("name") or ""] = item
    return mapping


def screen_candidates(
    db: Session,
    *,
    user_id: int,
    jd: JobDescription,
    resumes: list[Resume],
    top_k: int = 10,
) -> dict[str, Any]:
    """Score and rank resumes against one JD."""
    explainer = MatchExplainer()
    results = []
    recommendation_counter: Counter[str] = Counter()
    skill_gap_counter: Counter[str] = Counter()

    for resume in resumes:
        explain_result = explainer.explain(resume, jd)
        explain_data = explain_result.to_dict()
        recommendation = explain_data.get("recommendation", "")
        recommendation_counter[recommendation] += 1

        missing_required = _safe_list(explain_data.get("skill_match", {}).get("missing_required"))
        for skill in missing_required:
            skill_gap_counter[skill] += 1

        dimension_map = _dimension_score_map(explain_result)
        candidate = {
            "resume_id": resume.id,
            "candidate_name": _candidate_name(resume),
            "file_name": resume.file_name,
            "years_exp": (resume.parsed_json or {}).get("years_exp") or resume.years_exp or 0,
            "skills": _candidate_skills(resume),
            "overall_score": explain_data.get("overall_score", 0),
            "recommendation": recommendation,
            "overall_reason": explain_data.get("overall_reason", ""),
            "risk_points": explain_data.get("risk_points", [])[:3],
            "optimization_suggestions": explain_data.get("optimization_suggestions", [])[:3],
            "matched_skills": _safe_list(explain_data.get("skill_match", {}).get("matched")),
            "missing_required_skills": missing_required,
            "dimension_scores": {
                "skills": dimension_map.get("技能匹配", {}),
                "project": dimension_map.get("项目经历", {}),
                "experience": dimension_map.get("工作经验", {}),
                "education": dimension_map.get("学历要求", {}),
                "keyword": dimension_map.get("关键词覆盖", {}),
                "bonus": dimension_map.get("加分项", {}),
            },
        }
        results.append(candidate)

    results.sort(
        key=lambda item: (
            float(item.get("overall_score", 0)),
            len(item.get("matched_skills", [])),
            -len(item.get("missing_required_skills", [])),
            float(item.get("years_exp", 0)),
        ),
        reverse=True,
    )

    top_results = results[:top_k]
    summary = {
        "jd_id": jd.id,
        "jd_title": jd.title,
        "company": jd.company,
        "total_candidates": len(results),
        "returned_candidates": len(top_results),
        "recommendation_distribution": dict(recommendation_counter),
        "most_common_skill_gaps": [
            {"skill": skill, "count": count}
            for skill, count in skill_gap_counter.most_common(8)
        ],
        "top_candidate_ids": [item["resume_id"] for item in top_results[:3]],
    }
    return {"summary": summary, "candidates": top_results}


def save_screening_session(
    db: Session,
    *,
    user_id: int,
    jd: JobDescription,
    request_payload: dict[str, Any],
    result_payload: dict[str, Any],
    name: str = "",
) -> CandidateScreeningSession:
    top_candidate = (result_payload.get("candidates") or [{}])[0]
    session = CandidateScreeningSession(
        user_id=user_id,
        jd_id=jd.id,
        name=name or f"{jd.title} 筛选记录",
        jd_title=jd.title or "",
        company=jd.company or "",
        candidate_count=len(result_payload.get("candidates") or []),
        top_candidate_name=top_candidate.get("candidate_name", "") if isinstance(top_candidate, dict) else "",
        request_payload=request_payload,
        result_payload=result_payload,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_screening_sessions(db: Session, *, user_id: int) -> list[CandidateScreeningSession]:
    return (
        db.query(CandidateScreeningSession)
        .filter(CandidateScreeningSession.user_id == user_id)
        .order_by(CandidateScreeningSession.updated_at.desc(), CandidateScreeningSession.id.desc())
        .all()
    )


def get_screening_session(
    db: Session,
    *,
    user_id: int,
    session_id: int,
) -> CandidateScreeningSession | None:
    return (
        db.query(CandidateScreeningSession)
        .filter(
            CandidateScreeningSession.id == session_id,
            CandidateScreeningSession.user_id == user_id,
        )
        .first()
    )


def export_screening_session_csv(session: CandidateScreeningSession) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "rank",
            "resume_id",
            "candidate_name",
            "file_name",
            "years_exp",
            "overall_score",
            "recommendation",
            "matched_skills",
            "missing_required_skills",
            "risk_points",
            "optimization_suggestions",
        ]
    )
    candidates = ((session.result_payload or {}).get("candidates") or [])
    for index, item in enumerate(candidates, start=1):
        writer.writerow(
            [
                index,
                item.get("resume_id", ""),
                item.get("candidate_name", ""),
                item.get("file_name", ""),
                item.get("years_exp", 0),
                item.get("overall_score", 0),
                item.get("recommendation", ""),
                " / ".join(item.get("matched_skills", []) or []),
                " / ".join(item.get("missing_required_skills", []) or []),
                " / ".join(item.get("risk_points", []) or []),
                " / ".join(item.get("optimization_suggestions", []) or []),
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")
