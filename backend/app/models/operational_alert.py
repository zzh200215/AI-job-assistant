"""Persistent operational alerts for administrator follow-up."""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class OperationalAlert(Base):
    """A deduplicated alert emitted by the platform health evaluator."""

    __tablename__ = "operational_alert"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    alert_key = Column(String(100), nullable=False, unique=True, index=True)
    severity = Column(String(20), nullable=False, default="warning", index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    context = Column(JSON, default=dict)
    occurrences = Column(Integer, nullable=False, default=1)
    first_seen_at = Column(DateTime, nullable=False, default=utc_now)
    last_seen_at = Column(DateTime, nullable=False, default=utc_now, index=True)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(BigInteger)
    resolved_at = Column(DateTime, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "alert_key": self.alert_key,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "context": self.context or {},
            "occurrences": int(self.occurrences or 0),
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
