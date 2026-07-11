# -*- coding: utf-8 -*-
"""投递流程 ORM 模型

阶段流转：todo → applied → written_test → interview → offer → accepted / rejected / withdrawn
"""
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Text, JSON, Integer, Float

from app.core.database import Base
from app.utils.time_helper import utc_now

# ===== 投递流程阶段常量 =====
STAGE_TODO = "todo"
STAGE_APPLIED = "applied"
STAGE_WRITTEN_TEST = "written_test"
STAGE_INTERVIEW = "interview"
STAGE_OFFER = "offer"
STAGE_ACCEPTED = "accepted"
STAGE_REJECTED = "rejected"
STAGE_WITHDRAWN = "withdrawn"

PIPELINE_STAGES = {
    STAGE_TODO, STAGE_APPLIED, STAGE_WRITTEN_TEST,
    STAGE_INTERVIEW, STAGE_OFFER, STAGE_ACCEPTED,
    STAGE_REJECTED, STAGE_WITHDRAWN,
}

# 看板分组：活跃阶段 vs 终态阶段
ACTIVE_STAGES = [STAGE_TODO, STAGE_APPLIED, STAGE_WRITTEN_TEST, STAGE_INTERVIEW, STAGE_OFFER]
TERMINAL_STAGES = [STAGE_ACCEPTED, STAGE_REJECTED, STAGE_WITHDRAWN]

# 合法的前后阶段流转
VALID_TRANSITIONS = {
    STAGE_TODO: {STAGE_APPLIED, STAGE_WITHDRAWN},
    STAGE_APPLIED: {STAGE_WRITTEN_TEST, STAGE_INTERVIEW, STAGE_REJECTED, STAGE_WITHDRAWN},
    STAGE_WRITTEN_TEST: {STAGE_INTERVIEW, STAGE_REJECTED, STAGE_WITHDRAWN},
    STAGE_INTERVIEW: {STAGE_OFFER, STAGE_REJECTED, STAGE_WITHDRAWN},
    STAGE_OFFER: {STAGE_ACCEPTED, STAGE_REJECTED, STAGE_WITHDRAWN},
    STAGE_ACCEPTED: set(),
    STAGE_REJECTED: set(),
    STAGE_WITHDRAWN: set(),
}


class JobApplicationPipeline(Base):
    __tablename__ = "job_application_pipeline"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = Column(BigInteger, ForeignKey("tb_resume.id", ondelete="SET NULL"), nullable=True, index=True)
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="SET NULL"), nullable=True, index=True)
    target_id = Column(BigInteger, ForeignKey("job_target.id", ondelete="SET NULL"), nullable=True, index=True, comment="关联求职目标ID")

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

    stage = Column(String(20), nullable=False, default=STAGE_TODO, index=True)
    note = Column(Text)
    next_action = Column(String(255), default="")
    follow_up_at = Column(DateTime, nullable=True)
    resume_name = Column(String(255), default="")
    stage_history = Column(JSON, comment="阶段流转历史")

    # ===== 面试相关字段 =====
    interview_at = Column(DateTime, nullable=True, comment="最近面试时间")
    interview_type = Column(String(20), default="", comment="面试类型: tech/hr/comprehensive/case")
    interview_round = Column(Integer, default=0, comment="当前面试轮次")
    interview_location = Column(String(255), default="", comment="面试地点/视频链接")
    interview_contact = Column(String(100), default="", comment="面试联系人")

    # ===== Offer 相关字段 =====
    offer_salary = Column(String(100), default="", comment="Offer 薪资")
    offer_details = Column(JSON, comment="Offer 详情: 保险/期权/签字费等")
    offer_deadline = Column(DateTime, nullable=True, comment="Offer 回复截止日期")

    create_time = Column(DateTime, default=utc_now, index=True)
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "target_id": self.target_id,
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
            "interview_at": self.interview_at.isoformat() if self.interview_at else None,
            "interview_type": self.interview_type or "",
            "interview_round": self.interview_round or 0,
            "interview_location": self.interview_location or "",
            "interview_contact": self.interview_contact or "",
            "offer_salary": self.offer_salary or "",
            "offer_details": self.offer_details or {},
            "offer_deadline": self.offer_deadline.isoformat() if self.offer_deadline else None,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "update_time": self.update_time.isoformat() if self.update_time else None,
        }
