"""Service-layer access helpers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.history import AnalysisRecord, JobDescription, Resume
from app.models.user import User
from app.utils.job_access import get_accessible_job


def get_request_user(db: Session, user_id: int | None) -> User | None:
    if user_id is None:
        return None
    return db.get(User, user_id)


def get_owned_resume(
    db: Session,
    resume_id: int,
    user_id: int | None = None,
    *,
    include_deleted: bool = False,
) -> Resume | None:
    query = db.query(Resume).filter(Resume.id == resume_id)
    if user_id is not None:
        query = query.filter(Resume.user_id == user_id)
    if not include_deleted:
        query = query.filter(Resume.is_deleted == 0)
    return query.first()


def get_accessible_job_for_user(
    db: Session,
    jd_id: int,
    user_id: int | None = None,
) -> JobDescription | None:
    if user_id is None:
        return db.get(JobDescription, jd_id)
    user = get_request_user(db, user_id)
    if not user:
        return None
    return get_accessible_job(db, jd_id, user)


def get_owned_analysis_record(
    db: Session,
    record_id: int,
    user_id: int | None = None,
    *,
    include_deleted: bool = True,
) -> AnalysisRecord | None:
    query = db.query(AnalysisRecord).filter(AnalysisRecord.id == record_id)
    if user_id is not None:
        query = query.filter(AnalysisRecord.user_id == user_id)
    if not include_deleted:
        query = query.filter(AnalysisRecord.is_deleted == 0)
    return query.first()
