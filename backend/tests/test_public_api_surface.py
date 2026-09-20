"""E1: the unauthenticated API surface is a pinned list, not an accident.

Auth here is declared per endpoint (`Depends(get_current_user)`), so a new route is
public unless somebody remembers to protect it. That is how
`GET /api/system/metrics` came to answer anonymous callers with provider names,
model names and degraded-answer counters — and because `frontend/nginx.conf`
proxies all of `/api/` to the backend, "anonymous caller" includes the public
internet under the documented `docker-compose.prod.yml` topology.

This test walks the real router graph and fails when an operation carries none of
the credentials the codebase knows about and is not listed below with a reason.
"""

from __future__ import annotations

from app.api.auth import get_current_user, require_admin
from app.api.external.auth import require_api_key
from app.api.router import api_router
from app.api.system import require_metrics_reader

# require_metrics_reader 内部直接调用 get_current_user（为了让采集令牌能在无会话时通过），
# 所以 FastAPI 的依赖树上看不见会话依赖，只能显式登记。
AUTH_DEPS = {
    get_current_user: "session",
    require_admin: "admin",
    require_api_key: "api_key",
    require_metrics_reader: "metrics_reader",
}

# 每条都得有理由。新增一条就要在这里写清为什么允许匿名可调。
PUBLIC_OPERATIONS = {
    # 登录 / 注册 / 找回：拿到身份之前必须可调
    ("POST", "/auth/register"),
    ("POST", "/auth/login"),
    ("POST", "/auth/reset-password"),
    ("POST", "/auth/forgot-password"),
    ("POST", "/auth/verify-email"),
    ("POST", "/auth/reset-password-with-token"),
    # 探活：容器编排读它，不能要求凭据
    ("GET", "/system/health"),
    ("GET", "/system/ready"),
    # 登录页在拿到 token 之前就要用的静态字典与运行时品牌
    ("GET", "/jobs/cities"),
    ("GET", "/interview/config/types"),
    ("GET", "/tenant/brand"),
    ("GET", "/subscription/plans"),
    # 飞书 SSO 由 state 参数自证；支付回调由渠道签名自证（签名在校验在处理体内）
    ("GET", "/organizations/sso/feishu/{slug}/start"),
    ("GET", "/organizations/sso/feishu/callback"),
    ("POST", "/subscription/pay-callback"),
}


def _credential_kinds(dependant, seen: set[int]) -> set[str]:
    call = getattr(dependant, "call", None)
    kinds = {AUTH_DEPS[call]} if call in AUTH_DEPS else set()
    for sub in getattr(dependant, "dependencies", []) or []:
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        kinds |= _credential_kinds(sub, seen)
    return kinds


def _operations() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """(需要凭据的操作, 匿名可调的操作)"""
    protected: set[tuple[str, str]] = set()
    public: set[tuple[str, str]] = set()
    for route in api_router.routes:
        dependant = getattr(route, "dependant", None)
        kinds = _credential_kinds(dependant, set()) if dependant is not None else set()
        methods = sorted(getattr(route, "methods", None) or ["WS"])
        for method in methods:
            item = (method, getattr(route, "path", "?"))
            (protected if kinds else public).add(item)
    return protected, public


def test_the_walk_finds_credentials_on_the_bulk_of_the_api():
    """非空断言：清单测试只有在遍历真的能看到依赖时才有意义。"""
    protected, public = _operations()
    assert len(protected) >= 200, f"只有 {len(protected)} 条操作被判为需要凭据——遍历大概失效了"
    assert len(public) < 30, f"匿名可调操作 {len(public)} 条，远超清单规模"


def test_unauthenticated_surface_matches_the_pinned_list():
    _, public = _operations()
    unexpected = sorted(public - PUBLIC_OPERATIONS)
    stale = sorted(PUBLIC_OPERATIONS - public)
    assert not unexpected, f"新增的匿名可调端点：{unexpected}"
    assert not stale, f"这些端点其实已经有凭据了，把条目从清单里删掉：{stale}"


def test_metrics_endpoint_is_behind_a_credential():
    _, public = _operations()
    assert ("GET", "/system/metrics") not in public
