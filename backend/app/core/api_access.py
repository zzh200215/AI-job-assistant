"""`/api` 的默认拒绝（E11 末段）：装配期补齐会话依赖，不是请求期拦截。

以前"整段前缀挂会话依赖"只能盖住 22 段纯会话前缀；剩下 8 段里混着公开端点，按路径挂守护会
把 `GET /jobs/cities`（登录页要用）一起关死。这里改成对**每条操作**判定：

    一条操作要么出现在下面两张清单里，要么它的依赖树里必须有会话凭据——没有第三种。

于是"新增一条端点忘了写凭据"从"对公网开放"变成"出生就 401"，且不区分前缀。清单本身由
tests/test_public_api_surface.py 与那条遍历逐条比对，两边都要改才能扩大公开面。

为什么是"补齐"而不是"请求期直接调 `get_current_user`"：那扇门实测每次带凭据请求在 `tb_user`
上发**两条** SELECT——它不在 FastAPI 的依赖树上，进不去端点那个 session 的 identity map，而它的
`Depends(get_db)` 和端点的是两条独立 session（include 级 `Depends(get_current_user)` 会被合并成
一条，实测是 1 条）。所以这里只在"树里没有任何会话凭据"时补一条，每条受守护的请求仍然是**一次**
解析、**一条** SELECT，代价与今天完全相同。
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.dependencies.utils import get_parameterless_sub_dependant

from app.api.auth import get_current_user

# 故意无凭据可调：登录/注册/找回、探活、登录页要用的静态字典与品牌、SSO 与支付回调
# （那两条由 state / 渠道签名自证）。路径写全 `/api/...`，与请求侧看到的一致。
ANONYMOUS_OPERATIONS = {
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/reset-password"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/verify-email"),
    ("POST", "/api/auth/reset-password-with-token"),
    ("GET", "/api/system/health"),
    ("GET", "/api/system/ready"),
    # 2026-10-06 真删企业侧（D134）：/api/tenant/brand 与两条飞书 SSO 随 organization/tenant 两个 router 出树，
    ("GET", "/api/jobs/cities"),
    # 清单里删掉三条 = 少三个"匿名可达"的入口；剩下这套构造保证的形状一字未动。
    ("GET", "/api/interview/config/types"),
    ("GET", "/api/subscription/plans"),
    ("POST", "/api/subscription/pay-callback"),
}

# 不要求会话，但**自带另一种凭据**的操作：`require_metrics_reader`（管理员会话或静态采集令牌）
# 与外部能力 API 的 `X-API-Key`。这两类由端点自己校验，装配期不另加会话依赖——加上去就会把
# X-API-Key 那条通道关成 401。
OTHER_CREDENTIAL_OPERATIONS = {
    ("GET", "/api/system/metrics"),
    ("POST", "/api/v1/external/resume/parse"),
    ("POST", "/api/v1/external/match/evaluate"),
    ("POST", "/api/v1/external/interview/simulate"),
}

NEVER_SESSION_GUARDED = ANONYMOUS_OPERATIONS | OTHER_CREDENTIAL_OPERATIONS

# HEAD/OPTIONS 不是业务操作（HEAD 是 GET 的副产物，OPTIONS 是 CORS 预检）。
_NON_OPERATIONS = {"HEAD", "OPTIONS"}


def _has_session_credential(dependant, seen: set[int]) -> bool:
    """依赖树里是否已经有一条会话凭据（含 `require_admin` 这类内部直接调用的情况）。"""
    call = getattr(dependant, "call", None)
    if call is get_current_user:
        return True
    for sub in getattr(dependant, "dependencies", []) or []:
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        if _has_session_credential(sub, seen):
            return True
    return False


def apply_default_deny(routes) -> list[str]:
    """给清单外、且自己没写会话凭据的每条操作补上 `Depends(get_current_user)`。

    返回被补的 `METHOD path` 列表（今天真实 router 上应该是空的——所有非公开操作都已经各自写了
    凭据，这一趟纯是防以后漏写）。返回空不等于这趟是空转，`tests/` 里用一条裸端点钉住它的效果。
    """
    guarded: list[str] = []
    for route in routes:
        methods = set(getattr(route, "methods", None) or ()) - _NON_OPERATIONS
        if not methods or getattr(route, "dependant", None) is None:
            continue  # WebSocketRoute / Mount：WS 走自己的凭据通道（E16）
        raw_path = getattr(route, "path", "")
        if raw_path.startswith("/api"):
            # 清单里的键是 `/api/...`，而这一趟作用在**挂到 /api 之前**的 api_router 上（那里
            # 的路径还没有 /api）。对着已展开的 app.routes 调用会让清单永远匹配不上，公开端点
            # 被静默关死——所以直接把这种误用炸掉，而不是让它悄悄通过。
            raise ValueError(f"apply_default_deny 要作用在挂载前的路由表上，看到的却是已带 /api 的 {raw_path}")
        path = f"/api{raw_path}"
        operations = {(method, path) for method in methods}
        if operations & NEVER_SESSION_GUARDED:
            if operations - NEVER_SESSION_GUARDED:
                # 同一个装饰器上公开与受守护的方法混在一起时，补依赖会把公开那个一起关死，
                # 而且这种混法没人看得出来——直接炸在装配期。
                raise ValueError(f"{path} 的同一个路由对象上混了公开与需要凭据的方法：{sorted(operations)}")
            continue
        if _has_session_credential(route.dependant, set()):
            continue
        dependency = Depends(get_current_user)
        # 两份都要写：`.dependencies` 是给读依赖清单的人/测试，`.dependant.dependencies` 才是
        # FastAPI 请求期真正走的那棵树（它在构造时就编译好了，只改前者不会生效）。
        route.dependencies.append(dependency)
        route.dependant.dependencies.append(get_parameterless_sub_dependant(depends=dependency, path=route.path_format))
        guarded.extend(f"{method} {path}" for method in sorted(methods))
    return guarded
