"""External API usage log（T6-1）：每次外部调用一条记录，用于限流与计费。"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, Numeric, String

from app.core.database import Base
from app.utils.time_helper import utc_now


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    api_key_id = Column(BigInteger, nullable=False, index=True)
    tenant_id = Column(BigInteger, nullable=False, default=1, index=True)
    endpoint = Column(String(80), nullable=False, comment="resume.parse / match.evaluate / interview.simulate")
    status = Column(String(20), nullable=False, default="success", comment="success/failed")
    amount = Column(Numeric(10, 2), nullable=False, default=0, comment="计费金额(分)，来自 api_pricing")
    request_id = Column(String(64), nullable=False, default="", index=True, comment="调用方幂等/追踪 ID")
    created_at = Column(DateTime, nullable=False, default=utc_now, index=True, comment="调用时间（计费周期按此聚合）")
