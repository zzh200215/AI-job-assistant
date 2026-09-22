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

from fastapi import APIRouter

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


# ---------------------------------------------------------------- E11：默认要会话的前缀

# 这些前缀在本次改动前就已经 100% 带会话依赖，所以挂上 `SESSION_GUARD` 不改变任何一条已有
# 响应。改变的是"以后有人新增一条端点、忘了写 Depends(get_current_user)"的命运：它出生就要求
# 会话，而不是安静地对公网开放。挂不上的是混着公开端点的前缀（auth / system / jobs /
# interview / organizations / subscription / tenant / v1），它们仍由上面那张清单钉住。
CONSTRUCT_PROTECTED_PREFIXES = {
    "/user",
    "/dashboard",
    "/eval-reports",
    "/resume",
    "/jd",
    "/analysis",
    "/history",
    "/knowledge",
    "/analytics",
    "/admin",
    "/admin/tenants",
    "/agent",
    "/multi-agent",
    "/targets",
    "/journals",
    "/career-path",
    "/salary",
    "/timeline",
    "/tracking",
    "/notifications",
    "/prompt-traces",
    "/reminders",
}


def _matched_prefix(path: str) -> str | None:
    """最长前缀匹配：/admin/tenants/x 归 /admin/tenants，不归 /admin。"""
    best = None
    for prefix in CONSTRUCT_PROTECTED_PREFIXES:
        if (path == prefix or path.startswith(prefix + "/")) and (best is None or len(prefix) > len(best)):
            best = prefix
    return best


def _kinds_by_operation() -> dict[tuple[str, str], set[str]]:
    out: dict[tuple[str, str], set[str]] = {}
    for route in api_router.routes:
        dependant = getattr(route, "dependant", None)
        kinds = _credential_kinds(dependant, set()) if dependant is not None else set()
        for method in sorted(getattr(route, "methods", None) or ["WS"]):
            out[(method, getattr(route, "path", "?"))] = set(kinds)
    return out


def test_guarded_prefixes_actually_cover_every_operation_under_them():
    kinds = _kinds_by_operation()
    covered = {op: ks for op, ks in kinds.items() if _matched_prefix(op[1])}
    naked = sorted(op for op, ks in covered.items() if "session" not in ks)
    assert not naked, f"落在被守护前缀下却没被判为需要会话：{naked}"
    # 非空断言：量过是 123 条，低于这个数说明前缀表没真的对上前缀（改名/写错）。
    assert len(covered) >= 120, f"守护前缀只盖到 {len(covered)} 条操作，和量出来的 123 对不上"


def _include_level_deps(route) -> set:
    """只取 include 级依赖——这才是"构造保证"，端点自己写的 Depends 不算。"""
    return {getattr(d, "dependency", None) for d in (getattr(route, "dependencies", None) or [])}


def test_the_session_guard_is_mounted_on_every_protected_prefix():
    """上面那条测不出守护有没有真的挂上（这些端点本来就各自写了 Depends）。
    这条测的是 include 级依赖本身：没有它，构造保证就是句空话。"""
    seen: set[str] = set()
    missing = []
    for route in api_router.routes:
        path = getattr(route, "path", "?")
        prefix = _matched_prefix(path)
        if prefix is None:
            continue
        seen.add(prefix)
        if get_current_user not in _include_level_deps(route):
            missing.append((prefix, path))
    assert not missing, f"在守护前缀下却没有 include 级会话依赖：{missing[:8]}"
    # 反向：表里写错前缀（路由里根本没有它）也要报，否则守护范围是想象出来的。
    assert seen == CONSTRUCT_PROTECTED_PREFIXES, f"前缀表与真实路由不符：{sorted(seen ^ CONSTRUCT_PROTECTED_PREFIXES)}"


def test_guarded_prefixes_never_swallow_a_public_operation():
    """有人把 `/jobs` 顺手加进上表时，`GET /jobs/cities`（登录页要用）会当场变 401。"""
    for method, path in sorted(PUBLIC_OPERATIONS):
        prefix = _matched_prefix(path)
        assert prefix is None, f"{method} {path} 是公开端点，却在被守护前缀 {prefix} 下"


def _probe_app(**include_kwargs):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    probe = APIRouter()

    @probe.get("/probe")
    def _probe():  # 故意不声明任何凭据依赖
        return {"ok": True}

    @probe.get("/probe-auth")
    def _probe_auth(current_user=Depends(get_current_user)):  # 端点自己也写了一次
        return {"ok": bool(current_user)}

    app = FastAPI()
    app.include_router(probe, **include_kwargs)
    return TestClient(app)


def test_the_guard_protects_an_endpoint_that_forgot_to_declare_auth():
    """正向证明：自己不写凭据的端点，挂在守护前缀下对匿名调用返回 401。"""
    from app.api.router import SESSION_GUARD

    guarded = _probe_app(prefix="/resume", dependencies=SESSION_GUARD)
    assert guarded.get("/resume/probe").status_code == 401
    # 对照组：同一个 router 不挂守护时必须是匿名可调，否则上面那条断言是在空转。
    plain = _probe_app(prefix="/resume")
    assert plain.get("/resume/probe").status_code == 200


def test_the_guard_does_not_resolve_the_user_twice():
    """端点自己写了一次、前缀又挂了一次 → 只该解析一次，否则每个请求多一趟 DB。"""
    from app.api.router import SESSION_GUARD

    calls = []

    def counting():
        calls.append(1)
        return object()

    client = _probe_app(prefix="/resume", dependencies=SESSION_GUARD)
    client.app.dependency_overrides[get_current_user] = counting
    assert client.get("/resume/probe-auth").status_code == 200
    assert len(calls) == 1, f"get_current_user 每请求跑了 {len(calls)} 次，守护在重复解析"
