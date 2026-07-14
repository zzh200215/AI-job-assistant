"""Shared job visibility helpers."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.models.history import JobDescription
from app.models.user import User


def is_admin(user: User) -> bool:
    return user.username in settings.admin_usernames_list


def visible_job_filter(user: User):
    if is_admin(user):
        return None
    return or_(JobDescription.user_id == user.id, JobDescription.user_id.is_(None))


def can_access_job(job: JobDescription | None, user: User) -> bool:
    if job is None:
        return False
    return is_admin(user) or job.user_id in (None, user.id)


def accessible_job_query(db: Session, user: User) -> Query:
    query = db.query(JobDescription)
    visibility = visible_job_filter(user)
    if visibility is not None:
        query = query.filter(visibility)
    return query


def get_accessible_job(db: Session, jd_id: int, user: User) -> JobDescription | None:
    return accessible_job_query(db, user).filter(JobDescription.id == jd_id).first()
