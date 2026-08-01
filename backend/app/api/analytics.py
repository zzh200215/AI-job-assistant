"""数据分析 API：转化漏斗、留存、关键指标、租户收入汇总（T4-2）。

- `/analytics/*`：`?tenant_id=` 可选（管理员，默认平台级；给定时校验租户存在）；
- `/admin/analytics/revenue`：按租户汇总订单金额（独立 admin router，路由落在 /api/admin/analytics/revenue）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.services.analytics_service import (
    get_conversion_funnel,
    get_retention,
    get_revenue_summary,
    get_summary_metrics,
)
from app.utils.http_errors import api_error
from app.utils.response import ERR_PARAM, ok

router = APIRouter()
admin_router = APIRouter()


def _resolve_tenant_or_404(db: Session, tenant_id: int | None) -> None:
    """管理员指定租户时必须存在，否则 404。"""
    if tenant_id is None:
        return
    if db.get(Organization, tenant_id) is None:
        raise api_error(404, "租户不存在", ERR_PARAM)


@router.get("/summary", summary="关键业务指标汇总（可指定租户）")
def summary(
    tenant_id: int | None = Query(None, ge=1, description="租户 organization.id；缺省=平台级"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """返回用户数、简历数、分析数、面试数、Pro用户数、付费订单数。"""
    _resolve_tenant_or_404(db, tenant_id)
    return ok(get_summary_metrics(db, tenant_id=tenant_id))


@router.get("/funnel", summary="转化漏斗（可指定租户）")
def funnel(
    days: int = Query(30, ge=1, le=365),
    tenant_id: int | None = Query(None, ge=1, description="租户 organization.id；缺省=平台级"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """返回注册→上传→分析→面试→订阅的转化漏斗。"""
    _resolve_tenant_or_404(db, tenant_id)
    return ok(get_conversion_funnel(db, days=days, tenant_id=tenant_id))


@router.get("/retention", summary="用户留存（可指定租户）")
def retention(
    days: int = Query(30, ge=1, le=365),
    tenant_id: int | None = Query(None, ge=1, description="租户 organization.id；缺省=平台级"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """返回每日活跃和7/14/30日留存率。"""
    _resolve_tenant_or_404(db, tenant_id)
    return ok(get_retention(db, days=days, tenant_id=tenant_id))


@admin_router.get("/analytics/revenue", summary="管理员：按租户汇总收入")
def revenue(
    days: int = Query(30, ge=1, le=3650, description="统计近 N 天；缺省 30 天"),
    tenant_id: int | None = Query(None, ge=1, description="租户 organization.id；缺省=按租户分组汇总"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """按租户汇总订单金额（订阅与单次支付，status=paid）。

    - 不给 tenant_id：返回各租户收入 items + 平台总额；
    - 给 tenant_id：返回该租户总收入 + 分套餐明细。
    """
    _resolve_tenant_or_404(db, tenant_id)
    return ok(get_revenue_summary(db, tenant_id=tenant_id, days=days))
