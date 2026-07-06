# -*- coding: utf-8 -*-
"""岗位数据源管理 API

路径前缀: /api/datasource
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.user_roles import RECRUITER_ROLE
from app.models.user import User
from app.models.job_data_source import JobDataSource, JobSyncLog
from app.schemas.job_data_source import (
    JobDataSourceCreate,
    JobDataSourceUpdate,
    JobDataSourceOut,
    JobSyncLogOut,
    SyncTriggerIn,
    SyncTestIn,
    SyncTestOut,
    SyncResultOut,
)
from app.services.job_data_source.sync_service import SyncService
from app.utils.http_errors import api_error
from app.utils.response import ERR_AUTH, ERR_PARAM, fail, ok

router = APIRouter()


def _ensure_recruiter_access(user: User):
    if user.role != RECRUITER_ROLE:
        raise api_error(403, "仅招聘者可管理岗位数据源", ERR_AUTH)


# ==================== 数据源 CRUD ====================

@router.get("", summary="数据源列表", response_model=List[JobDataSourceOut])
async def list_data_sources(
    source_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_recruiter_access(current_user)
    q = db.query(JobDataSource).filter(
        JobDataSource.user_id == current_user.id,
    )
    if source_type:
        q = q.filter(JobDataSource.source_type == source_type)
    items = q.order_by(JobDataSource.created_at.desc()).all()
    return items


@router.post("", summary="创建数据源")
async def create_data_source(
    body: JobDataSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_recruiter_access(current_user)
    ds = JobDataSource(
        user_id=current_user.id,
        name=body.name,
        source_type=body.source_type,
        config=body.config.model_dump(),
        sync_interval=body.sync_interval,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ok(data=ds, message="创建成功")


@router.get("/{ds_id}", summary="数据源详情")
async def get_data_source(
    ds_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_recruiter_access(current_user)
    ds = db.query(JobDataSource).filter(
        JobDataSource.id == ds_id,
        JobDataSource.user_id == current_user.id,
    ).first()
    if not ds:
        return fail(message="数据源不存在", code=ERR_PARAM)
    return ok(data=ds)


@router.put("/{ds_id}", summary="更新数据源")
async def update_data_source(
    ds_id: int,
    body: JobDataSourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_recruiter_access(current_user)
    ds = db.query(JobDataSource).filter(
        JobDataSource.id == ds_id,
        JobDataSource.user_id == current_user.id,
    ).first()
    if not ds:
        return fail(message="数据源不存在", code=ERR_PARAM)
    if body.name is not None:
        ds.name = body.name
    if body.config is not None:
        ds.config = body.config.model_dump()
    if body.status is not None:
        ds.status = body.status
    if body.sync_interval is not None:
        ds.sync_interval = body.sync_interval
    db.commit()
    db.refresh(ds)
    return ok(data=ds, message="更新成功")


@router.delete("/{ds_id}", summary="删除数据源")
async def delete_data_source(
    ds_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_recruiter_access(current_user)
    ds = db.query(JobDataSource).filter(
        JobDataSource.id == ds_id,
        JobDataSource.user_id == current_user.id,
    ).first()
    if not ds:
        return fail(message="数据源不存在", code=ERR_PARAM)
    db.delete(ds)
    db.commit()
    return ok(message="删除成功")


# ==================== 测试 & 同步 ====================

@router.post("/{ds_id}/test", summary="测试数据源连接")
async def test_data_source(
    ds_id: int,
    _: SyncTestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_recruiter_access(current_user)
    ds = db.query(JobDataSource).filter(
        JobDataSource.id == ds_id,
        JobDataSource.user_id == current_user.id,
    ).first()
    if not ds:
        return fail(message="数据源不存在", code=ERR_PARAM)

    svc = SyncService(db, user_id=current_user.id)
    connectable, sample, message = svc.test_source(ds)
    return ok(data={
        "connectable": connectable,
        "sample": sample,
        "message": message,
    })


@router.post("/{ds_id}/sync", summary="手动触发同步")
async def trigger_sync(
    ds_id: int,
    body: SyncTriggerIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_recruiter_access(current_user)
    ds = db.query(JobDataSource).filter(
        JobDataSource.id == ds_id,
        JobDataSource.user_id == current_user.id,
    ).first()
    if not ds:
        return fail(message="数据源不存在", code=ERR_PARAM)
    if ds.status != 1:
        return fail(message="数据源已禁用，无法同步", code=ERR_PARAM)

    svc = SyncService(db, user_id=current_user.id)
    log = svc.sync(ds, dry_run=body.dry_run, limit=body.limit)

    return ok(data={
        "log_id": log.id,
        "status": log.status,
        "total_count": log.total_count,
        "success_count": log.success_count,
        "fail_count": log.fail_count,
        "duplicate_count": log.duplicate_count,
        "embed_count": log.embed_count,
        "duration_ms": log.duration_ms,
        "message": log.error_msg or f"同步完成: 成功 {log.success_count} 条",
    })


# ==================== 同步日志 ====================

@router.get("/{ds_id}/logs", summary="同步日志列表")
async def list_sync_logs(
    ds_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_recruiter_access(current_user)
    ds = db.query(JobDataSource).filter(
        JobDataSource.id == ds_id,
        JobDataSource.user_id == current_user.id,
    ).first()
    if not ds:
        return fail(message="数据源不存在", code=ERR_PARAM)

    q = db.query(JobSyncLog).filter(JobSyncLog.source_id == ds_id)
    total = q.count()
    logs = q.order_by(JobSyncLog.started_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok(data={
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": logs,
    })
