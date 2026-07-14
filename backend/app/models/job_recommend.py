"""岗位推荐相关 ORM 模型"""

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, String

from app.core.database import Base
from app.utils.time_helper import utc_now


class JobRecommendationFeedback(Base):
    """用户推荐反馈表"""

    __tablename__ = "job_recommend_feedback"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = Column(BigInteger, ForeignKey("tb_resume.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="CASCADE"), nullable=False, index=True)
    feedback_type = Column(String(10), nullable=False, comment="反馈类型: like/dislike")
    match_score = Column(Float, comment="推荐时的匹配分数")
    created_at = Column(DateTime, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "feedback_type": self.feedback_type,
            "match_score": self.match_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class JobBookmark(Base):
    """职位收藏/不感兴趣表"""

    __tablename__ = "job_bookmark"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(20), nullable=False, index=True, comment="操作类型: bookmark/dismiss")
    note = Column(String(500), default="", comment="收藏备注")
    created_at = Column(DateTime, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "jd_id": self.jd_id,
            "action": self.action,
            "note": self.note or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
