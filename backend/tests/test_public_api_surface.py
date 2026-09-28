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

from uuid import uuid4

import pytest
from fastapi import APIRouter, Depends, FastAPI

from app.api.auth import get_current_user, require_admin
from app.api.external.auth import require_api_key
from app.api.router import api_router
from app.api.system import require_metrics_reader
from app.core.api_access import ANONYMOUS_OPERATIONS, OTHER_CREDENTIAL_OPERATIONS
from app.core.security import create_access_token, hash_password
from app.models.user import User

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


# ------------------------------------------------- E11 末段：装配期补齐会话依赖
#
# 这条债原本写的是"端点级拆分"。三种做法都实测过，前两种被数据否掉了：
#   * 按路径给那 8 段混合前缀挂 include 级守护 —— 会把 `GET /jobs/cities`（登录页要用）一起关死；
#   * 每个模块拆出 `public_router` —— 真跑起来有 42 个测试文件自建 mini-app，其中十几个只
#     `include_router(auth_router)`，拆完它们全变 404；以后任何自建装配漏挂 public_router
#     都是一次莫名 404。为一条"构造保证"换这个代价不值。
#   * 在唯一 /api 挂载点上一道**请求期**的门 —— 拦得住，但实测每次带凭据请求在 `tb_user` 上发
#     **两条** SELECT（门不在依赖树上，进不去端点那个 session 的 identity map），还多开一条
#     session（连接池默认 5+10）。
# 现在是第三种的正确形态：判定还在装配期，但补的是 FastAPI 请求期真正走的那棵依赖树
# （`app/core/api_access.py:apply_default_deny`，由 `app/api/router.py` 末尾调用）。
# 于是覆盖面不区分前缀、不需要任何人记得挂第二个 router，而一条受守护请求仍只解析一次凭据。

ALL_LISTED = ANONYMOUS_OPERATIONS | OTHER_CREDENTIAL_OPERATIONS


def _guarded_and_public_operations() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """(有会话凭据的操作, 清单上的操作)，键都带 `/api` 前缀，与 `api_access` 那两张清单同形。"""
    guarded: set[tuple[str, str]] = set()
    listed: set[tuple[str, str]] = set()
    for op, kinds in _kinds_by_operation().items():
        key = (op[0], "/api" + op[1])
        if "session" in kinds:
            guarded.add(key)
        elif key in ALL_LISTED:
            listed.add(key)
    return guarded, listed


def test_every_operation_outside_the_two_lists_carries_a_session_credential():
    """构造保证的正面：清单外没有任何一条操作可以匿名调（遍历真实依赖树，不看注释）。"""
    guarded, listed = _guarded_and_public_operations()
    naked = sorted(
        (m, "/api" + p)
        for (m, p), kinds in _kinds_by_operation().items()
        if not kinds and (m, "/api" + p) not in ALL_LISTED
    )
    assert not naked, f"这些操作既不在两张清单里也没有会话凭据：{naked[:8]}"
    # 非空断言：量过是 232 条路由（E29 删掉 /tracking 之前是 233），远低于这个数说明遍历失效。
    assert len(guarded) >= 200, f"只核到 {len(guarded)} 条带会话凭据的操作，和真实规模对不上"
    assert (
        listed == ALL_LISTED
    ), f"清单里有操作其实已被补齐凭据（该删条目）或多出没登记的：{sorted(listed ^ ALL_LISTED)}"


def test_the_pass_attached_nothing_today_because_everyone_already_declares_auth():
    """`apply_default_deny` 今天补到 0 条——这是**事实**，不是它空转的证据（下一条测它的效果）。
    登记这个数字：以后它一旦非空，说明有人漏写了凭据却被装配期救下，值得知道发生了多少次。"""
    from app.api.router import DEFAULT_DENY_GUARDED_OPERATIONS

    assert DEFAULT_DENY_GUARDED_OPERATIONS == []


def _naked_probe_router(*, api_prefixed: bool = False):
    """一条挂在混合前缀下、自己完全不写凭据的端点——就是这次要防的那种写法。

    默认按**挂载前**的形状建（前缀 `/organizations`，与 `api_router` 里一致），因为
    `apply_default_deny` 要的就是这个形状；`api_prefixed=True` 用来测误用守卫。
    """
    naked = APIRouter()

    @naked.get("/forgot-me")
    def _forgot():
        return {"leak": True}

    app = FastAPI()
    app.include_router(naked, prefix="/api/organizations" if api_prefixed else "/organizations")
    return app


def test_the_pass_protects_an_endpoint_that_forgot_to_declare_auth():
    """裸端点经过这一趟之后必须 401；不跑这一趟必须 200（对照组，否则上一条测试是空转的）。"""
    from fastapi.testclient import TestClient

    from app.core.api_access import apply_default_deny

    app = _naked_probe_router()
    apply_default_deny(app.routes)
    guarded = TestClient(app).get("/organizations/forgot-me")
    assert guarded.status_code == 401, f"补齐后居然还能匿名调：{guarded.status_code}"

    control = TestClient(_naked_probe_router()).get("/organizations/forgot-me")
    assert control.status_code == 200, "对照组不跑这一趟就该是 200，否则上面那条断言什么都没证明"


def test_the_pass_refuses_a_route_table_that_already_carries_the_api_prefix():
    """这一趟作用在**挂载前**的 api_router 上；对着已展开成 `/api/...` 的 app.routes 调用会让
    清单永远匹配不上，公开端点被静默关死。所以误用必须炸，而不是悄悄通过。"""
    from app.core.api_access import apply_default_deny

    with pytest.raises(ValueError, match="挂载前"):
        apply_default_deny(_naked_probe_router(api_prefixed=True).routes)


def test_the_pass_leaves_alone_routes_that_already_declare_credentials():
    """已经写了 `Depends(get_current_user)` 的端点不该被再补一条：补了就是每请求两趟解析。"""
    from fastapi.testclient import TestClient

    from app.core.api_access import apply_default_deny

    declared = APIRouter()

    @declared.get("/already")
    def _already(current_user=Depends(get_current_user)):
        return {"ok": bool(current_user)}

    app = FastAPI()
    app.include_router(declared, prefix="/organizations")
    apply_default_deny(app.routes)

    route = next(r for r in app.routes if getattr(r, "path", "").endswith("/already"))
    session_deps = [d for d in route.dependant.dependencies if getattr(d, "call", None) is get_current_user]
    assert len(session_deps) == 1, f"同一请求里 get_current_user 挂了 {len(session_deps)} 次，会解析两趟"

    # 行为侧再钉一次：override 只被走一遍。
    calls = []

    def counting():
        calls.append(1)
        return object()

    app.dependency_overrides[get_current_user] = counting
    assert TestClient(app).get("/organizations/already").status_code == 200
    assert len(calls) == 1, f"get_current_user 每请求跑了 {len(calls)} 次"


def test_the_pass_refuses_a_route_object_mixing_public_and_guarded_methods():
    """一个装饰器上同时声明公开方法和需要凭据的方法时，补依赖会把公开那个一起关死——
    这种混法没人看得出来，所以直接炸在装配期。"""
    from app.core import api_access
    from app.core.api_access import apply_default_deny

    mixed = APIRouter()

    @mixed.api_route("/mix", methods=["GET", "POST"])
    def _mix():
        return {"ok": True}

    app = FastAPI()
    app.include_router(mixed, prefix="/organizations")
    # 把 GET 登记成公开、POST 不登记 → 同一个路由对象上混了两种命运
    original = api_access.NEVER_SESSION_GUARDED
    api_access.NEVER_SESSION_GUARDED = original | {("GET", "/api/organizations/mix")}
    try:
        with pytest.raises(ValueError, match="混了公开"):
            apply_default_deny(app.routes)
    finally:
        api_access.NEVER_SESSION_GUARDED = original


def test_the_real_app_blocks_anonymous_and_keeps_public_paths_working():
    """端到端钉一次装配结果：公开面还能匿名走，混合前缀下的受守护操作匿名走不了，
    而『自带别的凭据』那几条不是被会话依赖挡下的（补齐没把它们关错）。"""
    from fastapi.testclient import TestClient

    from app.main import app as real_app

    client = TestClient(real_app)
    assert client.get("/api/system/health").status_code == 200, "探活被关掉了"

    mixed_guarded = sorted(
        (m, p)
        for (m, p), kinds in _kinds_by_operation().items()
        if "session" in kinds and p.startswith("/organizations")
    )
    assert mixed_guarded, "混合前缀下没有受守护的操作，这条测试选不到靶子"
    method, path = mixed_guarded[0]
    denied = client.request(method, f"/api{path}")
    assert denied.status_code == 401, f"混合前缀下的受守护操作匿名居然通过：{method} {path} → {denied.status_code}"

    # X-API-Key 通道（这三条都是 POST）：报的必须是它自己的错。被会话依赖接管的话这里会是"未提供认证 Token"。
    external = client.post("/api/v1/external/resume/parse")
    assert external.status_code in (401, 403), f"外部能力 API 匿名调用返回了 {external.status_code}"
    assert "X-API-Key" in str(external.json()), f"外部 API 被会话依赖接管了：{str(external.json())[:120]}"

    # metrics 匿名必须拒（它内部会转调 get_current_user，所以只断言拒、不断言是谁报的错）。
    assert client.get("/api/system/metrics").status_code == 401, "metrics 对匿名开放了"


def _seed_app_engine_user(prefix: str) -> int:
    """在 app 引擎那块库里造一个能被真实 `get_db` 读到的用户，返回它的 id。

    **故意不给 id**：这条就是"BigInteger PK 在 SQLite 下必须渲染成 INTEGER 才会自增"的活证据。
    `backend/conftest.py` 里那条 `@compiles` 钩子一旦注册得比 `create_all` 晚，这里立刻撞
    `NOT NULL constraint failed: tb_user.id` —— E18 那对"fixture 插得进、SessionLocal 插不进"
    的矛盾原形就是这个顺序问题。
    """
    from app.core.database import Base, SessionLocal
    from app.core.database import engine as app_engine

    Base.metadata.create_all(bind=app_engine)
    session = SessionLocal()
    try:
        tag = uuid4().hex[:8]
        user = User(username=f"{prefix}-{tag}", email=f"{prefix}-{tag}@x.io", password=hash_password("GatePass123!"))
        session.add(user)
        session.commit()
        assert user.id is not None, "没给 id 却没拿到自增主键"
        return int(user.id)
    finally:
        session.close()


def _count_user_selects(app_engine, make_request):
    """返回 (状态码, tb_user 上的 SELECT 条数)。"""
    from sqlalchemy import event

    selects = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        if "FROM tb_user" in statement:
            selects.append(statement[:60])

    event.listen(app_engine, "before_cursor_execute", listener)
    try:
        status = make_request()
    finally:
        event.remove(app_engine, "before_cursor_execute", listener)
    return status, len(selects)


def test_a_pass_attached_guard_resolves_the_user_exactly_once():
    """补齐的那条依赖的真实代价：一次带凭据请求在 `tb_user` 上只有 **1** 条 SELECT。

    这条同时是放弃"请求期再判定"那个形态的数字依据——那扇门实测发 2 条（它不在依赖树上，
    进不去端点那个 session 的 identity map，还要多开一条 session）。
    """
    from fastapi.testclient import TestClient

    from app.core.api_access import apply_default_deny
    from app.core.database import engine as app_engine

    user_id = _seed_app_engine_user("gate")
    headers = {"authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}

    app = _naked_probe_router()
    apply_default_deny(app.routes)
    client = TestClient(app)
    status, guarded_selects = _count_user_selects(
        app_engine, lambda: client.get("/organizations/forgot-me", headers=headers).status_code
    )
    assert status == 200, f"带着有效 token 还被拦：{status}"
    assert guarded_selects == 1, f"补齐的守护每请求解析了 {guarded_selects} 次用户，应该是 1 次"

    # 对照组：同一条件不过这一趟，没人查用户 → 必须是 0 条，否则上面那个 1 说不清是谁发的。
    control = TestClient(_naked_probe_router())
    status, plain_selects = _count_user_selects(
        app_engine, lambda: control.get("/organizations/forgot-me", headers=headers).status_code
    )
    assert status == 200 and plain_selects == 0, f"对照组应该是 200/0 条，实测 {status}/{plain_selects}"


def _path_to_regex(path: str):
    """把路由模板近似编译成正则（只处理本仓出现的 `{name}` 与 `{name:int}` 两种）。"""
    import re

    out = re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\:int\}", r"[0-9]+", path)
    out = re.sub(r"\{[^}]+\}", r"[^/]+", out)
    return re.compile("^" + out + "$")


def _first_matching_route(routes, method: str, full: str):
    return next((r for r in routes if method in (r.methods or set()) and _path_to_regex(r.path).match(full)), None)


def test_public_literal_paths_are_not_shadowed_by_dynamic_siblings():
    """`/jobs/cities` 这类字面路径必须在同前缀的动态路径**之前**被匹配到，
    否则守护拆分会把公开端点变成一条假 404/401。这里按 app 的真实路由顺序解析。"""
    from app.main import app as real_app

    ordered = [r for r in real_app.routes if getattr(r, "path", None) and getattr(r, "methods", None)]
    for method, path in sorted(PUBLIC_OPERATIONS):
        full = "/api" + path
        winner = _first_matching_route(ordered, method, full)
        assert winner is not None, f"{method} {full} 一条路由都匹配不到"
        # 先匹配到的必须正是它自己那条路由（`/organizations/sso/feishu/{slug}/start` 自身就带
        # 一个参数段，所以判据是"同一条路径"，不是"没有花括号"）。
        assert winner.path == full, f"{method} {full} 被 {winner.path} 抢先匹配，公开端点会被遮蔽"


def test_the_shadow_check_itself_has_teeth():
    """反方向：真造一个"动态路径在前、字面路径在后"的装配，上面那条判据必须报出遮蔽——
    不然"全部 winner.path == full"可能只是因为压根匹配不到东西。"""
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient

    probe = APIRouter()

    @probe.get("/jobs/{any_id}")
    def _dynamic(any_id: str):
        return {"shadowed": any_id}

    @probe.get("/jobs/cities")
    def _literal():
        return {"cities": []}

    app = FastAPI()
    app.include_router(probe)
    client = TestClient(app)
    ordered = [r for r in app.routes if getattr(r, "path", None) and getattr(r, "methods", None)]
    winner = _first_matching_route(ordered, "GET", "/jobs/cities")
    assert winner is not None and winner.path == "/jobs/{any_id}", "这个反例没构造成功：字面路径反而先匹配了"
    # 真实 HTTP 也确认它被遮蔽（证明这条判据测的是会发生的事，不是正则游戏的自洽）
    assert client.get("/jobs/cities").json() == {"shadowed": "cities"}
