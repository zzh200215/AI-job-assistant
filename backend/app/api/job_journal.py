# -*- coding: utf-8 -*-
"""求职日记 API"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import JobDescription
from app.models.job_journal import JobJournal
from app.models.job_pipeline import JobApplicationPipeline
from app.models.user import User
from app.schemas.c_end import JournalCreate, JournalUpdate
from app.utils.response import ERR_PARAM, ok, fail

router = APIRouter()

VALID_ENTRY_TYPES = {"note", "interview_log", "offer_review", "reflection"}
VALID_MOODS = {"great", "good", "neutral", "bad", "terrible"}


@router.post("/", summary="创建日记/笔记")
async def create_journal(
    payload: JournalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    title = payload.title
    if not title:
        return fail(message="标题必填", code=ERR_PARAM)

    pipeline_id = payload.pipeline_id

    # 验证关联记录归属
    if pipeline_id:
        p = db.query(JobApplicationPipeline).filter(
            JobApplicationPipeline.id == pipeline_id,
            JobApplicationPipeline.user_id == current_user.id,
        ).first()
        if not p:
            return fail(message="投递记录不存在或无权限", code=ERR_PARAM)

    journal = JobJournal(
        user_id=current_user.id,
        pipeline_id=pipeline_id,
        jd_id=payload.jd_id,
        entry_type=payload.entry_type,
        title=title,
        content=payload.content,
        tags=payload.tags,
        mood=payload.mood,
        rating=payload.rating,
        interview_role=payload.interview_role,
        interview_round=payload.interview_round,
        interview_format=payload.interview_format,
        attachments=payload.attachments,
        is_private=payload.is_private,
    )
    db.add(journal)
    db.commit()
    db.refresh(journal)
    return ok(journal.to_dict(), message="日记已创建")


@router.get("/list", summary="获取日记列表")
async def list_journals(
    entry_type: str = Query("", description="类型过滤"),
    pipeline_id: int = Query(None, description="投递记录ID过滤"),
    jd_id: int = Query(None, description="JD ID过滤"),
    mood: str = Query("", description="心情过滤"),
    keyword: str = Query("", description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(JobJournal).filter(JobJournal.user_id == current_user.id)
    if entry_type:
        q = q.filter(JobJournal.entry_type == entry_type)
    if pipeline_id:
        q = q.filter(JobJournal.pipeline_id == pipeline_id)
    if jd_id:
        q = q.filter(JobJournal.jd_id == jd_id)
    if mood:
        q = q.filter(JobJournal.mood == mood)
    if keyword:
        q = q.filter(JobJournal.title.contains(keyword) | JobJournal.content.contains(keyword))

    total = q.count()
    items = (
        q.order_by(JobJournal.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 附带 JD 信息
    jd_ids = {item.jd_id for item in items if item.jd_id}
    jds = {
        item.id: {"id": item.id, "title": item.title, "company": item.company}
        for item in db.query(JobDescription).filter(JobDescription.id.in_(jd_ids)).all()
    } if jd_ids else {}

    result_items = []
    for item in items:
        d = item.to_dict()
        d["jd_summary"] = jds.get(item.jd_id) if item.jd_id else None
        result_items.append(d)

    return ok({"total": total, "items": result_items})


@router.get("/{journal_id}", summary="获取日记详情")
async def get_journal(
    journal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    journal = db.query(JobJournal).filter(
        JobJournal.id == journal_id,
        JobJournal.user_id == current_user.id,
    ).first()
    if not journal:
        return fail(message="日记不存在", code=ERR_PARAM)
    return ok(journal.to_dict())


@router.put("/{journal_id}", summary="更新日记")
async def update_journal(
    journal_id: int,
    payload: JournalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    journal = db.query(JobJournal).filter(
        JobJournal.id == journal_id,
        JobJournal.user_id == current_user.id,
    ).first()
    if not journal:
        return fail(message="日记不存在", code=ERR_PARAM)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(journal, field, value)

    db.add(journal)
    db.commit()
    db.refresh(journal)
    return ok(journal.to_dict(), message="日记已更新")


@router.delete("/{journal_id}", summary="删除日记")
async def delete_journal(
    journal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    journal = db.query(JobJournal).filter(
        JobJournal.id == journal_id,
        JobJournal.user_id == current_user.id,
    ).first()
    if not journal:
        return fail(message="日记不存在", code=ERR_PARAM)
    db.delete(journal)
    db.commit()
    return ok(message="日记已删除")


@router.get("/stats/summary", summary="日记统计")
async def journal_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """统计日记数据：按类型、心情分布等"""
    base = db.query(JobJournal).filter(JobJournal.user_id == current_user.id)

    # 按类型统计
    type_rows = db.query(
        JobJournal.entry_type, func.count(JobJournal.id)
    ).filter(JobJournal.user_id == current_user.id).group_by(JobJournal.entry_type).all()
    by_type = {t: c for t, c in type_rows}

    # 按心情统计
    mood_rows = db.query(
        JobJournal.mood, func.count(JobJournal.id)
    ).filter(
        JobJournal.user_id == current_user.id,
        JobJournal.mood != "",
    ).group_by(JobJournal.mood).all()
    by_mood = {m: c for m, c in mood_rows}

    # 平均自评分
    avg_rating = db.query(
        func.avg(JobJournal.rating)
    ).filter(
        JobJournal.user_id == current_user.id,
        JobJournal.rating > 0,
    ).scalar()

    total = base.count()

    return ok({
        "total": total,
        "by_type": by_type,
        "by_mood": by_mood,
        "avg_rating": round(float(avg_rating), 1) if avg_rating else None,
    })
