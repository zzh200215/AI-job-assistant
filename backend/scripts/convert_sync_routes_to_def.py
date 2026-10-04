"""§10.15 的一次性转换：把"拿着同步 db 会话、体内没有任何 await"的路由从 `async def` 改成 `def`。

判据来自 `scan_blocking_route_shapes.py`（先扫再转，两边共用同一份 AST 判据）：
`async def` 体内没有 `await` / `async for` / `async with` 时，这个函数在事件循环里**只是**在跑同步
SQLAlchemy —— 而 FastAPI 对 `def` 路由会自动丢进 anyio 线程池，于是循环不再被会话占用。
体内有 await 的那 12 条**不动**（改成 def 就是坏代码）。

每文件都断言"改掉的条数 == 计划条数"，并按名字重新解析确认函数还在、签名确实变成 def——
这类批量改写最容易的是把某条函数名写错或漏掉，报一个"看起来全绿"的结果。
"""

from __future__ import annotations

import ast
import re
import sys

from scripts.scan_blocking_route_shapes import API_DIR, scan


def main() -> int:
    dry = "--apply" not in sys.argv
    buckets = scan()
    total_changed = 0
    for fname, info in sorted(buckets.items()):
        plan = info["convertible"]
        if not plan:
            continue
        path = API_DIR / fname
        source = path.read_text(encoding="utf-8")
        lines = source.split("\n")
        changed: list[str] = []
        for name in plan:
            pattern = re.compile(rf"^async def {re.escape(name)}\(")
            hit = [i for i, line in enumerate(lines) if pattern.match(line)]
            if len(hit) != 1:
                raise SystemExit(f"{fname}: {name} 在顶层匹配到 {len(hit)} 处，计划是 1 处——停，不猜")
            lines[hit[0]] = lines[hit[0]][len("async ") :]
            changed.append(name)
        assert len(changed) == len(plan), f"{fname}: 计划 {len(plan)} 条，实际改了 {len(changed)} 条"
        new_source = "\n".join(lines)
        tree = ast.parse(new_source)
        still_def = {node.name for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in set(plan)}
        missing = set(plan) - still_def
        assert not missing, f"{fname}: 这些函数改写后不再是同步 def：{sorted(missing)}"
        total_changed += len(changed)
        print(f"{'[dry] ' if dry else ''}{fname}: {len(changed)} 条 async def -> def")
        if not dry:
            path.write_text(new_source, encoding="utf-8", newline="\n")
    print(f"合计 {total_changed} 条；剩余带 await 的同会话 async 路由见 scan_blocking_route_shapes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
