"""§10.15 的形状清点：`async def` 路由里，哪些拿着同步 db 会话、哪些**真的可以**改成 `def`。

为什么要把它写进仓库而不是每次临时搭：账上那个"179 条"是 D92 一次 ad hoc 统计出来的，从没被任何
工具钉着——下一次它一定又漂。而"改成 def"这一刀的可行子集**不等于**这 179 条：FastAPI 对 `def`
路由会自动丢进 anyio 线程池，但一个体内有 `await` 的函数改成 `def` 直接就是语法错误/行为崩坏。
所以这里分三桶报数：

    sync_session_async   拿着 `Depends(get_db)`（同步会话）的 async def 路由 —— 账上那条 179
    convertible          其中**体内没有任何 await/async for/async with** 的：可以安全改成 def
    awaits_something     其中体内有 await 的：这一刀动不了（要么逐处 run_in_threadpool，要么留着）

用法：PYTHONPATH=. python scripts/scan_blocking_route_shapes.py [--json]
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "app" / "api"
ROUTER_METHODS = {"get", "post", "put", "patch", "delete"}


def _is_get_db_default(node: ast.expr) -> bool:
    """匹配 `Depends(get_db)`；`Depends(…)` 里换别的依赖就不算这一族。"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Depends"
        and bool(node.args)
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "get_db"
    )


def _has_sync_session(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    defaults = list(fn.args.defaults) + [kw.value for kw in fn.args.kw_defaults if kw]
    return any(_is_get_db_default(d) for d in defaults)


class _AwaitFinder(ast.NodeVisitor):
    def __init__(self) -> None:
        self.found = False
        # 内嵌的 async def / async lambda 有自己的挂起点，不算这一层
        self._stack = 0

    def visit_Await(self, node: ast.Await) -> None:  # noqa: N802
        self.found = True

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:  # noqa: N802
        self.found = True

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:  # noqa: N802
        self.found = True

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        return


def _awaits(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    finder = _AwaitFinder()
    for stmt in fn.body:
        finder.visit(stmt)
    return finder.found


def _is_route(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ROUTER_METHODS:
            return True
    return False


def scan(root: Path = API_DIR) -> dict[str, dict[str, list[str]]]:
    buckets: dict[str, dict[str, list[str]]] = {}
    for file in sorted(root.glob("*.py")):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        sync_async: list[str] = []
        convertible: list[str] = []
        awaits: list[str] = []
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            if not _is_route(node) or not _has_sync_session(node):
                continue
            if not isinstance(node, ast.AsyncFunctionDef):
                continue  # 已经是 def：FastAPI 本来就丢线程池
            sync_async.append(node.name)
            if _awaits(node):
                awaits.append(node.name)
            else:
                convertible.append(node.name)
        if sync_async:
            buckets[file.name] = {
                "sync_session_async": sync_async,
                "convertible": convertible,
                "awaits_something": awaits,
            }
    return buckets


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    buckets = scan()
    totals = {
        "files": len(buckets),
        "sync_session_async": sum(len(v["sync_session_async"]) for v in buckets.values()),
        "convertible": sum(len(v["convertible"]) for v in buckets.values()),
        "awaits_something": sum(len(v["awaits_something"]) for v in buckets.values()),
    }
    if args.json:
        print(json.dumps({"totals": totals, "detail": buckets}, ensure_ascii=False, indent=1))
        return 0
    print(json.dumps(totals, ensure_ascii=False))
    for name, v in sorted(buckets.items(), key=lambda kv: -len(kv[1]["convertible"])):
        if v["convertible"]:
            print(f"  {name}: 可改 {len(v['convertible'])} / 同会话 async {len(v['sync_session_async'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
