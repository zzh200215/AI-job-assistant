# -*- coding: utf-8 -*-
"""求职目标 ORM 模型"""
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, JSON, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class JobTarget(Base):
    """求职目标表 — 用户可创建多个求职方向，每个方向独立管理"""
    __tablename__ = "job_target"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    name = Column(String(100), nullable=False, comment="目标名称，如'后端开发''架构师'")
    position = Column(String(100), default="", comment="目标岗位关键词")
    industry = Column(String(50), default="", comment="目标行业")
    cities = Column(JSON, comment="目标城市列表")
    salary_min = Column(Integer, comment="最低薪资(K/月)")
    salary_max = Column(Integer, comment="最高薪资(K/月)")
    skills = Column(JSON, comment="核心技能列表")
    priority = Column(String(10), default="medium", comment="优先级: high/medium/low")
    status = Column(String(15), default="active", index=True, comment="状态: active/paused/achieved/archived")
    is_primary = Column(Integer, default=0, index=True, comment="是否主目标: 0-否 1-是")
    notes = Column(Text, default="", comment="备注")
    config = Column(JSON, comment="扩展配置：订阅偏好、推荐参数等")

    # 关联统计（冗余，定期更新）
    application_count = Column(Integer, default=0, comment="关联投递数")
    interview_count = Column(Integer, default=0, comment="面试次数")
    offer_count = Column(Integer, default=0, comment="Offer次数")

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "position": self.position or "",
            "industry": self.industry or "",
            "cities": self.cities or [],
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "skills": self.skills or [],
            "priority": self.priority,
            "status": self.status,
            "is_primary": self.is_primary,
            "notes": self.notes or "",
            "config": self.config or {},
            "application_count": self.application_count,
            "interview_count": self.interview_count,
            "offer_count": self.offer_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
