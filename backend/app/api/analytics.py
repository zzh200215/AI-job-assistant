"""数据分析 API：转化漏斗、留存、关键指标。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.database import get_db
from app.models.user import User
from app.services.analytics_service import (
    get_conversion_funnel,
    get_retention,
    get_summary_metrics,
)
from app.utils.response import ok

router = APIRouter()


@router.get("/analytics/summary", summary="关键业务指标汇总")
def summary(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """返回用户数、简历数、分析数、面试数、Pro用户数、付费订单数。"""
    return ok(get_summary_metrics(db))


@router.get("/analytics/funnel", summary="转化漏斗")
def funnel(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """返回注册→上传→分析→面试→订阅的转化漏斗。"""
    return ok(get_conversion_funnel(db, days=days))


@router.get("/analytics/retention", summary="用户留存")
def retention(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """返回每日活跃和7/14/30日留存率。"""
    return ok(get_retention(db, days=days))
