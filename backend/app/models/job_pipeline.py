# -*- coding: utf-8 -*-
"""投递流程 ORM 模型"""
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Text, JSON, Integer

from app.core.database import Base
from app.utils.time_helper import utc_now


class JobApplicationPipeline(Base):
    __tablename__ = "job_application_pipeline"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = Column(BigInteger, ForeignKey("tb_resume.id", ondelete="SET NULL"), nullable=True, index=True)
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String(200), nullable=False, index=True)
    company = Column(String(200), default="", index=True)
    location = Column(String(100), default="")
    salary_range = Column(String(100), default="")
    source = Column(String(20), default="manual")
    source_url = Column(String(500), default="")
    summary = Column(Text)
    raw_text = Column(Text)
    experience_requirement = Column(String(50), default="")
    education_requirement = Column(String(50), default="")
    industry = Column(String(100), default="")
    skill_tags = Column(JSON, comment="岗位技能标签")

    priority_score = Column(Integer, default=0)
    priority_label = Column(String(50), default="")

    stage = Column(String(20), nullable=False, default="todo", index=True, comment="todo/applied/interview/rejected")
    note = Column(Text)
    next_action = Column(String(255), default="")
    follow_up_at = Column(DateTime, nullable=True)
    resume_name = Column(String(255), default="")
    stage_history = Column(JSON, comment="阶段流转历史")

    create_time = Column(DateTime, default=utc_now, index=True)
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary_range": self.salary_range,
            "source": self.source,
            "source_url": self.source_url,
            "summary": self.summary or "",
            "raw_text": self.raw_text or "",
            "experience_requirement": self.experience_requirement or "",
            "education_requirement": self.education_requirement or "",
            "industry": self.industry or "",
            "skill_tags": self.skill_tags or [],
            "priority_score": self.priority_score or 0,
            "priority_label": self.priority_label or "",
            "stage": self.stage,
            "note": self.note or "",
            "next_action": self.next_action or "",
            "follow_up_at": self.follow_up_at.isoformat() if self.follow_up_at else None,
            "resume_name": self.resume_name or "",
            "stage_history": self.stage_history or [],
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "update_time": self.update_time.isoformat() if self.update_time else None,
        }
