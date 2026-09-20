"""B2.3: career directions derived from real postings, not from a model's impression.

`/career-path/recommend` previously handed the model a resume summary and got back
plausible-sounding directions with invented `gap_skills`. Everything a direction
claims now comes from this module: which postings were counted, how much of their
requirement set the candidate already covers, what is missing, and what those
postings pay. The model is only asked to rank and explain what is already true.

A direction is marked `degraded` when its sample is too thin to carry the claim,
and the caller shows that instead of hiding it — a career plan built on one job
posting must say so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription
from app.models.user import User
from app.services.salary_evidence import MIN_RELIABLE_SAMPLE, SalarySample, parse_salary_range, summarize
from app.services.skill_gap import aggregate_skill_gaps, build_skill_gap
from app.utils.job_access import accessible_job_query

# Words that only ever modify a role, so "高级前端工程师" and "前端工程师" group
# together. 经理/总监/主管/专家 are deliberately *not* here: they are part of role
# names too ("产品经理"), and folding those away would merge unrelated directions.
_CJK_SENIORITY = ("首席", "资深", "高级", "初级", "中级", "助理", "实习")
_LATIN_SENIORITY = {"junior", "senior", "staff", "principal", "lead", "head", "architect"}
_NON_WORD = re.compile(r"[^\w\u4e00-\u9fff+#]+")
# Chinese has no word separators, so a space touching a CJK run is layout noise:
# "AI 算法工程师" and "AI算法工程师" are one direction, while "backend engineer"
# keeps its internal spaces.
_SPACE_AROUND_CJK = re.compile(r"(?<=[\u4e00-\u9fff])\s+|\s+(?=[\u4e00-\u9fff])")

MIN_DIRECTION_SAMPLES = 2


def direction_key(title: Any) -> str:
    """Group postings by what the role is, ignoring seniority and punctuation."""
    text = _NON_WORD.sub(" ", str(title or "").strip().lower())
    for token in _CJK_SENIORITY:
        text = text.replace(token, "")
    text = _SPACE_AROUND_CJK.sub("", text)
    return " ".join(token for token in text.split() if token and token not in _LATIN_SENIORITY)


@dataclass
class CareerDirection:
    key: str
    label: str
    jd_ids: list[int] = field(default_factory=list)
    sample_count: int = 0
    required_total: int = 0
    matched_skills: list[str] = field(default_factory=list)
    gap_skills: list[dict[str, Any]] = field(default_factory=list)
    coverage: float | None = None
    salary: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False
    degrade_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction_key": self.key,
            "label": self.label,
            "jd_ids": list(self.jd_ids),
            "sample_count": self.sample_count,
            "required_total": self.required_total,
            "matched_skills": list(self.matched_skills),
            "gap_skills": [dict(row) for row in self.gap_skills],
            "coverage": self.coverage,
            "salary": dict(self.salary),
            "degraded": self.degraded,
            "degrade_reasons": list(self.degrade_reasons),
        }


def _salary_for(jobs: list[JobDescription]) -> dict[str, Any]:
    samples = []
    for jd in jobs:
        parsed = parse_salary_range(jd.salary_range)
        if not parsed:
            continue
        low, high = parsed
        samples.append(
            SalarySample(
                jd_id=jd.id,
                title=jd.title or "",
                company=jd.company or "",
                location=jd.location or "",
                raw=str(jd.salary_range),
                min_k=low,
                max_k=high,
                mid_k=round((low + high) / 2, 1),
            )
        )
    evidence = summarize(samples, total_jds=len(jobs))
    return {
        "has_data": evidence.has_data,
        "sample_size": evidence.sample_size,
        "p25": evidence.p25,
        "p50": evidence.p50,
        "p75": evidence.p75,
        "low_confidence": evidence.low_confidence,
        "sample_jd_ids": evidence.sample_jd_ids,
    }


def derive_directions(
    db: Session,
    resume_parsed: dict[str, Any] | None,
    user: User,
    *,
    limit: int = 8,
    min_samples: int = MIN_DIRECTION_SAMPLES,
) -> tuple[list[CareerDirection], dict[str, Any]]:
    """Group the candidate's visible postings into directions and measure them."""
    jobs = accessible_job_query(db, user).filter(JobDescription.is_active == 1).order_by(JobDescription.id.asc()).all()
    parsed_resume = resume_parsed or {}

    groups: dict[str, list[JobDescription]] = {}
    for jd in jobs:
        key = direction_key(jd.title)
        if not key:
            continue
        groups.setdefault(key, []).append(jd)

    directions: list[CareerDirection] = []
    for key, group in groups.items():
        gaps = [
            build_skill_gap(
                parsed_resume,
                jd.parsed_json or {},
                jd_id=jd.id,
                title=jd.title or "",
                fallback_required=jd.skill_tags or [],
            )
            for jd in group
        ]

        required_union: set[str] = set()
        matched_union: set[str] = set()
        for gap in gaps:
            required_union.update(gap.matched_required)
            required_union.update(gap.missing_required)
            matched_union.update(gap.matched_required)

        salary = _salary_for(group)
        reasons: list[str] = []
        if len(group) < min_samples:
            reasons.append(f"仅 {len(group)} 条岗位样本")
        if not salary["has_data"]:
            reasons.append("样本岗位均未填写可解析薪资")
        elif salary["sample_size"] < MIN_RELIABLE_SAMPLE:
            reasons.append(f"薪资仅 {salary['sample_size']} 条可解析样本")

        directions.append(
            CareerDirection(
                key=key,
                label=group[0].title or key,
                jd_ids=sorted(jd.id for jd in group if jd.id is not None),
                sample_count=len(group),
                required_total=len(required_union),
                matched_skills=sorted(matched_union),
                gap_skills=aggregate_skill_gaps(gaps, limit=6),
                coverage=None if not required_union else round(len(matched_union) / len(required_union), 4),
                salary=salary,
                degraded=bool(reasons),
                degrade_reasons=reasons,
            )
        )

    directions.sort(key=lambda item: (-item.sample_count, -(item.coverage or 0), item.key))
    corpus = {
        "visible_jds": len(jobs),
        "directions_found": len(directions),
        "min_samples_per_direction": min_samples,
    }
    return directions[:limit], corpus
