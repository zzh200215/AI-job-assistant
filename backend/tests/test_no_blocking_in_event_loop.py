"""守卫：`async def` 路由不许在事件循环里直接做出网/慢 CPU 的同步调用。

为什么只查"直接调用"这一层：AST 看得见的是路由体内写了什么。把 `requests.post` 换成
`await run_in_threadpool(requests.post, ...)` 之后，那个函数名出现在**参数**位置而不是
`Call.func`，所以这个门天然放行——这正是要允许的写法。

它看不见的也写在这里，并且由测试钉住（`test_guard_blind_spots_are_pinned`），不留在注释里等
下一个人重新发现：
  1. 传递阻塞：路由 → 本文件的 sync 函数 / 别的服务模块 → requests。看不见。
  2. 路由体内定义的 sync 闭包：`await run_in_threadpool(_closure)` 是对的，直接 `_closure()`
     也看不见——因为这两种写法在 AST 上无法区分（后者要追到调用点）。
所以这个门的定位是"**别在 `async def` 里新写一次同步出网**"，不是"证明全仓无阻塞"。
"""

from __future__ import annotations

import ast
import pathlib
import textwrap
from time import perf_counter

import pytest

APP_ROOT = pathlib.Path(__file__).resolve().parents[1] / "app"

# 整串点号名匹配。按短名匹配会把 `cache.get(...)` 当成 `requests.get` —— 第一版的量具就是这么错的。
BLOCKING_DOTTED = {
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.patch",
    "requests.delete",
    "requests.request",
    "requests.head",
    "requests.options",
    "time.sleep",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_output",
    "subprocess.Popen",
    "os.system",
    "os.popen",
    "engine.connect",
}
# 仓内自己的同步 provider 入口（都在 `app/services/*` 里用 requests 实现）
BLOCKING_NAMES = {
    "chat_json",
    "chat_text",
    "chat_with_tools",
    "embed_text",
    "embed_texts",
    "rerank",
}
HTTP_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "api_route", "websocket"}


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_route(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in fn.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        name = _dotted(target)
        head = name.split(".")[0]
        if head in {"router", "ws"} and (len(name.split(".")) == 1 or name.split(".")[1] in HTTP_VERBS):
            return True
    return False


def _calls_inside_route_body(fn: ast.AST) -> list[ast.Call]:
    """路由体内的调用；**不下钻**内层定义的 sync 函数（那是线程池写法的样子，见模块 docstring）。"""
    found: list[ast.Call] = []
    stack: list[ast.AST] = [fn]
    while stack:
        node = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef):
                continue
            if isinstance(child, ast.AsyncFunctionDef):
                continue
            if isinstance(child, ast.Call):
                found.append(child)
            stack.append(child)
    return found


def violations_in_source(src: str, filename: str = "<src>") -> list[str]:
    out: list[str] = []
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or not _is_route(node):
            continue
        for call in _calls_inside_route_body(node):
            name = _dotted(call.func)
            last = name.split(".")[-1]
            if name in BLOCKING_DOTTED or (last in BLOCKING_NAMES and "." not in name):
                out.append(f"{filename}:{call.lineno} {node.name} -> {name}")
    return out


def _scan_app() -> tuple[list[str], int]:
    violations: list[str] = []
    routes = 0
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and _is_route(node):
                routes += 1
                for call in _calls_inside_route_body(node):
                    name = _dotted(call.func)
                    last = name.split(".")[-1]
                    if name in BLOCKING_DOTTED or (last in BLOCKING_NAMES and "." not in name):
                        violations.append(f"{path.relative_to(APP_ROOT)}:{call.lineno} {node.name} -> {name}")
    return violations, routes


def test_no_async_route_calls_a_blocking_primitive_directly():
    """E15 之后的账：**空清单**。新增一条就要先想清楚为什么不能挪进线程池。"""
    violations, routes = _scan_app()
    assert violations == [], "在 async 路由里发现同步出网/慢 CPU 调用，改成 await run_in_threadpool(...)：\n" + "\n".join(
        violations
    )


def test_the_scan_actually_looked_at_the_routes():
    """防空转：真的遍历到了路由，而不是因为匹配不上而"全绿"。"""
    _, routes = _scan_app()
    assert routes >= 150, f"只扫到 {routes} 条 async 路由，多半是判据失效了"


async_src_blocking = """
import requests
from fastapi import APIRouter
router = APIRouter()

@router.get("/x")
async def bad_route():
    return requests.get("https://example.invalid").status_code
"""

async_src_threadpool = """
import requests
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
router = APIRouter()

@router.get("/x")
async def good_route():
    return await run_in_threadpool(requests.get, "https://example.invalid")
"""

sync_src_route = """
import requests
from fastapi import APIRouter
router = APIRouter()

@router.get("/x")
def threadpool_route():
    return requests.get("https://example.invalid")
"""

transitive_src = """
import requests
from fastapi import APIRouter
router = APIRouter()

def _service():
    return requests.get("https://example.invalid")

@router.get("/x")
async def transitive_route():
    return _service()
"""

closure_src = """
import requests
from fastapi import APIRouter
router = APIRouter()

@router.get("/x")
async def closure_route():
    def _inner():
        return requests.get("https://example.invalid")

    return _inner()
"""


def test_guard_fires_on_a_real_violation():
    """反方向自证：把违规写回来看得见吗。看不见的话，上面那条"全绿"没有意义。"""
    hits = violations_in_source(async_src_blocking, "bad.py")
    assert len(hits) == 1 and "requests.get" in hits[0], hits


@pytest.mark.parametrize(
    "src, label",
    [
        (async_src_threadpool, "线程池写法"),
        (sync_src_route, "sync def 路由（FastAPI 自己丢线程池）"),
    ],
)
def test_guard_passes_the_correct_forms(src, label):
    assert violations_in_source(src, "ok.py") == [], label


def test_guard_blind_spots_are_pinned():
    """两处看不见：传递阻塞与内联闭包。写成测试而不是注释，是为了让限制随代码一起被读到。"""
    assert violations_in_source(transitive_src, "t.py") == []
    assert violations_in_source(closure_src, "c.py") == []


async def _latency_while_something_blocks(client, slow_path: str, fast_path: str) -> float:
    """快请求的排队时间。计时窗口必须从"两个请求都还没跑"开始。

    前两版都测错了，值得记下来：
      * 只 `ensure_future(slow)` 再 `await fast`：fast 的 handler 全程没有挂起点，它先跑完，
        量到 0.0004s；
      * 中间加一次 `asyncio.sleep(0.05)` 让 slow 先进 sleep：于是**阻塞整个循环的那 0.4 秒
        被算进我的 settle 里**，started 取在阻塞结束之后，fast 又变成 0。
    被同步代码卡住的协程根本还没开始执行，所以从它自己的起点量不出等待——只能从"两个请求
    都发出去"的那一刻量到"快请求拿到响应"。
    """
    import asyncio

    started = perf_counter()
    slow = asyncio.ensure_future(client.get(slow_path))
    fast = asyncio.ensure_future(client.get(fast_path))
    await asyncio.sleep(0)  # 让 slow 先被调度，才有机会去卡住循环
    response = await fast
    elapsed = perf_counter() - started
    await slow
    assert response.status_code == 200
    return elapsed


def test_readiness_probe_does_not_stall_the_loop(monkeypatch):
    """行为证据（这条在改动前是红的）：/ready 是公开端点，它要做的 DB + Chroma 往返
    以前同步跑在事件循环里，一个匿名请求就能让别人的请求排队。"""
    import asyncio

    from app.main import app

    stall = 0.4

    class _FakeChroma:
        def heartbeat(self):
            import time

            time.sleep(stall)

    monkeypatch.setattr("app.core.chroma_client.get_chroma_client", lambda: _FakeChroma())

    async def _run():
        import httpx
        from httpx import ASGITransport

        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            return await _latency_while_something_blocks(client, "/api/system/ready", "/api/system/health")

    elapsed = asyncio.run(_run())
    assert elapsed < stall / 2, f"/health 被 /ready 停住了 {elapsed:.3f}s，事件循环还在被同步占着"


def test_the_stall_measurement_can_see_a_stall():
    """同一把尺子的反方向：把 `async def + time.sleep` 这个形状装回去，必须量出停摆。"""
    import asyncio

    from fastapi import FastAPI
    from fastapi.concurrency import run_in_threadpool

    stall = 0.4
    app = FastAPI()

    def _sleep():
        import time

        time.sleep(stall)
        return {"slept": stall}

    @app.get("/slow-off-loop")
    async def slow_off_loop():
        return await run_in_threadpool(_sleep)

    @app.get("/slow-on-loop")
    async def slow_on_loop():
        return _sleep()

    @app.get("/fast")
    async def fast():
        return {"ok": True}

    async def _measure(path):
        import httpx
        from httpx import ASGITransport

        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            return await _latency_while_something_blocks(client, path, "/fast")

    on_loop = asyncio.run(_measure("/slow-on-loop"))
    off_loop = asyncio.run(_measure("/slow-off-loop"))
    assert on_loop >= stall * 0.6, f"直接 sleep 都没让 /fast 排队（{on_loop:.3f}s），这把尺子是空的"
    assert off_loop < stall / 2, f"挪进线程池之后仍然停摆 {off_loop:.3f}s"
