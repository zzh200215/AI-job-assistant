# -*- coding: utf-8 -*-
"""求职目标管理 API"""
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.job_pipeline import JobApplicationPipeline, ACTIVE_STAGES
from app.models.job_target import JobTarget
from app.models.user import User
from app.schemas.c_end import TargetCreate, TargetUpdate
from app.utils.response import ERR_PARAM, ok, fail

router = APIRouter()


@router.post("/", summary="创建求职目标")
async def create_target(
    payload: TargetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = payload.name.strip()
    if not name:
        return fail(message="目标名称必填", code=ERR_PARAM)

    # 检查用户目标数量上限
    existing = db.query(JobTarget).filter(
        JobTarget.user_id == current_user.id,
        JobTarget.status == "active",
    ).count()
    if existing >= 5:
        return fail(message="最多同时维护5个活跃求职目标", code=ERR_PARAM)

    is_primary = payload.is_primary
    # 如果设为主目标，取消其他主目标
    if is_primary:
        db.query(JobTarget).filter(
            JobTarget.user_id == current_user.id,
            JobTarget.is_primary == 1,
        ).update({"is_primary": 0})

    # 如果是第一个目标，自动设为主目标
    if existing == 0:
        is_primary = 1

    target = JobTarget(
        user_id=current_user.id,
        name=name,
        position=payload.position,
        industry=payload.industry,
        cities=payload.cities,
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        skills=payload.skills,
        priority=payload.priority,
        status="active",
        is_primary=is_primary,
        notes=payload.notes,
        config=payload.config,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return ok(target.to_dict(), message="求职目标已创建")


@router.get("/list", summary="获取求职目标列表")
async def list_targets(
    status: str = Query("", description="状态过滤: active/paused/achieved/archived"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(JobTarget).filter(JobTarget.user_id == current_user.id)
    if status:
        q = q.filter(JobTarget.status == status)

    targets = q.order_by(JobTarget.is_primary.desc(), JobTarget.priority.desc(), JobTarget.created_at.desc()).all()

    result = []
    for t in targets:
        stats = _compute_target_stats(t, db)
        t_dict = t.to_dict()
        t_dict["stats"] = stats
        result.append(t_dict)

    return ok(result)


@router.get("/{target_id}", summary="获取求职目标详情")
async def get_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = db.query(JobTarget).filter(
        JobTarget.id == target_id,
        JobTarget.user_id == current_user.id,
    ).first()
    if not target:
        return fail(message="目标不存在", code=ERR_PARAM)

    stats = _compute_target_stats(target, db)
    t_dict = target.to_dict()
    t_dict["stats"] = stats
    return ok(t_dict)


@router.put("/{target_id}", summary="更新求职目标")
async def update_target(
    target_id: int,
    payload: TargetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = db.query(JobTarget).filter(
        JobTarget.id == target_id,
        JobTarget.user_id == current_user.id,
    ).first()
    if not target:
        return fail(message="目标不存在", code=ERR_PARAM)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "is_primary":
            continue
        setattr(target, field, value)

    # 设为主目标
    if payload.get("is_primary"):
        db.query(JobTarget).filter(
            JobTarget.user_id == current_user.id,
            JobTarget.is_primary == 1,
        ).update({"is_primary": 0})
        target.is_primary = 1

    db.add(target)
    db.commit()
    db.refresh(target)
    return ok(target.to_dict(), message="目标已更新")


@router.delete("/{target_id}", summary="删除求职目标")
async def delete_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = db.query(JobTarget).filter(
        JobTarget.id == target_id,
        JobTarget.user_id == current_user.id,
    ).first()
    if not target:
        return fail(message="目标不存在", code=ERR_PARAM)

    # 解除关联的投递记录
    db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.target_id == target_id,
    ).update({"target_id": None})

    db.delete(target)
    db.commit()
    return ok(message="目标已删除")


@router.post("/{target_id}/set-primary", summary="设为主目标")
async def set_primary(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = db.query(JobTarget).filter(
        JobTarget.id == target_id,
        JobTarget.user_id == current_user.id,
    ).first()
    if not target:
        return fail(message="目标不存在", code=ERR_PARAM)

    db.query(JobTarget).filter(
        JobTarget.user_id == current_user.id,
        JobTarget.is_primary == 1,
    ).update({"is_primary": 0})

    target.is_primary = 1
    db.add(target)
    db.commit()
    return ok(message="已设为主目标")


@router.get("/{target_id}/applications", summary="获取目标下的投递记录")
async def target_applications(
    target_id: int,
    stage: str = Query("", description="阶段过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = db.query(JobTarget).filter(
        JobTarget.id == target_id,
        JobTarget.user_id == current_user.id,
    ).first()
    if not target:
        return fail(message="目标不存在", code=ERR_PARAM)

    q = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.user_id == current_user.id,
        JobApplicationPipeline.target_id == target_id,
    )
    if stage:
        q = q.filter(JobApplicationPipeline.stage == stage)

    total = q.count()
    items = q.order_by(JobApplicationPipeline.create_time.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return ok({
        "total": total,
        "items": [a.to_dict() for a in items],
        "target": target.to_dict(),
    })


@router.get("/{target_id}/progress", summary="目标进度分析")
async def target_progress(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = db.query(JobTarget).filter(
        JobTarget.id == target_id,
        JobTarget.user_id == current_user.id,
    ).first()
    if not target:
        return fail(message="目标不存在", code=ERR_PARAM)

    # 各阶段数量
    stage_rows = db.query(
        JobApplicationPipeline.stage, func.count(JobApplicationPipeline.id)
    ).filter(
        JobApplicationPipeline.target_id == target_id,
    ).group_by(JobApplicationPipeline.stage).all()
    stage_counts = {s: c for s, c in stage_rows}

    total = sum(stage_counts.values())
    active = sum(stage_counts.get(s, 0) for s in ACTIVE_STAGES)
    interviews = stage_counts.get("interview", 0)
    offers = stage_counts.get("offer", 0) + stage_counts.get("accepted", 0)

    # 转化率
    applied = stage_counts.get("applied", 0) + stage_counts.get("written_test", 0) + interviews + offers
    response_rate = round(interviews / applied * 100, 1) if applied > 0 else 0

    # 进度评估
    if offers > 0:
        progress_level = "excellent"
        message = "已获得Offer，目标进展优秀！"
    elif interviews > 0:
        progress_level = "good"
        message = "已获得面试机会，进展良好"
    elif applied > 0:
        progress_level = "in_progress"
        message = f"已投递 {applied} 个岗位，等待回应中"
    elif total > 0:
        progress_level = "starting"
        message = "有待投递的岗位，建议尽快投递"
    else:
        progress_level = "empty"
        message = "还没有关联的投递记录，开始行动吧！"

    return ok({
        "target": target.to_dict(),
        "progress": {
            "level": progress_level,
            "message": message,
            "total_applications": total,
            "active_applications": active,
            "interviews": interviews,
            "offers": offers,
            "response_rate": response_rate,
        },
        "stage_distribution": stage_counts,
        "funnel": {
            "todo": stage_counts.get("todo", 0),
            "applied": applied,
            "interview": interviews,
            "offer": offers,
        },
    })


def _compute_target_stats(target: JobTarget, db: Session) -> dict:
    """纯读取：计算目标的统计数，不写入数据库"""
    base = db.query(JobApplicationPipeline).filter(
        JobApplicationPipeline.target_id == target.id,
    )

    total = base.count()
    interview_count = base.filter(
        JobApplicationPipeline.stage.in_(["interview", "offer", "accepted"]),
    ).count()
    offer_count = base.filter(
        JobApplicationPipeline.stage.in_(["offer", "accepted"]),
    ).count()

    return {
        "total_applications": total,
        "interview_count": interview_count,
        "offer_count": offer_count,
    }


def _refresh_target_stats(target: JobTarget, db: Session) -> dict:
    """刷新目标的冗余统计字段（仅由定时任务调用）"""
    stats = _compute_target_stats(target, db)

    if (target.application_count != stats["total_applications"]
            or target.interview_count != stats["interview_count"]
            or target.offer_count != stats["offer_count"]):
        target.application_count = stats["total_applications"]
        target.interview_count = stats["interview_count"]
        target.offer_count = stats["offer_count"]
        db.add(target)
        db.commit()

    return stats
