# -*- coding: utf-8 -*-
"""投递流程 API"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import JobDescription, Resume
from app.models.job_pipeline import JobApplicationPipeline
from app.models.user import User
from app.schemas.job_pipeline import PipelineCreateReq, PipelineUpdateReq
from app.utils.job_access import get_accessible_job
from app.utils.response import ERR_PARAM, ok, fail
from app.utils.time_helper import utc_now_iso

router = APIRouter()

PIPELINE_STAGES = {"todo", "applied", "interview", "rejected"}


@router.get("/pipeline/list", summary="获取投递流程列表")
async def list_pipeline_entries(
    stage: str = Query("", description="流程阶段过滤"),
    keyword: str = Query("", description="岗位/公司/备注关键词"),
    resume_id: Optional[int] = Query(None, description="简历 ID 过滤"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if stage and stage not in PIPELINE_STAGES:
        return fail(message="非法的流程阶段", code=ERR_PARAM)

    q = db.query(JobApplicationPipeline).filter(JobApplicationPipeline.user_id == current_user.id)
    if stage:
        q = q.filter(JobApplicationPipeline.stage == stage)
    if resume_id is not None:
        q = q.filter(JobApplicationPipeline.resume_id == resume_id)

    items = q.all()
    keyword = keyword.strip().lower()
    if keyword:
        items = [
            item for item in items
            if keyword in " ".join([
                item.title or "",
                item.company or "",
                item.location or "",
                item.note or "",
                item.next_action or "",
                item.resume_name or "",
            ]).lower()
        ]

    items.sort(key=_sort_key)
    return ok({
        "total": len(items),
        "items": [item.to_dict() for item in items],
    })


@router.post("/pipeline", summary="创建投递流程记录")
async def create_pipeline_entry(
    payload: PipelineCreateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = None
    jd = None

    if payload.resume_id is not None:
        resume = db.query(Resume).filter(
            Resume.id == payload.resume_id,
            Resume.user_id == current_user.id,
            Resume.is_deleted == 0,
        ).first()
        if not resume:
            return fail(message="简历不存在或无权限", code=ERR_PARAM)

    if payload.jd_id is not None:
        jd = get_accessible_job(db, payload.jd_id, current_user)
        if not jd:
            return fail(message="岗位不存在或无权限", code=ERR_PARAM)

    duplicate = None
    if payload.jd_id is not None:
        duplicate = db.query(JobApplicationPipeline).filter(
            JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.jd_id == payload.jd_id,
            JobApplicationPipeline.resume_id == payload.resume_id,
        ).first()
    elif payload.source_url and payload.title:
        duplicate = db.query(JobApplicationPipeline).filter(
            JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.source_url == payload.source_url,
            JobApplicationPipeline.title == payload.title,
            JobApplicationPipeline.company == payload.company,
        ).first()

    if duplicate:
        return ok(duplicate.to_dict(), message="该岗位已在投递流程中")

    try:
        follow_up_at = _parse_datetime(payload.follow_up_at)
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)

    history = [item.model_dump() for item in payload.stage_history]
    if not history:
        history = [{"stage": payload.stage, "at": utc_now_iso()}]

    entry = JobApplicationPipeline(
        user_id=current_user.id,
        resume_id=resume.id if resume else payload.resume_id,
        jd_id=jd.id if jd else payload.jd_id,
        title=payload.title or (jd.title if jd else ""),
        company=payload.company or (jd.company if jd else ""),
        location=payload.location or (jd.location if jd else ""),
        salary_range=payload.salary_range or (jd.salary_range if jd else ""),
        source=payload.source or (jd.source if jd else "manual"),
        source_url=payload.source_url or (jd.external_url if jd else ""),
        summary=payload.summary,
        raw_text=payload.raw_text or (jd.raw_text if jd else ""),
        experience_requirement=payload.experience_requirement or (jd.experience_requirement if jd else ""),
        education_requirement=payload.education_requirement or (jd.education_requirement if jd else ""),
        industry=payload.industry or (jd.industry if jd else ""),
        skill_tags=_unique_skill_tags(payload.skill_tags or (jd.skill_tags if jd else [])),
        priority_score=payload.priority_score,
        priority_label=payload.priority_label,
        stage=payload.stage,
        note=payload.note,
        next_action=payload.next_action,
        follow_up_at=follow_up_at,
        resume_name=payload.resume_name or (resume.file_name if resume else ""),
        stage_history=history,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return ok(entry.to_dict(), message="已加入投递流程")


@router.put("/pipeline/{entry_id}", summary="更新投递流程记录")
async def update_pipeline_entry(
    entry_id: int,
    payload: PipelineUpdateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.id == entry_id,
        JobApplicationPipeline.user_id == current_user.id,
    ).first()
    if not entry:
        return fail(message="投递记录不存在或无权限", code=ERR_PARAM)

    data = payload.model_dump(exclude_unset=True)

    if "resume_id" in data and data["resume_id"] is not None:
        resume = db.query(Resume).filter(
            Resume.id == data["resume_id"],
            Resume.user_id == current_user.id,
            Resume.is_deleted == 0,
        ).first()
        if not resume:
            return fail(message="简历不存在或无权限", code=ERR_PARAM)
        entry.resume_id = resume.id
        if "resume_name" not in data:
            entry.resume_name = resume.file_name or resume.name or ""

    if "jd_id" in data and data["jd_id"] is not None:
        jd = get_accessible_job(db, data["jd_id"], current_user)
        if not jd:
            return fail(message="岗位不存在或无权限", code=ERR_PARAM)
        entry.jd_id = jd.id

    for field in (
        "title",
        "company",
        "location",
        "salary_range",
        "source",
        "source_url",
        "summary",
        "raw_text",
        "experience_requirement",
        "education_requirement",
        "industry",
        "priority_score",
        "priority_label",
        "stage",
        "note",
        "next_action",
        "resume_name",
    ):
        if field in data:
            setattr(entry, field, data[field])

    if "skill_tags" in data and data["skill_tags"] is not None:
        entry.skill_tags = _unique_skill_tags(data["skill_tags"])

    if "follow_up_at" in data:
        try:
            entry.follow_up_at = _parse_datetime(data["follow_up_at"])
        except ValueError as exc:
            return fail(message=str(exc), code=ERR_PARAM)

    if "stage_history" in data and data["stage_history"] is not None:
        entry.stage_history = [item.model_dump() if hasattr(item, "model_dump") else item for item in data["stage_history"]]

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return ok(entry.to_dict(), message="投递记录已更新")


@router.delete("/pipeline/rejected", summary="清理已淘汰投递记录")
async def clear_rejected_pipeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == current_user.id,
        JobApplicationPipeline.stage == "rejected",
    ).all()
    count = len(items)
    for item in items:
        db.delete(item)
    db.commit()
    return ok({"deleted": count}, message=f"已清理 {count} 条淘汰记录")


@router.delete("/pipeline/{entry_id}", summary="删除投递流程记录")
async def delete_pipeline_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.id == entry_id,
        JobApplicationPipeline.user_id == current_user.id,
    ).first()
    if not entry:
        return fail(message="投递记录不存在或无权限", code=ERR_PARAM)

    db.delete(entry)
    db.commit()
    return ok(message="投递记录已删除")


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(normalized, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("follow_up_at 时间格式非法") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _sort_key(item: JobApplicationPipeline):
    follow_up = item.follow_up_at or datetime.max
    updated = item.update_time or datetime.min
    return (follow_up, -updated.timestamp())


def _unique_skill_tags(items):
    return list(dict.fromkeys([str(item).strip() for item in (items or []) if str(item).strip()]))
