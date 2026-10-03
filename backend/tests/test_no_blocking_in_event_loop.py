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
    # 仓内自己的**慢 helper**（E25 补）：这一层 E15 那把尺子看不见，因为它只认原语。
    # 漏掉的四个站点当时就是这么活下来的 —— `spider.search` 里面确实是 requests + `time.sleep`，
    # 但尺子扫的是调用点的名字，不会下钻到 helper 体内。
    "spider.search",
    "spider.demo",
    "spider.fetch_detail",
    "knowledge_service.save_and_process",
    "resume_export_service.export_pdf",
    "resume_export_service.export_docx",
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
        parts = name.split(".")
        head = parts[0]
        # 只认 `router.` / `ws.` 会漏掉整段 `admin_router`、`external_router` 上的路由 ——
        # `api/tenant.py` 那条阻塞的入库就是靠这个盲区活到 E25 的。
        head_ok = head in {"router", "ws"} or head.endswith("_router")
        if head_ok and (len(parts) == 1 or parts[1] in HTTP_VERBS):
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
    assert violations == [], (
        "在 async 路由里发现同步出网/慢 CPU 调用，改成 await run_in_threadpool(...)：\n" + "\n".join(violations)
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


helper_src_blocking = """
from app.api import knowledge
from fastapi import APIRouter
router = APIRouter()

@router.post("/x")
async def bad_helper_route(db, raw):
    return knowledge_service.save_and_process(db, raw)
"""

helper_src_threadpool = """
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
router = APIRouter()

@router.post("/x")
async def good_helper_route(db, raw):
    return await run_in_threadpool(knowledge_service.save_and_process, db, raw)
"""


def test_guard_fires_on_a_real_violation():
    """反方向自证：把违规写回来看得见吗。看不见的话，上面那条"全绿"没有意义。"""
    hits = violations_in_source(async_src_blocking, "bad.py")
    assert len(hits) == 1 and "requests.get" in hits[0], hits


def test_guard_fires_on_a_slow_project_helper():
    """E25 新补的那一层也要自证：只列名字不咬人等于没列。"""
    hits = violations_in_source(helper_src_blocking, "bad_helper.py")
    assert len(hits) == 1 and "knowledge_service.save_and_process" in hits[0], hits


@pytest.mark.parametrize(
    "src, label",
    [
        (async_src_threadpool, "线程池写法"),
        (sync_src_route, "sync def 路由（FastAPI 自己丢线程池）"),
        (helper_src_threadpool, "helper 的线程池写法"),
    ],
)
def test_guard_passes_the_correct_forms(src, label):
    assert violations_in_source(src, "ok.py") == [], label


def test_guard_blind_spots_are_pinned():
    """两处看不见：传递阻塞与内联闭包。写成测试而不是注释，是为了让限制随代码一起被读到。

    改注（A5）：下面第 1 条"传递阻塞"已由 `test_indirect_blocking_matches_the_allowlist` 接管，
    这把尺子仍然看不见它——保留这条断言是为了说清**每把尺子各自的边界**，而不是说全仓没人管。"""
    assert violations_in_source(transitive_src, "t.py") == []
    assert violations_in_source(closure_src, "c.py") == []


# ---- A5：把上面那条"看不见 #1（传递阻塞）"换成一把真的能咬人的尺子 ----
"""E25 那把尺子只认调用点写了什么名字，所以 `analyze_resume(db, ...)` 这种"路由里调仓内的 sync
函数、出网发生在那个函数体内"的形状按定义看不见。A5 做的是**传递闭包**：从每条 async 路由的调用点
出发，顺着仓内函数定义往下走，直到命中阻塞原语。

口径（有意取**上界**，宁可多报不少报）：
  * 原语集合 = 上面那两张表 + 几类同步重活（PDF 渲染、向量库读写、httpx）；
  * 只解析 `import a.b [as c]` 与 `from a.b import c [as d]`；动态 getattr 与字符串路由看不见；
  * `run_in_threadpool(slow, ...):` 里的 `slow` 出现在**参数**位置而不是 `Call.func`，所以
    E15/E25 修过的那 6 个文件（job_search / knowledge / organization / resume / system / tenant）
    在这里一条都不出现——这是口径正确，不是漏扫，由
    `test_indirect_scan_passes_the_threadpool_form` 钉住；
  * 函数按**限定名**（模块.名）索引，不按短名合并：按短名会把某个模块里阻塞的 `_run` 算到所有
    同名函数头上。这一轮两种口径都跑过，结果同为 23 条、差集为空。

清单只能往下走：新增一条就要先把那条路由挪进线程池，删一条要同时把名字从表里去掉。"""

TRANSITIVE_PRIMITIVES = set(BLOCKING_DOTTED) | {
    "httpx.get",
    "httpx.post",
    "httpx.Client",
    "requests.Session",
}
# 不加"裸名 add/query"这一类：`seen.add(x)` 与 `collection.add(...)` 在 AST 上只差一个点号，
# 按裸名匹配会把集合操作判成向量库写入。真要管 Chroma，就按 `xxx.add(...)` 的点号名逐个列。


class _Fn:
    __slots__ = ("qname", "module", "calls", "blocks", "is_route")

    def __init__(self, qname: str):
        self.qname = qname
        self.module = qname.rsplit(".", 1)[0]
        self.calls: list[str] = []
        self.blocks = False
        self.is_route = False


def _module_of(path: pathlib.Path, root: pathlib.Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = [p for p in rel.parts if p != "__init__"]
    return "app." + ".".join(parts) if parts else "app"


def _build_graph(root: pathlib.Path) -> tuple[dict[str, _Fn], dict[str, dict[str, str]]]:
    """扫给定 app/ 目录，返回 {限定名 -> 函数} 与 {模块 -> {本地名 -> 目标点号名}}"""
    funcs: dict[str, _Fn] = {}
    imports: dict[str, dict[str, str]] = {}
    for path in sorted(root.rglob("*.py")):
        mod = _module_of(path, root)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imps = imports.setdefault(mod, {})
        parts = mod.split(".")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imps[a.asname or a.name.split(".")[0]] = a.name
            elif isinstance(node, ast.ImportFrom):
                # `from a.b import c` → a.b.c；`from .x import c`（在 app.api.resume 里）→ app.api.x.c
                pkg = ".".join(parts[: len(parts) - node.level]) if node.level else ""
                base = node.module if not node.level else ".".join(p for p in (pkg, node.module) if p)
                for a in node.names:
                    imps[a.asname or a.name] = f"{base}.{a.name}" if base else a.name

        def walk(body, prefix: str, module: str) -> None:
            for n in body:
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                    fn = _Fn(f"{module}.{prefix}{n.name}")
                    fn.is_route = any(
                        (_dotted(d.func) if isinstance(d, ast.Call) else _dotted(d)).split(".")[-1] in HTTP_VERBS
                        for d in n.decorator_list
                    )
                    for call in ast.walk(n):
                        if not isinstance(call, ast.Call):
                            continue
                        name = _dotted(call.func)
                        last = name.split(".")[-1]
                        if name in TRANSITIVE_PRIMITIVES or last in BLOCKING_NAMES:
                            fn.blocks = True
                        if name:
                            fn.calls.append(name)
                    funcs[fn.qname] = fn
                    walk(n.body, prefix, module)
                elif isinstance(n, ast.ClassDef):
                    walk(n.body, f"{prefix}{n.name}.", module)

        walk(tree.body, "", mod)
    return funcs, imports


def _resolve(funcs, imports, module: str, callee: str) -> str | None:
    imps = imports.get(module, {})
    head, _, tail = callee.partition(".")
    if not tail:  # 裸名：同模块函数优先，其次 `from x import fn`
        if f"{module}.{head}" in funcs:
            return f"{module}.{head}"
        for name, target in imps.items():
            if name == head and target in funcs:
                return target
        return None
    base = imps.get(head, f"{module}.{head}")
    cand = f"{base}.{tail}" if not base.startswith(f"{module}.") else f"{base}.{tail}"
    return cand if cand in funcs else None


def indirect_offenders(root: pathlib.Path = APP_ROOT) -> tuple[set[str], int]:
    """返回（间接走到阻塞原语的 async 路由限定名，扫到的 async 路由条数）。"""
    funcs, imports = _build_graph(root)
    memo: dict[str, bool] = {}

    def blocks(qname: str, depth: int = 0) -> bool:
        if qname in memo:
            return memo[qname]
        if depth > 12 or qname not in funcs:  # 递归环与超深由步数上限兜住
            return False
        fn = funcs[qname]
        if fn.blocks:
            memo[qname] = True
            return True
        out = False
        for callee in fn.calls:
            nxt = _resolve(funcs, imports, fn.module, callee)
            if nxt and blocks(nxt, depth + 1):
                out = True
                break
        memo[qname] = out
        return out

    routes = [fn for fn in funcs.values() if fn.is_route]
    hits = set()
    for fn in routes:
        # 直接命中的那类归上面那把尺子管，这里只报"要往下钻才看得见"的
        if any(c.split(".")[-1] in BLOCKING_NAMES or c in BLOCKING_DOTTED for c in fn.calls):
            continue
        for callee in fn.calls:
            nxt = _resolve(funcs, imports, fn.module, callee)
            if nxt and blocks(nxt):
                hits.add(fn.qname)
                break
    return hits, len(routes)


# A5 量出来的现状：22 条 async 路由在事件循环里**间接**做同步出网/重活。
# 每一条的正主与两处口径修正写在 §8 那行的记录里（D46）；这份清单只许往下走。
# 曾有第三条规则"裸调用 add/query/write_pdf 也算重活"，它会把 `seen.add(x)` 判成向量库写入
# （`career_path.recommend_career_paths → derive_directions` 就是这样被误报成阻塞的——那个函数
# 只有 DB 查询与纯计算），所以**不要**把它加回来。
INDIRECT_BLOCKING_ALLOWLIST = {
    "app.api.analysis.full_match",
    "app.api.analysis.get_record_references",
    "app.api.analysis.regen_interview",
    "app.api.analysis.regen_optimize",
    "app.api.external.capabilities.external_interview_simulate",
    "app.api.external.capabilities.external_match_evaluate",
    "app.api.external.capabilities.external_resume_parse",
    "app.api.jd.batch_import_jds",
    "app.api.jd.import_jd_from_url",
    "app.api.jd.parse_jd",
    "app.api.job_recommend.apply_feedback_tuning",
    "app.api.job_recommend.compare_recommend_config",
    "app.api.job_recommend.export_feedback_tuning_samples",
    "app.api.job_recommend.feedback_evaluation",
    "app.api.job_recommend.feedback_tuning_samples",
    "app.api.resume.analyze_resume_api",
    "app.api.resume.diagnose_resume",
    "app.api.resume.generate_optimized_resume",
    "app.api.resume.parse_resume",
    "app.api.resume.rewrite_suggestions",
    "app.api.resume.tailor_resume",
    "app.api.tenant.import_tenant_jobs",
}


def test_indirect_blocking_matches_the_allowlist():
    """新增一条就红；把某条挪进线程池之后，也要同时从表里删掉，否则"表比现实松"同样红。"""
    hits, routes = indirect_offenders()
    assert hits == INDIRECT_BLOCKING_ALLOWLIST, (
        f"多出来（新的间接阻塞，改成 await run_in_threadpool(...)）："
        f"{sorted(hits - INDIRECT_BLOCKING_ALLOWLIST)}；"
        f"少了（已修，请把这些名字从表里删掉）："
        f"{sorted(INDIRECT_BLOCKING_ALLOWLIST - hits)}"
    )


def test_indirect_scan_is_not_vacuous():
    """和上面那条一样要有防空转：真的扫到了路由，而不是解析失败换来的"全绿"。"""
    _, routes = indirect_offenders()
    assert routes >= 200, f"只扫到 {routes} 条 async 路由，多半是判据失效了"


def _snippet_app(tmp_path, src: str) -> pathlib.Path:
    """把合成源码摆成一个临时 app/ 目录，让同一套解析逻辑跑在它身上。"""
    base = pathlib.Path(tmp_path) / "app"
    base.mkdir(parents=True, exist_ok=True)
    (base / "x.py").write_text(textwrap.dedent(src), encoding="utf-8")
    return base


def test_indirect_scan_fires_on_the_transitive_case_the_direct_guard_misses(tmp_path):
    """正面自证：`test_guard_blind_spots_are_pinned` 里那个例子，这把尺子要看得见。"""
    hits, routes = indirect_offenders(_snippet_app(tmp_path, transitive_src))
    assert hits == {"app.x.transitive_route"}, hits
    assert routes == 1, routes


def test_indirect_scan_passes_the_threadpool_form(tmp_path):
    """反证：包进线程池就不该报——否则那 23 条里会混进 E15/E25 已经修好的那些。"""
    hits, _ = indirect_offenders(_snippet_app(tmp_path, async_src_threadpool))
    assert hits == set(), hits


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
    以前同步跑在事件循环里，一个匿名请求就能让别人的请求排队。

    D104 把阈值改成**跟着基线走**：同一条 /ready 在不注入 sleep 时先量一次，判据是
    `注入之后 < 基线 + stall/2`。原来那句 `elapsed < stall / 2` 把两件事混成了一个数——
    "事件循环被同步代码卡住"和"这台机器此刻 CPU 饥饿"。实测：空闲单跑 4.32s 绿，
    旁边并发一份前端全量（`npx vitest run`）就红，而红的这一条里 /ready 的行为什么都没变。
    改判据不降低分辨率：真卡住循环时 `注入之后 ≈ 基线 + stall`，照样越线。
    """
    import asyncio

    from app.main import app

    stall = 0.4

    class _FakeChroma:
        def __init__(self, delay: float = 0.0) -> None:
            self.delay = delay

        def heartbeat(self):
            if self.delay:
                import time

                time.sleep(self.delay)

    async def _measure(delay: float) -> float:
        monkeypatch.setattr("app.core.chroma_client.get_chroma_client", lambda: _FakeChroma(delay))
        import httpx
        from httpx import ASGITransport

        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            return await _latency_while_something_blocks(client, "/api/system/ready", "/api/system/health")

    async def _run():
        baseline = await _measure(0.0)
        blocked = await _measure(stall)
        return baseline, blocked

    baseline, blocked = asyncio.run(_run())
    assert blocked < baseline + stall / 2, (
        f"/health 被 /ready 停住了：注入 {stall}s 之后排队 {blocked:.3f}s，"
        f"同一条路径不注入时的基线是 {baseline:.3f}s（多出来的那 {blocked - baseline:.3f}s "
        f"就是事件循环被同步占着的时长；阈值随基线走，满载时不要把 CPU 饥饿读成回归）"
    )


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
