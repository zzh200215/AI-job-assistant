"""租户上下文：请求级 ContextVar + Header/域名解析（T2-3）。

- `TenantContext`：当前租户快照（tenant_id + 品牌配置）；
- `get_current_tenant()` / `set_current_tenant()` / `reset_current_tenant()`：ContextVar 读写；
- `resolve_tenant_by_host()`：查 `tenant_domain_bindings` 解析域名归属租户；
- `load_tenant_context()`：完整解析（X-Tenant-Id 优先 → Host → 默认租户 id=1）；
- `tenant_context_middleware`：可复用 HTTP 中间件（main.py 注册，测试直接挂载）；
- `require_tenant`：FastAPI 依赖，供需要租户的接口使用。

解析约定（T2-1 定稿：organization 即租户，tenant_id = organization.id）：
- 显式 X-Tenant-Id：租户必须存在且 status=active，否则 403（code=-13 租户不可用）；
- 未带 X-Tenant-Id：按 Host 解析域名绑定；未绑定 → 回落内置默认租户 id=1（单租户存量数据归属）；
- 域名已绑定但租户不存在/停用 → 403。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.organization import ORGANIZATION_STATUS_ACTIVE, Organization
from app.models.tenant import TenantDomainBinding
from app.utils.response import ERR_TENANT, fail

# 内置默认租户（单租户模式的存量数据归属，T2-1 定稿）
DEFAULT_TENANT_ID: int = 1
DEFAULT_TENANT_NAME: str = "默认租户"


class TenantUnavailableError(Exception):
    """租户不存在或状态不可用 → 中间件返回 403 code=-13。"""


@dataclass
class TenantContext:
    """当前请求租户快照（品牌配置来自 organization 字段）。"""

    tenant_id: int
    name: str = DEFAULT_TENANT_NAME
    slug: str = ""
    status: str = ORGANIZATION_STATUS_ACTIVE
    plan_tier: str = "free"
    brand: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "slug": self.slug,
            "status": self.status,
            "plan_tier": self.plan_tier,
            "brand": self.brand,
        }


_tenant_ctx: ContextVar[TenantContext | None] = ContextVar("current_tenant", default=None)


def get_current_tenant() -> TenantContext | None:
    """读取当前请求租户；中间件未运行时返回 None。"""
    return _tenant_ctx.get()


def set_current_tenant(ctx: TenantContext | None) -> Token:
    return _tenant_ctx.set(ctx)


def reset_current_tenant(token: Token) -> None:
    _tenant_ctx.reset(token)


def current_tenant_id() -> int:
    """当前租户 id（未注入时回落默认租户），供查询过滤使用（T2-4）。"""
    ctx = get_current_tenant()
    return ctx.tenant_id if ctx else DEFAULT_TENANT_ID


def tenant_filter(model):
    """返回当前租户对模型实例的过滤条件（SQLAlchemy BinaryExpression）。

    列表/详情/统计查询统一走本函数，**禁止业务代码散写 tenant_id 判断**（T2-4）：
        db.query(Resume).filter(tenant_filter(Resume), ...)
    未注入租户上下文（如单测）时按默认租户 1 过滤，保证存量单租户行为不变。
    """
    return model.tenant_id == current_tenant_id()


def stamp_tenant(instance) -> object:
    """为新建行打上当前租户标记（T2-4 写入强制隔离）。

    使用：`row = stamp_tenant(Resume(...))` 后统一 add。未注入上下文时写入默认租户 1。
    """
    if hasattr(instance, "tenant_id"):
        instance.tenant_id = current_tenant_id()
    return instance


def normalize_hostname(host: str | None) -> str | None:
    """归一化域名：小写、去 scheme/端口/首尾点。域名入库（T4-1）与解析均用此规则。"""
    if not host:
        return None
    host = host.strip().lower().strip(".")
    if ":" in host:
        host = host.split(":", 1)[0]
    return host or None


def _default_tenant() -> TenantContext:
    return TenantContext(tenant_id=DEFAULT_TENANT_ID)


def _tenant_from_org(org: Organization) -> TenantContext:
    return TenantContext(
        tenant_id=org.id,
        name=org.name,
        slug=org.slug,
        status=org.status,
        plan_tier=org.plan_tier or "free",
        brand={
            "industry": org.industry,
            "logo_url": org.logo_url,
            "primary_color": org.primary_color,
        },
    )


def resolve_tenant_by_host(host: str | None, db: Session) -> TenantContext | None:
    """查 tenant_domain_bindings 解析域名归属租户。

    - 域名未绑定 → 返回 None（调用方回落默认租户）；
    - 已绑定但租户不存在/停用 → 抛 TenantUnavailableError（403）。
    """
    normalized = normalize_hostname(host)
    if normalized is None:
        return None

    binding = db.scalar(
        select(TenantDomainBinding).where(
            TenantDomainBinding.domain == normalized,
            TenantDomainBinding.status == "active",
        )
    )
    if binding is None:
        return None

    org = db.get(Organization, binding.tenant_id)
    if org is None:
        return None
    if org.status != ORGANIZATION_STATUS_ACTIVE:
        raise TenantUnavailableError(f"tenant {org.id} status={org.status}")
    return _tenant_from_org(org)


def parse_tenant_id(raw: str | None) -> int | None:
    """解析 X-Tenant-Id 头；空 → None；非正整数 → 抛 TenantUnavailableError。"""
    if raw is None or not raw.strip():
        return None
    raw = raw.strip()
    if not raw.isdigit():
        raise TenantUnavailableError(f"invalid X-Tenant-Id: {raw!r}")
    return int(raw)


def load_tenant_context(
    db: Session,
    tenant_id: int | None = None,
    host: str | None = None,
) -> TenantContext:
    """完整解析当前租户：显式 tenant_id 优先，其次 Host，最后默认租户 1。"""
    if tenant_id is not None:
        org = db.get(Organization, tenant_id)
        if org is None or org.status != ORGANIZATION_STATUS_ACTIVE:
            raise TenantUnavailableError(f"tenant {tenant_id} unavailable")
        return _tenant_from_org(org)

    host_ctx = resolve_tenant_by_host(host, db)
    if host_ctx is not None:
        return host_ctx
    return _default_tenant()


# ===== 中间件 =====

_tenant_session_factory = SessionLocal


def set_tenant_session_factory(factory) -> None:
    """测试用：替换中间件使用的 Session 工厂（默认 SessionLocal）。"""
    global _tenant_session_factory
    _tenant_session_factory = factory


def reset_tenant_session_factory() -> None:
    """恢复中间件默认 Session 工厂。"""
    global _tenant_session_factory
    _tenant_session_factory = SessionLocal


def _tenant_unavailable_response() -> JSONResponse:
    return JSONResponse(status_code=403, content=fail(message="租户不可用", code=ERR_TENANT))


async def tenant_context_middleware(request: Request, call_next):
    """HTTP 中间件：解析并注入当前租户（注册于 CORS 之后、路由之前）。

    - X-Tenant-Id 显式指定 → 必须存在且 active，否则 403 code=-13；
    - 未指定 → Host 解析域名绑定，未绑定回落默认租户 id=1；
    - OPTIONS 预检直接放行（避免跨域预检被租户校验拦截）。
    """
    if request.method == "OPTIONS":
        return await call_next(request)

    tenant_id = None
    raw = request.headers.get("X-Tenant-Id")
    if raw:
        try:
            tenant_id = parse_tenant_id(raw)
        except TenantUnavailableError:
            return _tenant_unavailable_response()

    host = request.headers.get("host") or (request.url.hostname if request.url else None)

    db = _tenant_session_factory()
    try:
        try:
            ctx = load_tenant_context(db, tenant_id=tenant_id, host=host)
        except TenantUnavailableError:
            return _tenant_unavailable_response()
    finally:
        db.close()

    token = set_current_tenant(ctx)
    try:
        return await call_next(request)
    finally:
        reset_current_tenant(token)


def require_tenant() -> TenantContext:
    """FastAPI 依赖：返回当前租户上下文；未注入（如单测直调）回落默认租户 1。"""
    ctx = get_current_tenant()
    return ctx if ctx is not None else _default_tenant()
