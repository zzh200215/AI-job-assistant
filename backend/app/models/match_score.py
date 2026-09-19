"""Canonical resume↔job match scores (A4).

Before this table existed, three code paths each produced their own number for
the same (resume, job) pair — the recommend engine's vector/rule blend, the
explainer's 6-dimension weighted rubric, and a raw LLM score clipped to 0-100 —
and none of them applied `infer_match_score_cap`. The recommend page and the
explain page therefore showed different matches for the same job.

One row per (resume_id, resume_version, jd_id) is now the only displayed score.
"""

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, String, Text

from app.core.database import Base
from app.models.base import TenantScopedMixin
from app.services.scoring_config import SCORE_METHOD
from app.utils.time_helper import utc_now


class MatchScore(TenantScopedMixin, Base):
    """Persisted canonical match score for one resume version against one JD."""

    __tablename__ = "match_score"
    __table_args__ = (
        Index("uq_match_score_resume_version_jd", "resume_id", "resume_version", "jd_id", unique=True),
        Index("ix_match_score_tenant_user", "tenant_id", "user_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = Column(BigInteger, ForeignKey("tb_resume.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_version = Column(String(64), nullable=False, comment="Hash of the parsed resume the score was computed from")
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="CASCADE"), nullable=False, index=True)

    score = Column(Float, nullable=False, comment="Canonical 0-100 match score, after any cap")
    raw_score = Column(Float, nullable=False, comment="Rubric score before the weak-fit cap")
    cap_applied = Column(Float, nullable=True, comment="Weak-fit cap that bound the score, if any")
    method = Column(String(32), nullable=False, default=SCORE_METHOD, comment="Scoring method identifier")

    dimensions_json = Column(Text, comment="Per-dimension breakdown, JSON")
    skill_gap_json = Column(Text, comment="Missing skills driving the gap, JSON")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def to_dict(self) -> dict:
        import json

        def _load(raw):
            if not raw:
                return None
            try:
                return json.loads(raw)
            except (ValueError, TypeError):
                return None

        return {
            "id": self.id,
            "user_id": self.user_id,
            "resume_id": self.resume_id,
            "resume_version": self.resume_version,
            "jd_id": self.jd_id,
            "score": round(float(self.score), 1),
            "raw_score": round(float(self.raw_score), 1),
            "cap_applied": self.cap_applied,
            "method": self.method,
            "dimensions": _load(self.dimensions_json) or [],
            "skill_gap": _load(self.skill_gap_json) or [],
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
