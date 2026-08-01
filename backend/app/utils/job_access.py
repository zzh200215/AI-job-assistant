"""Shared job visibility helpers."""

from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.core.tenant_context import current_tenant_id
from app.models.history import JobDescription
from app.models.user import User


def is_admin(user: User) -> bool:
    return user.username in settings.admin_usernames_list


def visible_job_filter(user: User):
    """非管理员岗位可见性：本人 + 平台共享，且归属当前租户或平台共享（T3-3 租户隔离）。"""
    if is_admin(user):
        return None
    return and_(
        or_(JobDescription.user_id == user.id, JobDescription.user_id.is_(None)),
        or_(JobDescription.tenant_id == current_tenant_id(), JobDescription.tenant_id.is_(None)),
    )


def can_access_job(job: JobDescription | None, user: User) -> bool:
    if job is None:
        return False
    if is_admin(user):
        return True
    owner_ok = job.user_id in (None, user.id)
    tenant_ok = job.tenant_id in (None, current_tenant_id())
    return owner_ok and tenant_ok


def accessible_job_query(db: Session, user: User) -> Query:
    query = db.query(JobDescription)
    visibility = visible_job_filter(user)
    if visibility is not None:
        query = query.filter(visibility)
    return query


def get_accessible_job(db: Session, jd_id: int, user: User) -> JobDescription | None:
    return accessible_job_query(db, user).filter(JobDescription.id == jd_id).first()
