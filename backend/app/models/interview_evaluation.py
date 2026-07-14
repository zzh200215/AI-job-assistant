"""Persistent per-turn interview evaluation records."""

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.time_helper import utc_now


class InterviewTurnEvaluation(Base):
    """One candidate answer and its structured evaluation evidence."""

    __tablename__ = "interview_turn_evaluation"
    __table_args__ = (UniqueConstraint("session_id", "turn_id", name="uq_interview_turn_evaluation_turn"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(BigInteger, ForeignKey("interview_session.id", ondelete="CASCADE"), nullable=False, index=True)
    turn_id = Column(String(80), nullable=False)
    question_index = Column(Integer, nullable=False, default=0)
    question = Column(Text, nullable=False, default="")
    category = Column(String(50), default="general")
    user_answer = Column(Text, default="")
    is_follow_up = Column(Integer, default=0)
    status = Column(String(20), nullable=False, default="pending", index=True)
    completeness = Column(Integer, default=0)
    accuracy = Column(Integer, default=0)
    depth = Column(Integer, default=0)
    expression = Column(Integer, default=0)
    overall_score = Column(Integer, default=0)
    feedback = Column(Text, default="")
    improvement = Column(Text, default="")
    evidence = Column(JSON)
    error_msg = Column(String(500), default="")
    created_at = Column(DateTime, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "turn_id": self.turn_id,
            "question_index": self.question_index,
            "question": self.question,
            "category": self.category or "general",
            "user_answer": self.user_answer or "",
            "is_follow_up": bool(self.is_follow_up),
            "status": self.status,
            "completeness": self.completeness or 0,
            "accuracy": self.accuracy or 0,
            "depth": self.depth or 0,
            "expression": self.expression or 0,
            "overall_score": self.overall_score or 0,
            "feedback": self.feedback or "",
            "improvement": self.improvement or "",
            "evidence": self.evidence or {},
            "error_msg": self.error_msg or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
