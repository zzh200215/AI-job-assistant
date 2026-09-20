"""外部 API 计费与账单（T6-2）：Key 管理 / 月度结算 / 账单查询与 CSV 导出。

管理端接口（require_admin），供平台运营配置 Key 与出账。
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.database import get_db
from app.models.api_bill import ApiBill
from app.models.api_key import ApiKey
from app.models.user import User
from app.services.api_key_service import create_api_key, run_monthly_billing
from app.utils.time_helper import utc_now_naive

router = APIRouter(prefix="/admin/external", tags=["external-billing"])


# ===== Key 管理 =====


@router.post("/api-keys", summary="管理：创建 API Key（明文仅此一次返回）")
def admin_create_api_key(
    payload: dict,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 必填")
    tenant_id = int(payload.get("tenant_id") or 1)
    daily_quota = int(payload.get("daily_quota") or 1000)
    expires_at = None
    if payload.get("expires_at"):
        try:
            # DB DATETIME 读回 naive，统一存 naive（截断 tzinfo 避免比较 TypeError）
            expires_at = datetime.fromisoformat(
                str(payload["expires_at"]).replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="expires_at 格式错误，示例 2027-01-01T00:00:00") from exc
    key, plain = create_api_key(
        db,
        name=name,
        tenant_id=tenant_id,
        daily_quota=daily_quota,
        expires_at=expires_at,
    )
    return {
        "id": key.id,
        "name": key.name,
        "api_key": plain,  # 仅创建时返回一次，请立即保存
        "tenant_id": key.tenant_id,
        "daily_quota": key.daily_quota,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
    }


@router.get("/api-keys", summary="管理：Key 列表（含用量）")
def admin_list_api_keys(
    tenant_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = db.query(ApiKey)
    if tenant_id:
        query = query.filter(ApiKey.tenant_id == tenant_id)
    total = query.count()
    keys = query.order_by(ApiKey.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for key in keys:
        items.append(
            {
                "id": key.id,
                "name": key.name,
                "tenant_id": key.tenant_id,
                "status": key.status,
                "daily_quota": key.daily_quota,
                "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
                "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                "created_at": key.created_at.isoformat() if key.created_at else None,
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/api-keys/{key_id}/revoke", summary="管理：吊销 API Key")
def admin_revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=404, detail="API Key 不存在")
    key.status = "revoked"
    key.revoked_at = utc_now_naive()
    db.add(key)
    db.commit()
    return {"id": key.id, "status": key.status}


# ===== 月度结算与账单 =====


@router.post("/billing/run", summary="管理：手动触发月度结算（可空月份跳过）")
def admin_run_billing(
    payload: dict,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    try:
        year = int(payload.get("year") or 0)
        month = int(payload.get("month") or 0)
        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="year/month 必填且合法") from exc
    bill_ids = run_monthly_billing(db, year, month)
    return {"period": f"{year:04d}-{month:02d}", "bills_generated": len(bill_ids), "bill_ids": bill_ids}


@router.get("/billing/bills", summary="管理：账单列表")
def admin_list_bills(
    tenant_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    query = db.query(ApiBill)
    if tenant_id:
        query = query.filter(ApiBill.tenant_id == tenant_id)
    total = query.count()
    bills = query.order_by(ApiBill.period_start.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for bill in bills:
        items.append(
            {
                "id": bill.id,
                "api_key_id": bill.api_key_id,
                "tenant_id": bill.tenant_id,
                "period_start": bill.period_start.isoformat(),
                "period_end": bill.period_end.isoformat(),
                "usage_count": bill.usage_count,
                "total_amount": float(bill.total_amount),
                "line_items": bill.line_items,
                "status": bill.status,
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/billing/bills/{bill_id}/export", summary="管理：账单导出 CSV")
def admin_export_bill_csv(
    bill_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    bill = db.get(ApiBill, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="账单不存在")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["账单ID", "API Key ID", "租户ID", "周期开始", "周期结束", "端点", "调用次数", "金额(分)"])
    for endpoint, item in (bill.line_items or {}).items():
        writer.writerow(
            [
                bill.id,
                bill.api_key_id,
                bill.tenant_id,
                bill.period_start.isoformat(),
                bill.period_end.isoformat(),
                endpoint,
                item.get("count", 0),
                item.get("amount", 0),
            ]
        )
    writer.writerow(["", "", "", "", "", "合计", bill.usage_count, int(bill.total_amount)])

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="bill_{bill.id}_{bill.period_start.strftime("%Y%m")}.csv"'
        },
    )
