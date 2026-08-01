"""External API pricing model（T6-2）：端点 × 单价（分/次）。

与 docs/定价表.md §7 API 定价框架对应，初始值在迁移中写入：
  resume.parse        30 分（¥0.30）
  match.evaluate      30 分（¥0.30）
  interview.simulate  80 分（¥0.80）
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, Numeric, String

from app.core.database import Base
from app.utils.time_helper import utc_now


class ApiPricing(Base):
    __tablename__ = "api_pricing"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    endpoint = Column(String(80), nullable=False, unique=True, index=True)
    unit_price = Column(Numeric(10, 2), nullable=False, default=0, comment="单价(分/次)")
    is_active = Column(Integer, nullable=False, default=1, comment="是否启用")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
