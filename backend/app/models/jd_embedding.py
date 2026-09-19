"""岗位向量持久表（B3）"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.core.database import Base
from app.utils.time_helper import utc_now


class JobEmbedding(Base):
    """一个岗位在 (provider, model) 下的向量。

    派生数据，不是候选人内容，所以不带 tenant_id：可见性始终由 `tb_jd` 上的
    查询决定，这张表只按 jd_id 取。
    """

    __tablename__ = "jd_embedding"
    __table_args__ = (
        UniqueConstraint("jd_id", "provider", "model", name="uq_jd_embedding_jd_provider_model"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    jd_id = Column(BigInteger, ForeignKey("tb_jd.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, comment="embedding provider")
    model = Column(String(64), nullable=False, comment="embedding model")
    text_hash = Column(String(32), nullable=False, comment="向量对应的岗位文本指纹")
    dimension = Column(Integer, nullable=False, default=0)
    vector = Column(Text, nullable=False, comment="JSON 数组")
    create_time = Column(DateTime, default=utc_now)
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "jd_id": self.jd_id,
            "provider": self.provider,
            "model": self.model,
            "text_hash": self.text_hash,
            "dimension": self.dimension,
        }
