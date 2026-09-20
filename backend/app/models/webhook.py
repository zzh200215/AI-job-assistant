"""External webhook subscription model（T6-3）。

事件回调：resume.parsed / match.evaluated / interview.completed。
投递签名：HMAC-SHA256(secret, payload)，头 `X-Webhook-Signature`。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, String

from app.core.database import Base
from app.utils.time_helper import utc_now


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    api_key_id = Column(BigInteger, nullable=False, index=True)
    tenant_id = Column(BigInteger, nullable=False, default=1, index=True)
    event = Column(
        String(80), nullable=False, comment="事件类型: resume.parsed / match.evaluated / interview.completed"
    )
    url = Column(String(500), nullable=False, comment="回调 URL")
    secret = Column(String(64), nullable=False, default="", comment="签名密钥")
    status = Column(String(20), nullable=False, default="active", comment="active/disabled")
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
