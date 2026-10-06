"""审计日志工具。记录用户敏感操作轨迹。"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


def write_audit_log(
    db: Session,
    user: User,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    detail: dict = None,
    request: Request = None,
    status: str = "success",
) -> AuditLog:
    """
    写入审计日志。

    参数:
        user: 当前用户
        action: 操作类型，命名规则: domain.operation
                如 subscription.payment, user.delete, resume.delete, data.export
        resource_type: 资源类型（subscription / resume / analysis / interview / user）
        resource_id: 资源 ID
        detail: 操作详情（JSON）
        request: FastAPI Request 对象（自动提取 IP 和 UA）
        status: 操作结果（success / failure / blocked）
    """
    log = AuditLog(
        user_id=user.id,
        username=user.username or "",
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else "",
        detail=detail or {},
        ip_address=_get_client_ip(request) if request else "",
        user_agent=str(request.headers.get("user-agent", "")) if request else "",
        status=status,
        created_at=datetime.utcnow(),
    )
    db.add(log)
    db.commit()
    logger.info("AUDIT: user=%s action=%s resource=%s status=%s", user.username, action, resource_type, status)
    return log


def _get_client_ip(request: Request) -> str:
    """从请求中提取客户端 IP，优先取 X-Forwarded-For。"""
    if not request:
        return ""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def list_audit_logs(
    db: Session,
    user_id: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AuditLog]:
    """查询审计日志（管理员用）。"""
    query = db.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    return query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
