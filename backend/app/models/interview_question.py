"""面试题库 ORM 模型"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class InterviewQuestion(Base):
    """面试题库表"""

    __tablename__ = "interview_question"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    category = Column(String(30), nullable=False, index=True, comment="分类: basic/tech/project/scenario/behavioral")
    sub_category = Column(String(50), default="", index=True, comment="子分类: 如 Python/系统设计/并发等")
    difficulty = Column(String(10), default="medium", index=True, comment="难度: easy/medium/hard")
    question = Column(Text, nullable=False, comment="题目内容")
    intent = Column(String(500), default="", comment="考察意图")
    ref_answer = Column(Text, default="", comment="参考答案")
    keywords = Column(JSON, comment="关键词列表，用于匹配")
    tags = Column(JSON, comment="标签列表")
    source = Column(String(50), default="system", comment="来源: system/user/ai_generated")
    use_count = Column(Integer, default=0, comment="使用次数")
    avg_score = Column(Integer, default=0, comment="平均得分")
    created_at = Column(DateTime, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "sub_category": self.sub_category or "",
            "difficulty": self.difficulty,
            "question": self.question,
            "intent": self.intent or "",
            "ref_answer": self.ref_answer or "",
            "keywords": self.keywords or [],
            "tags": self.tags or [],
            "source": self.source,
            "use_count": self.use_count,
            "avg_score": self.avg_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
