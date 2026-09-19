"""A4: the single authority for a displayed match score.

One (resume, resume_version, jd) maps to exactly one number. The recommend
engine, the explain page and the full-analysis flow all read through here, so
the same job cannot show 82% in one place and 67% in another.

The number is the 6-dimension rubric from MatchExplainer — deterministic,
explainable and free — bounded above by `infer_match_score_cap`, which used to be
applied only inside the agent graph and never on the two paths candidates
actually see.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription, Resume
from app.models.match_score import MatchScore
from app.services.match_explainer_service import MatchExplainer

logger = logging.getLogger(__name__)

METHOD = "rubric_6dim"


def resume_version_of(resume: Resume) -> str:
    """Version identity for a resume: a hash of the text scoring actually reads.

    `Resume.update_time` is MySQL DATETIME(0), so a timestamp version collides for
    any two writes inside the same second — an applied rewrite would keep serving
    cached scores for the pre-edit resume. `parsed_json` is the only input the
    rubric and the recommender read (see MatchExplainer and
    JobRecommendEngine._build_vector_text), so hashing it both tracks every real
    change and ignores edits that cannot move a score.

    Single source of truth: the recommendation cache imports this instead of
    restating it, so the two cache layers cannot disagree.
    """
    payload = json.dumps(resume.parsed_json or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def compute_canonical_score(resume: Resume, jd: JobDescription) -> dict[str, Any]:
    """Pure computation, no persistence. The rubric already applies the cap."""
    explainer = MatchExplainer()
    rubric = explainer.compute_rubric(resume, jd)

    score = max(0.0, min(100.0, float(rubric["overall"])))
    dims = rubric["dims"]
    return {
        "score": round(score, 1),
        "raw_score": round(float(rubric["raw_score"]), 1),
        "cap_applied": rubric["cap_applied"],
        "method": METHOD,
        "dimensions": [
            {
                "name": d.name,
                "score": round(d.score, 1),
                "weight": d.weight,
                "weighted_score": round(d.weighted_score, 1),
                "details": d.details,
            }
            for d in dims
        ],
        "skill_gap": list(rubric["skill_match"].get("missing_required") or []),
    }


def canonical_match_score(
    db: Session,
    resume: Resume,
    jd: JobDescription,
    *,
    user_id: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Return the one authoritative match score for this pair.

    Reads the persisted row when the same resume version has already been
    scored, so ranking a list of jobs does not redo the rubric for jobs scored
    moments ago, and so the number a candidate saw cannot drift between visits.
    """
    version = resume_version_of(resume)
    owner = user_id if user_id is not None else getattr(resume, "user_id", None)

    existing = (
        db.query(MatchScore)
        .filter(
            MatchScore.resume_id == resume.id,
            MatchScore.resume_version == version,
            MatchScore.jd_id == jd.id,
        )
        .first()
    )
    if existing is not None:
        return existing.to_dict()

    computed = compute_canonical_score(resume, jd)

    if persist and owner is not None:
        try:
            row = MatchScore(
                user_id=owner,
                resume_id=resume.id,
                resume_version=version,
                jd_id=jd.id,
                score=computed["score"],
                raw_score=computed["raw_score"],
                cap_applied=computed["cap_applied"],
                method=computed["method"],
                dimensions_json=_serialize(computed["dimensions"]),
                skill_gap_json=_serialize(computed["skill_gap"]),
            )
            db.add(row)
            db.commit()
        except Exception:
            # A failed cache write must not take the recommendation list down;
            # the score itself is deterministic and was already computed.
            db.rollback()
            logger.exception("failed to persist canonical match score for jd=%s", jd.id)

    return computed
