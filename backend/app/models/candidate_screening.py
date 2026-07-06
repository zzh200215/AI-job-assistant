# -*- coding: utf-8 -*-
"""Candidate screening workspace persistence models."""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, JSON, String

from app.core.database import Base
from app.utils.time_helper import utc_now


class CandidateScreeningSession(Base):
    __tablename__ = "candidate_screening_session"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="SET NULL"), nullable=True, index=True)

    name = Column(String(200), default="", index=True, comment="筛选记录名称")
    jd_title = Column(String(200), default="", index=True)
    company = Column(String(200), default="", index=True)
    candidate_count = Column(BigInteger, default=0)
    top_candidate_name = Column(String(100), default="")

    request_payload = Column(JSON, comment="原始请求快照")
    result_payload = Column(JSON, comment="筛选结果快照")

    created_at = Column(DateTime, default=utc_now, index=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    def to_dict(self):
        result_payload = self.result_payload or {}
        summary = result_payload.get("summary", {}) if isinstance(result_payload, dict) else {}
        return {
            "id": self.id,
            "user_id": self.user_id,
            "jd_id": self.jd_id,
            "name": self.name or "",
            "jd_title": self.jd_title or "",
            "company": self.company or "",
            "candidate_count": int(self.candidate_count or 0),
            "top_candidate_name": self.top_candidate_name or "",
            "request_payload": self.request_payload or {},
            "result_payload": result_payload,
            "summary": summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
