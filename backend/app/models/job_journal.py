"""求职日记 ORM 模型"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class JobJournal(Base):
    """求职日记/笔记表"""

    __tablename__ = "job_journal"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    pipeline_id = Column(BigInteger, nullable=True, index=True, comment="关联投递记录ID")
    jd_id = Column(BigInteger, nullable=True, index=True, comment="关联JD ID")

    entry_type = Column(
        String(20), nullable=False, index=True, comment="类型: note/interview_log/offer_review/reflection"
    )
    title = Column(String(200), nullable=False, comment="标题")
    content = Column(Text, default="", comment="正文内容")
    tags = Column(JSON, comment="标签列表")
    mood = Column(String(20), default="", comment="心情: great/good/neutral/bad/terrible")
    rating = Column(Integer, default=0, comment="自评分 1-5")

    # 面试相关字段
    interview_role = Column(String(100), default="", comment="面试官角色/姓名")
    interview_round = Column(Integer, default=0, comment="第几轮面试")
    interview_format = Column(String(20), default="", comment="面试形式: onsite/video/phone")

    attachments = Column(JSON, comment="附件列表 [{'name','url','type'}]")
    is_private = Column(Integer, default=1, comment="是否私密: 0-公开 1-私密")

    created_at = Column(DateTime, default=utc_now, index=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "pipeline_id": self.pipeline_id,
            "jd_id": self.jd_id,
            "entry_type": self.entry_type,
            "title": self.title,
            "content": self.content or "",
            "tags": self.tags or [],
            "mood": self.mood or "",
            "rating": self.rating,
            "interview_role": self.interview_role or "",
            "interview_round": self.interview_round,
            "interview_format": self.interview_format or "",
            "attachments": self.attachments or [],
            "is_private": self.is_private,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
