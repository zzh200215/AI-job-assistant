"""数据分析 API：转化漏斗、留存、关键指标、收入汇总（T4-2）。

2026-10-06 真删企业侧第六增量（D136）之前，这四条 GET 都带一个可选的 `?tenant_id=`
（管理员指定租户时先查 `organization` 存不存在、不存在 404），`/admin/analytics/revenue`
还按租户分组。参数与那趟校验随 organization 一起出树，服务层只剩平台一条口径。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.database import get_db
from app.models.user import User
from app.services.analytics_service import (
    get_conversion_funnel,
    get_retention,
    get_revenue_summary,
    get_summary_metrics,
)
from app.utils.response import ok

router = APIRouter()
admin_router = APIRouter()


@router.get("/summary", summary="关键业务指标汇总")
def summary(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """返回用户数、简历数、分析数、面试数、Pro用户数、付费订单数。"""
    return ok(get_summary_metrics(db))


@router.get("/funnel", summary="转化漏斗")
def funnel(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """返回注册→上传→分析→面试→订阅的转化漏斗。"""
    return ok(get_conversion_funnel(db, days=days))


@router.get("/retention", summary="用户留存")
def retention(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """返回每日活跃和7/14/30日留存率。"""
    return ok(get_retention(db, days=days))


@admin_router.get("/analytics/revenue", summary="管理员：收入汇总")
def revenue(
    days: int = Query(30, ge=1, le=3650, description="统计近 N 天；缺省 30 天"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """收入汇总（订阅与单次支付，status=paid）+ 按套餐的一维分解。"""
    return ok(get_revenue_summary(db, days=days))
