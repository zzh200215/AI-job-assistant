"""SQLAlchemy ORM 模型：对应 3 张表"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.utils.time_helper import utc_now


class Resume(Base):
    __tablename__ = "tb_resume"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, default=None, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(20))
    file_size = Column(BigInteger)
    raw_text = Column(Text)
    parsed_json = Column(JSON)
    name = Column(String(100), index=True)
    phone = Column(String(50))
    email = Column(String(200))
    years_exp = Column(Integer)
    create_time = Column(DateTime, default=utc_now, index=True)
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now)

    # 软删除
    is_deleted = Column(Integer, default=0, comment="0-正常 1-已删除")
    deleted_at = Column(DateTime, nullable=True, comment="删除时间")

    # 优化版简历
    optimized_content = Column(Text, comment="优化版简历内容(Markdown)")
    optimized_at = Column(DateTime, nullable=True, comment="优化时间")


class JobDescription(Base):
    __tablename__ = "tb_jd"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, default=None, index=True)
    title = Column(String(200), nullable=False, index=True)
    company = Column(String(200), index=True)
    location = Column(String(100))
    salary_range = Column(String(100))
    raw_text = Column(Text, nullable=False)
    parsed_json = Column(JSON)
    source = Column(String(20), default="manual", comment="来源: manual/imported/api/crawled")
    industry = Column(String(100), comment="所属行业")
    is_active = Column(Integer, default=1, comment="是否活跃: 0-下架 1-上架")
    external_url = Column(String(500), comment="外部招聘来源URL")
    external_id = Column(String(100), comment="外部招聘平台岗位ID")
    skill_tags = Column(JSON, comment="技能标签列表")
    education_requirement = Column(String(50), comment="学历要求")
    experience_requirement = Column(String(50), comment="经验要求")
    create_time = Column(DateTime, default=utc_now, index=True)
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now)


class AnalysisRecord(Base):
    __tablename__ = "tb_analysis_record"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, default=None, index=True)
    resume_id = Column(BigInteger, ForeignKey("tb_resume.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="CASCADE"), nullable=False, index=True)
    match_score = Column(Integer)
    match_report = Column(JSON)
    optimize_suggestions = Column(JSON)
    interview_questions = Column(JSON)
    remark = Column(String(500))
    create_time = Column(DateTime, default=utc_now, index=True)

    # 软删除
    is_deleted = Column(Integer, default=0, comment="0-正常 1-已删除")
    deleted_at = Column(DateTime, nullable=True, comment="删除时间")

    resume = relationship("Resume")
    jd = relationship("JobDescription")


class ResumeVersion(Base):
    """简历版本表"""

    __tablename__ = "resume_version"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    resume_id = Column(BigInteger, ForeignKey("tb_resume.id", ondelete="CASCADE"), nullable=False, index=True)
    version_type = Column(String(20), nullable=False, comment="版本类型: original/optimized")
    content = Column(Text, nullable=False, comment="简历内容(Markdown)")
    format = Column(String(10), default="md", comment="格式: md/json/txt")
    label = Column(String(120), nullable=True, comment="用户可见的版本名称")
    target_jd_id = Column(BigInteger, nullable=True, index=True, comment="目标岗位ID")
    parent_version_id = Column(BigInteger, nullable=True, index=True, comment="来源版本ID")
    change_log = Column(JSON, nullable=True, comment="改写建议与变更记录")
    suggestion_decisions = Column(JSON, nullable=True, comment="建议采纳状态")
    ats_snapshot = Column(JSON, nullable=True, comment="最近一次ATS预览结果")
    created_at = Column(DateTime, default=utc_now, comment="创建时间")

    resume = relationship("Resume")

    def to_dict(self):
        return {
            "id": self.id,
            "resume_id": self.resume_id,
            "version_type": self.version_type,
            "content": self.content,
            "format": self.format,
            "label": self.label,
            "target_jd_id": self.target_jd_id,
            "parent_version_id": self.parent_version_id,
            "change_log": self.change_log or [],
            "suggestion_decisions": self.suggestion_decisions or {},
            "ats_snapshot": self.ats_snapshot,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
