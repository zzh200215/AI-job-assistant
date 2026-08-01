"""订阅与权益 ORM 模型。"""

import enum

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Index, Integer, Numeric, String

from app.core.database import Base
from app.models.base import TenantScopedMixin
from app.utils.time_helper import utc_now


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class SubscriptionPlan(Base):
    """套餐定义表（tenant_id=NULL=平台默认；租户自定义行覆盖对应 tier 的默认套餐）"""

    __tablename__ = "subscription_plan"
    __table_args__ = (
        Index("uq_subscription_plan_tenant_tier", "tenant_id", "tier", unique=True),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tier = Column(String(20), nullable=False, comment="套餐标识: free/pro/enterprise")
    tenant_id = Column(
        BigInteger,
        nullable=True,
        index=True,
        comment="归属租户 organization.id；NULL=平台默认套餐（T3-1）",
    )
    is_custom = Column(Integer, default=0, comment="是否租户自定义套餐（T3-1）")
    name = Column(String(50), nullable=False, comment="展示名称")
    price_monthly = Column(Numeric(10, 2), default=0, comment="月付价格(分)")
    price_yearly = Column(Numeric(10, 2), default=0, comment="年付价格(分)")
    features = Column(JSON, default=dict, comment="权益配置 JSON，见 subscription_service.py")
    sort_order = Column(Integer, default=0, comment="排序")
    is_active = Column(Integer, default=1, comment="是否启用")
    created_at = Column(DateTime, default=utc_now)


class UserSubscription(TenantScopedMixin, Base):
    """用户订阅状态表"""

    __tablename__ = "user_subscription"
    __table_args__ = (Index("ix_user_subscription_tenant_user", "tenant_id", "user_id"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id"), nullable=False, index=True)
    plan_tier = Column(String(20), nullable=False, default="free", comment="当前套餐")
    status = Column(String(20), nullable=False, default="active", comment="active/expired/cancelled")
    start_at = Column(DateTime, nullable=False, default=utc_now, comment="生效时间")
    end_at = Column(DateTime, nullable=True, comment="到期时间")
    auto_renew = Column(Integer, default=0, comment="自动续费")
    # 额度快照：按天的已用量
    quota_usage = Column(JSON, default=dict, comment='{"daily_analysis": 3, "daily_interview": 1}')
    quota_reset_at = Column(DateTime, nullable=True, comment="上次额度重置时间")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class SubscriptionOrder(TenantScopedMixin, Base):
    """订阅订单表"""

    __tablename__ = "subscription_order"
    __table_args__ = (Index("ix_subscription_order_tenant_user", "tenant_id", "user_id"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("tb_user.id"), nullable=False, index=True)
    plan_tier = Column(String(20), nullable=False, comment="购买的套餐")
    amount = Column(Numeric(10, 2), default=0, comment="金额(分)")
    currency = Column(String(10), default="cny")
    status = Column(String(20), nullable=False, default="pending", comment="pending/paid/failed/refunded/cancelled")
    payment_method = Column(String(50), default="", comment="支付方式")
    payment_channel = Column(String(50), default="", comment="支付渠道")
    transaction_id = Column(String(200), default="", comment="第三方交易号")
    period_start = Column(DateTime, nullable=True, comment="订阅开始")
    period_end = Column(DateTime, nullable=True, comment="订阅结束")
    idempotency_key = Column(String(100), unique=True, nullable=True, comment="幂等键")
    created_at = Column(DateTime, default=utc_now)
    paid_at = Column(DateTime, nullable=True)
