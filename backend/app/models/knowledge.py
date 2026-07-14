"""知识库 ORM 模型"""

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class KnowledgeDocument(Base):
    """知识库文档表"""

    __tablename__ = "kb_document"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, default=None, index=True, comment="所属用户ID")
    organization_id = Column(BigInteger, default=None, index=True, comment="所属组织ID；为空表示个人或平台知识")
    title = Column(String(255), nullable=False, comment="文档标题")
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    file_type = Column(String(20), nullable=False, comment="文件类型")
    file_size = Column(BigInteger, comment="文件大小(字节)")
    file_path = Column(String(500), nullable=False, comment="文件存储相对路径")
    doc_type = Column(
        String(50),
        nullable=False,
        default="general",
        comment="文档分类: resume_template/jd_lib/interview_q/skill_model/industry_report/general",
    )
    chunk_count = Column(Integer, default=0, comment="切片数量")
    status = Column(String(20), nullable=False, default="processing", comment="状态: processing/ready/failed")
    error_msg = Column(Text, comment="处理失败原因")
    create_time = Column(DateTime, default=utc_now, comment="创建时间")
    update_time = Column(DateTime, default=utc_now, onupdate=utc_now, comment="更新时间")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "title": self.title,
            "file_name": self.file_name,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "file_path": self.file_path,
            "doc_type": self.doc_type,
            "chunk_count": self.chunk_count or 0,
            "status": self.status,
            "error_msg": self.error_msg,
            "create_time": self.create_time.isoformat() if self.create_time else None,
            "update_time": self.update_time.isoformat() if self.update_time else None,
        }
