"""共享前缀下的路由遮蔽与重号是构造问题，不是顺序运气（E22）。

债行原话："`/jobs` 由三个 router 共享前缀，当前不冲突仅因 `job_recommend.py:1448` 的
`/{jd_id:int}` 是单段"。先把"当前不冲突"量成事实：`/jobs` 下 37 条路由，**0 组同号重复、
0 条字面路径被更靠前的动态路径遮蔽**。也就是说这行记的不是一个现存故障，而是一个**没人保证
下次也不出故障**的性质——谁在 `/jobs` 下新加一条 `/{section}` 就能安静地把三条字面路径吃掉。

所以这里不加"别加这种路由"的注释，加一条会响的尺子：作用在真实路由表上，并且用合成路由
反证它真的会响。
"""

from __future__ import annotations

import re
from collections import Counter

from fastapi import APIRouter, FastAPI

from app.api.router import api_router

_NON_OPERATIONS = {"HEAD", "OPTIONS"}


def _template_to_regex(template: str) -> re.Pattern[str]:
    """把路由模板近似编译成正则：`{x:int}` 只吃数字，其余 `{x}` 吃单段。"""
    out = re.sub(r"\{[a-zA-Z_][a-zA-Z0-9_]*:int\}", r"[0-9]+", template)
    out = re.sub(r"\{[^}]+\}", "[^/]+", out)
    return re.compile("^" + out + "$")


def _operating_routes(routes) -> list:
    return [r for r in routes if getattr(r, "methods", None) and getattr(r, "path", None)]


def duplicate_operations(routes) -> list[tuple[str, str]]:
    """同一个 (方法, 模板) 被两条路由注册——Starlette 只跑第一条，第二条安静地死掉。"""
    pairs: list[tuple[str, str]] = []
    for route in _operating_routes(routes):
        for method in sorted(set(route.methods) - _NON_OPERATIONS):
            pairs.append((method, route.path))
    return [(method, path) for (method, path), count in Counter(pairs).items() if count > 1]


def shadowed_literal_paths(routes) -> list[tuple[str, str]]:
    """字面路径被**注册得更早**的动态路径遮蔽（同方法才谈得上遮蔽）。"""
    operating = _operating_routes(routes)
    hits: list[tuple[str, str]] = []
    for index, literal in enumerate(operating):
        if "{" in literal.path:
            continue
        for earlier_index, dynamic in enumerate(operating):
            if earlier_index >= index or "{" not in dynamic.path:
                continue
            if not set(literal.methods) & set(dynamic.methods):
                continue
            if _template_to_regex(dynamic.path).match(literal.path):
                hits.append((literal.path, dynamic.path))
    return hits


def shared_prefixes(routes) -> dict[str, int]:
    """哪些一级前缀由不止一个来源注册（`/jobs` 是这条债的靶子，`/admin` 同形）。"""
    owners: dict[str, set[str]] = {}
    for route in _operating_routes(routes):
        prefix = "/" + route.path.lstrip("/").split("/")[0]
        owners.setdefault(prefix, set()).add(route.endpoint.__module__)
    return {prefix: len(modules) for prefix, modules in sorted(owners.items()) if len(modules) > 1}


def test_no_two_operations_share_the_same_method_and_template():
    # 非空断言：遍历真能看到几十条操作，否则这条"零重复"可能只是什么都没查到。
    operating = _operating_routes(api_router.routes)
    assert len(operating) >= 200, f"只遍历到 {len(operating)} 条带方法的路由，遍历大概失效了"
    assert duplicate_operations(api_router.routes) == []


def test_no_literal_path_under_a_shared_prefix_is_shadowed():
    # 这条是真实不变式；先确认作用域非空，否则"没有遮蔽"可能只是因为没东西可查。
    shared = shared_prefixes(api_router.routes)
    assert "/jobs" in shared, f"`/jobs` 不再由多来源注册了？现在共享前缀是 {shared}"
    assert shared["/jobs"] >= 3, f"`/jobs` 下的来源数与债行记的三个 router 不符：{shared['/jobs']}"
    assert shadowed_literal_paths(api_router.routes) == []


def test_the_shadow_check_actually_fires():
    """反方向：合成一个"动态路径在前、字面路径在后"的表，尺子必须响。"""
    router = APIRouter()

    @router.get("/sections/{name}")
    def _dynamic(name: str):
        return {"ok": True}

    @router.get("/sections/featured")
    def _literal():
        return {"ok": True}

    app = FastAPI()
    app.include_router(router, prefix="/jobs")

    assert shadowed_literal_paths(app.routes) == [("/jobs/sections/featured", "/jobs/sections/{name}")]
    # 对照组：顺序反过来就不算遮蔽（第一条匹配就是它自己），否则上面那条是恒真断言。
    reversed_router = APIRouter()

    @reversed_router.get("/sections/featured")
    def _literal_first():
        return {"ok": True}

    @reversed_router.get("/sections/{name}")
    def _dynamic_second(name: str):
        return {"ok": True}

    control = FastAPI()
    control.include_router(reversed_router, prefix="/jobs")
    assert shadowed_literal_paths(control.routes) == []


def test_a_duplicate_template_is_caught():
    """反方向：两个 router 在同一前缀下注册同一个 (方法, 路径) 时必须被点名。"""
    first = APIRouter()

    @first.get("/same")
    def _one():
        return {"ok": True}

    second = APIRouter()

    @second.get("/same")
    def _two():
        return {"ok": True}

    app = FastAPI()
    app.include_router(first, prefix="/jobs")
    app.include_router(second, prefix="/jobs")
    assert duplicate_operations(app.routes) == [("GET", "/jobs/same")]
