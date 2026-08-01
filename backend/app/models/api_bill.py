"""External API monthly bill model（T6-2）：聚合 api_usage 生成月账单。"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, Numeric, String

from app.core.database import Base
from app.utils.time_helper import utc_now


class ApiBill(Base):
    __tablename__ = "api_bill"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    api_key_id = Column(BigInteger, nullable=False, index=True)
    tenant_id = Column(BigInteger, nullable=False, default=1, index=True)
    period_start = Column(DateTime, nullable=False, comment="账单周期起（含）")
    period_end = Column(DateTime, nullable=False, comment="账单周期止（含）")
    usage_count = Column(Integer, nullable=False, default=0, comment="周期内成功调用次数")
    total_amount = Column(Numeric(10, 2), nullable=False, default=0, comment="账单总额(分)")
    line_items = Column(JSON, nullable=False, default=dict, comment='{"resume.parse": {"count": n, "amount": x}}')
    status = Column(String(20), nullable=False, default="pending", comment="pending/paid")
    created_at = Column(DateTime, nullable=False, default=utc_now)
