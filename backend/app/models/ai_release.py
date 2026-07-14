"""Versioned AI release records and their evaluation gate evidence."""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class AIRelease(Base):
    """An administrator-owned model and prompt release candidate."""

    __tablename__ = "ai_release"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    release_key = Column(String(100), nullable=False, unique=True, index=True)
    provider = Column(String(30), nullable=False)
    model = Column(String(120), nullable=False)
    prompt_versions = Column(JSON, nullable=False, default=list)
    evaluation_reports = Column(JSON, nullable=False, default=list)
    gate_result = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="draft", index=True)
    notes = Column(Text, default="")
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    approved_by = Column(BigInteger)
    approved_at = Column(DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "release_key": self.release_key,
            "provider": self.provider,
            "model": self.model,
            "prompt_versions": self.prompt_versions or [],
            "evaluation_reports": self.evaluation_reports or [],
            "gate_result": self.gate_result or {},
            "status": self.status,
            "notes": self.notes or "",
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
        }
