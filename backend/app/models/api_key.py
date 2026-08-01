"""External API Key model（T6-1）。

对外能力 API 使用独立鉴权体系（X-API-Key 头），不依赖平台用户 JWT。
只存 sha256 哈希，明文 Key 仅创建时返回一次。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from app.core.database import Base
from app.utils.time_helper import utc_now


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="Key 名称（如：客户A-分析端）")
    key_hash = Column(String(64), nullable=False, unique=True, index=True, comment="明文 Key 的 sha256 哈希")
    tenant_id = Column(BigInteger, nullable=False, default=1, index=True, comment="归属租户 organization.id")
    status = Column(String(20), nullable=False, default="active", comment="active/revoked")
    daily_quota = Column(Integer, nullable=False, default=1000, comment="每日成功调用上限")
    expires_at = Column(DateTime, nullable=True, comment="过期时间，为空永不过期")
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    revoked_at = Column(DateTime, nullable=True)
