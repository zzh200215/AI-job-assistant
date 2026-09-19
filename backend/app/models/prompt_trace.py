"""Prompt trace ORM model for lightweight LLM observability."""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Float, ForeignKey, Integer, SmallInteger, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


def _preview(value, limit: int = 180) -> str:
    text = "" if value is None else str(value)
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


class PromptTrace(Base):
    """Single structured LLM call trace."""

    __tablename__ = "prompt_trace"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(100), index=True, comment="HTTP request id")
    source = Column(String(120), index=True, comment="Callsite source module:function")
    prompt_version = Column(String(50), comment="Prompt render/version marker")
    prompt_family = Column(String(50), index=True, comment="Prompt family / feature group")
    prompt_name = Column(String(100), index=True, comment="Canonical prompt name")
    provider = Column(String(20), nullable=False, comment="LLM provider")
    model = Column(String(100), comment="Effective model used")
    response_source = Column(
        String(20),
        nullable=False,
        default="unknown",
        index=True,
        comment="real/mock/truncated/fallback_model; provider above is only the configured value",
    )
    degraded = Column(
        SmallInteger,
        nullable=False,
        default=0,
        comment="1 when the response did not come from the configured primary model",
    )
    status = Column(String(20), nullable=False, default="success", comment="success/failed")
    cache_hit = Column(SmallInteger, nullable=False, default=0, comment="Whether response came from cache")
    duration_ms = Column(Integer, comment="End-to-end duration in milliseconds")
    prompt_chars = Column(Integer, comment="Prompt length in characters")
    prompt_hash = Column(String(32), index=True, comment="Prompt content hash")
    prompt_text = Column(Text, comment="Original prompt text")
    response_text = Column(Text, comment="Raw model response text")
    response_json = Column(JSON, comment="Parsed JSON response")
    error_message = Column(Text, comment="Error when call/parsing failed")
    trace_context = Column(JSON, comment="Request / business context for traceability")
    prompt_metadata = Column(JSON, comment="Prompt metadata and rendered version info")
    feedback_label = Column(String(50), index=True, comment="Human feedback label")
    feedback_note = Column(Text, comment="Human feedback note")
    feedback_score = Column(Float, comment="Human feedback score")
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_cents = Column(Float, nullable=False, default=0.0)
    task_id = Column(BigInteger, ForeignKey("agent_task.id", ondelete="SET NULL"), index=True)
    analysis_record_id = Column(BigInteger, ForeignKey("tb_analysis_record.id", ondelete="SET NULL"), index=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id", ondelete="SET NULL"), index=True)
    resume_id = Column(BigInteger, ForeignKey("tb_resume.id", ondelete="SET NULL"), index=True)
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="SET NULL"), index=True)
    created_at = Column(DateTime, default=utc_now, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "request_id": self.request_id,
            "source": self.source,
            "prompt_version": self.prompt_version,
            "prompt_family": self.prompt_family,
            "prompt_name": self.prompt_name,
            "provider": self.provider,
            "model": self.model,
            "response_source": self.response_source or "unknown",
            "degraded": bool(self.degraded),
            "status": self.status,
            "cache_hit": bool(self.cache_hit),
            "duration_ms": self.duration_ms,
            "prompt_chars": self.prompt_chars,
            "prompt_hash": self.prompt_hash,
            "prompt_text": self.prompt_text,
            "response_text": self.response_text,
            "response_json": self.response_json,
            "error_message": self.error_message,
            "trace_context": self.trace_context or {},
            "prompt_metadata": self.prompt_metadata or {},
            "feedback_label": self.feedback_label,
            "feedback_note": self.feedback_note,
            "feedback_score": self.feedback_score,
            "prompt_tokens": int(self.prompt_tokens or 0),
            "completion_tokens": int(self.completion_tokens or 0),
            "total_tokens": int(self.total_tokens or 0),
            "cost_cents": round(float(self.cost_cents or 0.0), 6),
            "task_id": self.task_id,
            "analysis_record_id": self.analysis_record_id,
            "user_id": self.user_id,
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_summary_dict(self) -> dict:
        return {
            "id": self.id,
            "request_id": self.request_id,
            "source": self.source,
            "prompt_version": self.prompt_version,
            "prompt_family": self.prompt_family,
            "prompt_name": self.prompt_name,
            "provider": self.provider,
            "model": self.model,
            "response_source": self.response_source or "unknown",
            "degraded": bool(self.degraded),
            "status": self.status,
            "cache_hit": bool(self.cache_hit),
            "duration_ms": self.duration_ms,
            "prompt_chars": self.prompt_chars,
            "prompt_hash": self.prompt_hash,
            "prompt_preview": _preview(self.prompt_text),
            "response_preview": _preview(self.response_text),
            "error_message": _preview(self.error_message, limit=120),
            "feedback_label": self.feedback_label,
            "feedback_note": _preview(self.feedback_note, limit=120),
            "feedback_score": self.feedback_score,
            "prompt_tokens": int(self.prompt_tokens or 0),
            "completion_tokens": int(self.completion_tokens or 0),
            "total_tokens": int(self.total_tokens or 0),
            "cost_cents": round(float(self.cost_cents or 0.0), 6),
            "task_id": self.task_id,
            "analysis_record_id": self.analysis_record_id,
            "user_id": self.user_id,
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
