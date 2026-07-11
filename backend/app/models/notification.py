# -*- coding: utf-8 -*-
"""站内消息 ORM 模型"""
from sqlalchemy import Column, BigInteger, String, DateTime, Text, Integer, JSON

from app.core.database import Base
from app.utils.time_helper import utc_now


class Notification(Base):
    """站内消息表"""
    __tablename__ = "notification"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, comment="接收用户 ID")
    type = Column(String(30), nullable=False, index=True, comment="消息类型: interview_reminder/offer_reminder/system/recommendation/application_update")
    title = Column(String(200), nullable=False, comment="消息标题")
    content = Column(Text, default="", comment="消息正文")
    link = Column(String(500), default="", comment="跳转链接")
    ext_data = Column(JSON, comment="附加数据（如面试时间、JD信息等）")
    is_read = Column(Integer, default=0, index=True, comment="是否已读: 0-未读 1-已读")
    read_at = Column(DateTime, nullable=True, comment="阅读时间")
    created_at = Column(DateTime, default=utc_now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "content": self.content or "",
            "link": self.link or "",
            "metadata": self.ext_data or {},
            "is_read": self.is_read,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
