"""租户 API：品牌白标 + 平台管理员租户管理（T2-5 / T4-1）。

- `GET /tenant/brand`：公开接口，返回当前租户品牌（未配置回落默认），供前端运行时覆盖主题；
- `GET/POST /admin/tenants`：管理员租户列表（分页+搜索）/ 创建；
- `PUT /admin/tenants/{id}`：更新租户（状态/到期/套餐/基础信息），停用置 expired；
- `POST /admin/tenants/{id}/admin`：分配租户管理员；
- `GET/POST /admin/tenants/{id}/domains`、`DELETE /admin/tenants/{id}/domains/{domain}`：域名绑定管理；
- `PUT /admin/tenants/{id}/brand`：更新品牌配置（organization 字段 + tenant_configs）；
- `POST /admin/tenants/{id}/jobs`、`POST /admin/tenants/{id}/knowledge`：导入岗位/知识（T3-3）。

品牌数据来源：
- organization 列：name / logo_url / primary_color；
- tenant_configs（config_key=`brand.*`）：favicon / login_bg / company / contact。

敏感操作统一写审计日志（audit_service.write_audit_log）。
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.database import get_db
from app.core.tenant_context import TenantContext, normalize_hostname, require_tenant
from app.models.organization import ORGANIZATION_STATUSES, Organization
from app.models.subscription import SubscriptionOrder
from app.models.tenant import TenantConfig, TenantDomainBinding
from app.models.user import User
from app.services import job_recommend_engine, knowledge_service
from app.services.audit_service import write_audit_log
from app.services.subscription_service import restore_tenant_subscriptions
from app.utils.http_errors import api_error
from app.utils.response import ERR_FILE, ERR_PARAM, ok
from app.utils.time_helper import utc_now_naive

# 租户知识文档上传限制（与 app/api/knowledge.py 保持一致）
_KB_ALLOWED_EXTENSIONS = {"txt", "md", "pdf", "docx", "doc"}
_KB_ALLOWED_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/octet-stream",
}
_KB_MAX_FILE_SIZE = 20 * 1024 * 1024

router = APIRouter()
admin_router = APIRouter()

# 品牌主色默认值（与前端 styles/main.css `--app-primary` 保持一致）
DEFAULT_PRIMARY_COLOR = "#2563eb"

# tenant_configs 品牌配置键（短名 -> 完整 config_key）
_BRAND_CONFIG_KEYS = {
    "favicon": "brand.favicon",
    "login_bg": "brand.login_bg",
    "company": "brand.company",
    "contact": "brand.contact",
}


def _load_brand_config(db: Session, tenant_id: int) -> dict:
    rows = db.query(TenantConfig).filter(TenantConfig.tenant_id == tenant_id).all()
    config = {row.config_key: row.config_value for row in rows}
    return {short: config.get(full, "") for short, full in _BRAND_CONFIG_KEYS.items()}


def _upsert_brand_config(db: Session, tenant_id: int, updates: dict) -> None:
    for short, value in updates.items():
        full = _BRAND_CONFIG_KEYS[short]
        row = (
            db.query(TenantConfig)
            .filter(TenantConfig.tenant_id == tenant_id, TenantConfig.config_key == full)
            .first()
        )
        if row is None:
            db.add(TenantConfig(tenant_id=tenant_id, config_key=full, config_value=value))
        else:
            row.config_value = value


def _brand_payload(org: Organization, config: dict) -> dict:
    return {
        "tenant_id": org.id,
        "name": org.name,
        "logo_url": org.logo_url or "",
        "primary_color": org.primary_color or DEFAULT_PRIMARY_COLOR,
        "favicon": config.get("favicon", ""),
        "login_bg": config.get("login_bg", ""),
        "company": config.get("company") or org.name,
        "contact": config.get("contact", ""),
    }


@router.get("/brand", summary="获取当前租户品牌配置（未配置回落默认）")
def get_brand(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(require_tenant),
):
    org = db.get(Organization, tenant.tenant_id)
    if org is None:
        return ok(
            {
                "tenant_id": tenant.tenant_id,
                "name": tenant.name,
                "logo_url": "",
                "primary_color": DEFAULT_PRIMARY_COLOR,
                "favicon": "",
                "login_bg": "",
                "company": tenant.name,
                "contact": "",
            }
        )
    return ok(_brand_payload(org, _load_brand_config(db, org.id)))


@admin_router.get("", summary="管理员：租户列表（分页 + 搜索 + 状态过滤）")
def list_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="按名称/标识搜索"),
    status: str = Query("", description="按状态过滤：active/suspended/expired"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    q = db.query(Organization)
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        q = q.filter((Organization.name.like(like)) | (Organization.slug.like(like)))
    if status.strip():
        # 前端「状态筛选」此前被忽略：补上 Organization.status 过滤
        q = q.filter(Organization.status == status.strip())
    total = q.count()
    items = (
        q.order_by(Organization.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok({"total": total, "page": page, "page_size": page_size, "items": [o.to_dict() for o in items]})


@admin_router.post("", summary="管理员：创建租户")
def create_tenant(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    name = str(payload.get("name") or "").strip()
    slug = re.sub(r"[^a-z0-9-]+", "-", str(payload.get("slug") or name).strip().lower()).strip("-")
    if not name or not slug or len(name) > 100 or len(slug) > 80:
        raise api_error(400, "租户名称或标识不合法", ERR_PARAM)
    if db.query(Organization).filter(Organization.slug == slug).first():
        raise api_error(409, "租户标识已存在", ERR_PARAM)

    expires_at = None
    if payload.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
        except ValueError:
            expires_at = None

    org = Organization(
        name=name,
        slug=slug,
        owner_id=current_user.id,
        admin_user_id=current_user.id,
        industry=str(payload.get("industry") or "") or None,
        logo_url=str(payload.get("logo_url") or "") or None,
        primary_color=str(payload.get("primary_color") or "") or None,
        plan_tier=str(payload.get("plan_tier") or "free"),
        expires_at=expires_at,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    write_audit_log(db, current_user, "tenant.create", "tenant", str(org.id), {"name": org.name, "slug": org.slug}, request)
    return ok(org.to_dict(), message="租户已创建")


@admin_router.put("/{tenant_id}", summary="管理员：更新租户（状态/到期/套餐/基础信息）")
def update_tenant(
    tenant_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """更新租户。status=expired 即停用（T4-1，租户中间件对非 active 返回 403）。

    可更新：name / industry / plan_tier / status / expires_at / primary_color / logo_url。
    slug 不可变更（作为租户唯一标识）。每次变更写审计日志（记录变更项）。
    """
    org = _require_tenant_org(db, tenant_id)
    changes: list[str] = []

    if "name" in payload:
        name = str(payload["name"] or "").strip()
        if not name or len(name) > 100:
            raise api_error(400, "租户名称不合法", ERR_PARAM)
        if name != org.name:
            changes.append(f"名称:{org.name}→{name}")
        org.name = name

    if "industry" in payload:
        industry = str(payload["industry"]).strip()
        if industry != (org.industry or ""):
            changes.append(f"行业:{org.industry or '-'}→{industry}")
        org.industry = industry or None

    if "plan_tier" in payload:
        tier = str(payload["plan_tier"]).strip()
        if tier not in {"free", "pro", "enterprise"}:
            raise api_error(400, "套餐不合法: free/pro/enterprise", ERR_PARAM)
        if tier != org.plan_tier:
            changes.append(f"套餐:{org.plan_tier}→{tier}")
        org.plan_tier = tier

    if "status" in payload:
        status = str(payload["status"]).strip()
        if status not in ORGANIZATION_STATUSES:
            raise api_error(400, "状态不合法: active/suspended/expired", ERR_PARAM)
        if status != org.status:
            changes.append(f"状态:{org.status}→{status}")
        org.status = status

    if "expires_at" in payload:
        raw = payload["expires_at"]
        if raw is None or str(raw).strip() in ("", "null"):
            org.expires_at = None
        else:
            try:
                org.expires_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                raise api_error(400, "expires_at 不是合法 ISO 时间", ERR_PARAM)

    if "primary_color" in payload:
        color = str(payload["primary_color"]).strip()
        if color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise api_error(400, "主色必须是 #RRGGBB 格式", ERR_PARAM)
        org.primary_color = color or None

    if "logo_url" in payload:
        org.logo_url = str(payload["logo_url"]).strip() or None

    db.commit()
    db.refresh(org)
    write_audit_log(db, _admin, "tenant.update", "tenant", str(org.id), {"changes": changes}, request)
    return ok(org.to_dict(), message="租户已更新")


@admin_router.post("/{tenant_id}/admin", summary="管理员：分配租户管理员")
def assign_tenant_admin(
    tenant_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    org = _require_tenant_org(db, tenant_id)
    user_id = payload.get("user_id")
    if not isinstance(user_id, int) or user_id <= 0:
        raise api_error(400, "user_id 不合法", ERR_PARAM)
    user = db.get(User, user_id)
    if user is None:
        raise api_error(404, "用户不存在", ERR_PARAM)

    org.admin_user_id = user.id
    db.commit()
    db.refresh(org)
    write_audit_log(
        db,
        _admin,
        "tenant.assign_admin",
        "tenant",
        str(org.id),
        {"user_id": user.id, "username": user.username},
        request,
    )
    return ok({"tenant_id": org.id, "admin_user_id": user.id, "username": user.username}, message=f"已分配 {user.username} 为租户管理员")


@admin_router.post("/{tenant_id}/renew", summary="管理员：租户续费")
def renew_tenant(
    tenant_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """续费（T4-3）：延长 expires_at、恢复租户 active 与订阅状态、记录 paid 订单、写审计。

    payload: {months: int(1-36), amount?: 实付金额(分)}
    立即生效（无需等调度周期）；调度器每小时扫描兜底。
    """
    org = _require_tenant_org(db, tenant_id)

    months_raw = payload.get("months")
    months = int(months_raw) if months_raw is not None else 1
    if months < 1 or months > 36:
        raise api_error(400, "续费月数不合法: 1-36", ERR_PARAM)
    amount = payload.get("amount")
    if amount is not None and (not isinstance(amount, (int, float)) or amount < 0):
        raise api_error(400, "金额不合法", ERR_PARAM)

    now = utc_now_naive()  # 与 DB 读回的 naive DateTime 一致
    base = org.expires_at if (org.expires_at and org.expires_at > now) else now
    new_expiry = base + timedelta(days=30 * months)

    # 记录订单（订阅与单次支付同表；续费单 plan_tier 取租户当前套餐）
    order = SubscriptionOrder(
        user_id=_admin.id,
        tenant_id=org.id,
        plan_tier=org.plan_tier or "free",
        amount=amount if amount is not None else 0,
        currency="cny",
        status="paid",
        payment_method="renewal",
        transaction_id=f"renew-{org.id}-{int(now.timestamp())}",
        period_start=now,
        period_end=new_expiry,
        created_at=now,
        paid_at=now,
    )
    db.add(order)

    # 恢复租户与订阅
    org.status = "active"
    org.expires_at = new_expiry
    restore_tenant_subscriptions(db, org)

    db.commit()
    write_audit_log(
        db,
        _admin,
        "tenant.renew",
        "tenant",
        str(org.id),
        {"months": months, "amount": amount, "expires_at": new_expiry.isoformat()},
        request,
    )
    return ok(org.to_dict(), message=f"租户已续费 {months} 个月，到期 {new_expiry.date()}")


@admin_router.get("/{tenant_id}/domains", summary="管理员：租户域名列表")
def list_tenant_domains(
    tenant_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    org = _require_tenant_org(db, tenant_id)
    rows = (
        db.query(TenantDomainBinding)
        .filter(TenantDomainBinding.tenant_id == org.id)
        .order_by(TenantDomainBinding.is_primary.desc(), TenantDomainBinding.id.asc())
        .all()
    )
    return ok([row.to_dict() for row in rows])


@admin_router.post("/{tenant_id}/domains", summary="管理员：绑定域名")
def bind_tenant_domain(
    tenant_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    org = _require_tenant_org(db, tenant_id)
    domain = normalize_hostname(str(payload.get("domain") or ""))
    if not domain:
        raise api_error(400, "域名不合法", ERR_PARAM)
    if not re.fullmatch(r"(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}", domain):
        raise api_error(400, f"域名格式不合法: {domain}", ERR_PARAM)
    if db.query(TenantDomainBinding).filter(TenantDomainBinding.domain == domain).first():
        raise api_error(409, "域名已被绑定", ERR_PARAM)

    is_primary = bool(payload.get("is_primary"))
    if is_primary:
        db.query(TenantDomainBinding).filter(TenantDomainBinding.tenant_id == org.id).update(
            {TenantDomainBinding.is_primary: 0}
        )
    row = TenantDomainBinding(tenant_id=org.id, domain=domain, is_primary=1 if is_primary else 0)
    db.add(row)
    db.commit()
    db.refresh(row)
    write_audit_log(db, _admin, "tenant.bind_domain", "tenant", str(org.id), {"domain": domain, "is_primary": is_primary}, request)
    return ok(row.to_dict(), message=f"域名 {domain} 已绑定")


@admin_router.delete("/{tenant_id}/domains/{domain}", summary="管理员：解绑域名")
def unbind_tenant_domain(
    tenant_id: int,
    domain: str,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    org = _require_tenant_org(db, tenant_id)
    row = (
        db.query(TenantDomainBinding)
        .filter(TenantDomainBinding.tenant_id == org.id, TenantDomainBinding.domain == domain)
        .first()
    )
    if row is None:
        raise api_error(404, "域名未绑定", ERR_PARAM)
    db.delete(row)
    db.commit()
    write_audit_log(db, _admin, "tenant.unbind_domain", "tenant", str(org.id), {"domain": domain}, request)
    return ok({"tenant_id": org.id, "domain": domain}, message=f"域名 {domain} 已解绑")


@admin_router.put("/{tenant_id}/brand", summary="管理员：更新租户品牌配置")
def update_tenant_brand(
    tenant_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    org = db.get(Organization, tenant_id)
    if org is None:
        raise api_error(404, "租户不存在", ERR_PARAM)

    if "name" in payload and str(payload["name"]).strip():
        org.name = str(payload["name"]).strip()
    if "logo_url" in payload:
        org.logo_url = str(payload["logo_url"]).strip() or None
    if "primary_color" in payload:
        org.primary_color = str(payload["primary_color"]).strip() or None

    config_updates = {
        short: str(payload[short]).strip()
        for short in _BRAND_CONFIG_KEYS
        if short in payload and str(payload[short]).strip()
    }
    if config_updates:
        _upsert_brand_config(db, org.id, config_updates)

    db.commit()
    db.refresh(org)
    write_audit_log(db, _admin, "tenant.update_brand", "tenant", str(org.id), {"fields": list(payload.keys())}, request)
    return ok(_brand_payload(org, _load_brand_config(db, org.id)), message="品牌配置已更新")


def _require_tenant_org(db: Session, tenant_id: int) -> Organization:
    org = db.get(Organization, tenant_id)
    if org is None:
        raise api_error(404, "租户不存在", ERR_PARAM)
    return org


@admin_router.post("/{tenant_id}/jobs", summary="管理员：批量导入租户岗位 JD")
def import_tenant_jobs(
    tenant_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """批量导入岗位到指定租户（T3-3）：岗位只在该租户的推荐/检索中出现。

    payload.items: [{title, company, location, salary_range, raw_text, industry, ...}]
    逐条校验 title 与 raw_text 必填，失败项计入 errors，成功项继续导入。
    """
    org = _require_tenant_org(db, tenant_id)
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise api_error(400, "items 不能为空，请至少提供一条岗位", ERR_PARAM)

    jobs: list[dict] = []
    errors: list[dict] = []
    for idx, item in enumerate(items):
        title = str((item or {}).get("title") or "").strip()
        raw_text = str((item or {}).get("raw_text") or (item or {}).get("description") or "").strip()
        if not title:
            errors.append({"index": idx, "error": "title 不能为空"})
            continue
        if not raw_text:
            errors.append({"index": idx, "error": "raw_text 不能为空"})
            continue
        jobs.append(
            {
                "title": title,
                "company": str(item.get("company") or "").strip(),
                "location": str(item.get("location") or "").strip(),
                "salary_range": str(item.get("salary_range") or "").strip(),
                "raw_text": raw_text,
                "industry": str(item.get("industry") or "").strip(),
                "parsed_json": item.get("parsed_json") or {},
            }
        )

    ids = job_recommend_engine.batch_import_jobs(
        db, jobs, source="tenant-import", tenant_id=org.id
    )
    write_audit_log(
        db,
        _admin,
        "tenant.import_jobs",
        "tenant",
        str(org.id),
        {"imported": len(ids), "failed": len(errors)},
        request,
    )
    return ok(
        {
            "tenant_id": org.id,
            "imported": len(ids),
            "failed": len(errors),
            "jd_ids": ids,
            "errors": errors,
        },
        message=f"租户岗位导入完成: 成功 {len(ids)} 个, 失败 {len(errors)} 个",
    )


@admin_router.post("/{tenant_id}/knowledge", summary="管理员：为租户上传知识文档")
async def import_tenant_knowledge(
    tenant_id: int,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: str = Form("general"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """上传知识文档到指定租户（T3-3）：文档只在租户的 RAG 检索中出现。"""
    org = _require_tenant_org(db, tenant_id)

    if not file or not file.filename:
        raise api_error(400, "上传文件不能为空", ERR_FILE)

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in _KB_ALLOWED_EXTENSIONS:
        raise api_error(400, f"不支持的文件类型: .{ext}", ERR_FILE)

    mime = (file.content_type or "").lower()
    if mime and mime not in _KB_ALLOWED_MIME_TYPES:
        raise api_error(400, f"不支持的内容类型: {mime}", ERR_FILE)

    title = (title or "").strip()
    if not title:
        raise api_error(400, "title 不能为空", ERR_PARAM)

    raw = await file.read()
    if len(raw) > _KB_MAX_FILE_SIZE:
        raise api_error(400, f"文件过大: {len(raw)} 字节（上限 20MB）", ERR_FILE)

    try:
        doc = knowledge_service.save_and_process(
            db,
            raw,
            file.filename,
            title,
            doc_type,
            user_id=None,
            organization_id=org.id,
            tenant_id=org.id,
        )
    except Exception as exc:
        raise api_error(500, f"文档处理失败: {exc}", ERR_PARAM)

    write_audit_log(
        db,
        _admin,
        "tenant.import_knowledge",
        "tenant",
        str(org.id),
        {"doc_id": doc.id, "title": doc.title, "file_name": doc.file_name, "status": doc.status},
        request,
    )
    return ok(
        {
            "tenant_id": org.id,
            "id": doc.id,
            "title": doc.title,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "file_size": doc.file_size or 0,
            "doc_type": doc.doc_type,
            "status": doc.status,
            "error_msg": doc.error_msg,
            "create_time": doc.create_time.isoformat() if doc.create_time else None,
        },
        message=f"租户知识文档上传完成, 状态={doc.status}",
    )
