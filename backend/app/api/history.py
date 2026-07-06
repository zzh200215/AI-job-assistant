# -*- coding: utf-8 -*-
"""历史记录路由：列表 + 详情 + 删除"""
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.history import AnalysisRecord, Resume, JobDescription
from app.models.user import User
from app.api.auth import get_current_user
from app.utils.job_access import accessible_job_query, get_accessible_job
from app.utils.time_helper import utc_now
from app.utils.response import ERR_PARAM, fail, ok


def _deep_parse_json(obj):
    """递归解析对象中所有 JSON 字符串（兼容 LLM 双重序列化或 DB 驱动差异）"""
    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            return _deep_parse_json(parsed)
        except Exception:
            return obj
    if isinstance(obj, dict):
        return {k: _deep_parse_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_parse_json(i) for i in obj]
    return obj


router = APIRouter()


def _owned_resume_map(db: Session, user: User, resume_ids: list[int]) -> dict[int, Resume]:
    if not resume_ids:
        return {}
    return {
        resume.id: resume
        for resume in db.query(Resume)
        .filter(Resume.user_id == user.id, Resume.id.in_(resume_ids))
        .all()
    }


def _visible_job_map(db: Session, user: User, jd_ids: list[int]) -> dict[int, JobDescription]:
    if not jd_ids:
        return {}
    return {
        job.id: job
        for job in accessible_job_query(db, user)
        .filter(JobDescription.id.in_(jd_ids))
        .all()
    }


@router.get("", summary="历史记录列表（按时间倒序）")
async def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(AnalysisRecord).filter(
        AnalysisRecord.user_id == current_user.id,
        AnalysisRecord.is_deleted == 0,
    ).order_by(AnalysisRecord.create_time.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    # 关联查一下简历 / JD 的标题，避免前端多次请求
    rid_to_resume = _owned_resume_map(db, current_user, [item.resume_id for item in items if item.resume_id])
    jid_to_jd = _visible_job_map(db, current_user, [item.jd_id for item in items if item.jd_id])

    data = []
    for it in items:
        r = rid_to_resume.get(it.resume_id)
        j = jid_to_jd.get(it.jd_id)
        data.append({
            "id": it.id,
            "resume_id": it.resume_id,
            "jd_id": it.jd_id,
            "resume_name": r.name if r else None,
            "resume_file": r.file_name if r else None,
            "jd_title": j.title if j else None,
            "jd_company": j.company if j else None,
            "match_score": it.match_score,
            "remark": it.remark,
            "create_time": it.create_time.isoformat() if it.create_time else None,
        })
    return ok({"total": total, "page": page, "page_size": page_size, "items": data})


@router.get("/{record_id}", summary="历史记录详情")
async def get_history(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rec: AnalysisRecord = db.query(AnalysisRecord).filter(
        AnalysisRecord.id == record_id,
        AnalysisRecord.user_id == current_user.id,
        AnalysisRecord.is_deleted == 0,
    ).first()
    if not rec:
        return fail(message="记录不存在或无权限", code=ERR_PARAM)
    r = _owned_resume_map(db, current_user, [rec.resume_id]).get(rec.resume_id)
    j = get_accessible_job(db, rec.jd_id, current_user) if rec.jd_id else None
    return ok({
        "id": rec.id,
        "resume_id": rec.resume_id,
        "jd_id": rec.jd_id,
        "resume": {
            "id": r.id, "name": r.name, "file_name": r.file_name,
            "parsed": r.parsed_json or {}
        } if r else None,
        "jd": {
            "id": j.id, "title": j.title, "company": j.company,
            "parsed": j.parsed_json or {}
        } if j else None,
        "match_score": rec.match_score,
        "match_report": _deep_parse_json(rec.match_report),
        "optimize_suggestions": _deep_parse_json(rec.optimize_suggestions),
        "interview_questions": _deep_parse_json(rec.interview_questions),
        "remark": rec.remark,
        "create_time": rec.create_time.isoformat() if rec.create_time else None,
    })


@router.delete("/{record_id}", summary="软删除一条历史记录")
async def delete_history(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rec = db.query(AnalysisRecord).filter(
        AnalysisRecord.id == record_id,
        AnalysisRecord.user_id == current_user.id,
        AnalysisRecord.is_deleted == 0,
    ).first()
    if not rec:
        return fail(message="记录不存在或无权限", code=ERR_PARAM)
    rec.is_deleted = 1
    rec.deleted_at = utc_now()
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return ok({"id": record_id, "deleted": True})
