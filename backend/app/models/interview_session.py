"""面试会话表：InterviewSession"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base
from app.utils.time_helper import utc_now


class InterviewSession(Base):
    """AI 模拟面试会话"""

    __tablename__ = "interview_session"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id = Column(BigInteger, ForeignKey("tb_resume.id", ondelete="SET NULL"), nullable=True, index=True)
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="SET NULL"), nullable=True, index=True)
    interview_type = Column(String(20), default="tech", comment="面试类型: tech/hr/comprehensive")

    # 状态: created → ongoing → completed
    status = Column(String(20), default="created", index=True, comment="created/ongoing/completed")

    # 题目列表（InterviewAgent 的输出，平铺为有序数组）
    questions = Column(JSON, comment="面试题列表 [{'id','type','question','intent','ref_answer','category'},...]")

    # 消息记录（完整对话）
    messages = Column(JSON, default=list, comment="消息数组 [{'role','type','content','metadata','timestamp'},...]")

    # 评估结果
    evaluation = Column(JSON, comment="最终评估报告")
    evaluation_status = Column(String(20), default="idle", comment="idle/processing/completed")
    memory_snapshot = Column(JSON, comment="异步评估聚合出的面试记忆快照")

    # 面试状态统计
    total_questions = Column(Integer, default=0)
    answered_count = Column(Integer, default=0)
    timeout_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "interview_type": self.interview_type,
            "status": self.status,
            "questions": self.questions or [],
            "messages": self.messages or [],
            "evaluation": self.evaluation or {},
            "evaluation_status": self.evaluation_status or "idle",
            "memory_snapshot": self.memory_snapshot or {},
            "total_questions": self.total_questions,
            "answered_count": self.answered_count,
            "timeout_count": self.timeout_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
