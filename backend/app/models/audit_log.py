"""审计日志 ORM 模型。记录敏感操作轨迹。"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, String

from app.core.database import Base
from app.models.base import TenantScopedMixin


class AuditLog(TenantScopedMixin, Base):
    """审计日志表"""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_tenant_user", "tenant_id", "user_id"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, comment="操作用户ID")
    username = Column(String(50), default="", comment="用户名")
    action = Column(
        String(100),
        nullable=False,
        index=True,
        comment="操作类型: subscription.payment / user.delete / data.export / resume.delete 等",
    )
    resource_type = Column(String(50), default="", comment="资源类型: subscription / resume / analysis / interview")
    resource_id = Column(String(50), default="", comment="资源ID")
    detail = Column(JSON, default=dict, comment="操作详情 JSON")
    ip_address = Column(String(50), default="", comment="请求IP")
    user_agent = Column(String(500), default="", comment="User-Agent")
    status = Column(String(20), default="success", comment="操作结果: success / failure / blocked")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
