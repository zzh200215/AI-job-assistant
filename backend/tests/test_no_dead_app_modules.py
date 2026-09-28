"""防复发守卫：`app/` 里不许再有"写了但没人 import"的模块（E21）。

这条债原本记的是"三个 `DeprecationWarning` 垫片层靠 import 维持存活"。实测之后两头都不准：
`agent_orchestrator.py` 与 `agent_workflow.py` 是 `/api/multi-agent`、`/api/agent` 在用的兼容入口
（**活的**），真正零引用的是另外六个模块——`app/services/smart_orchestrator.py`（80 行，
`run_orchestrator_sync` 无人调用，而两处"已废弃，请使用 …→ smart_orchestrator"的提示恰恰在指这个
死入口）、4 个 prompt 文本模块（210 行，`PROMPT_VERSION` 全仓无人读，`SummaryAgent` 实际用
`agent_report`）、以及 `app/utils/llm_output.py`（135 行，覆盖率 **0%**）。合计 425 行已删。

守卫从真实入口做静态 import 闭包。它成立有个前提：**没人动态 import app 模块**，所以第三条测试
钉住这点，否则这条断言不可信。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

# 真入口：app 自己，加上每个会被人运行的目录。tests 也算入口——"只有测试在用"的模块不算死，
# 但它必须真的被点名。
ROOT_GLOBS = ("tests/**/*.py", "scripts/**/*.py", "alembic/**/*.py")
EXPLICIT_ROOTS = {"app.main", "app.api.router"}

# 允许的"不可达"：模块名 -> 理由。**空表是目标**；新增一条就得写清为什么留着。
ALLOWED_UNREACHABLE: dict[str, str] = {}


def _module_name(path: Path, backend: Path) -> str:
    parts = list(path.relative_to(backend).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _referenced_names(path: Path, backend: Path) -> set[str]:
    """一条 import 引用的所有模块名，含 `from X import a` 里的 X 与 X.a。

    少展开 alias 会把 `app/api/router.py` 那 30 段 `from app.api import (agent, ...)` 判成整包
    不可达——第一版探针就是这么量出 84 个"死模块"的，全是假阳性。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()

    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:  # 相对 import 拼回绝对名
                own = _module_name(path, backend)
                stem = own.rsplit(".", node.level - 1)[0] if node.level > 1 else own
                base = f"{stem}.{base}" if base and stem else (stem or base)
            if base:
                out.add(base)
            out.update(f"{base}.{alias.name}" for alias in node.names if base and alias.name != "*")
    return out


def _split_reachable(backend: Path) -> tuple[set[str], set[str]]:
    module_edges: dict[str, set[str]] = {}
    for path in sorted(backend.rglob("*.py")):
        if ".venv" in path.parts or "node_modules" in path.parts:
            continue
        module_edges.setdefault(_module_name(path, backend), set()).update(_referenced_names(path, backend))

    app_dir = backend / "app"
    if not app_dir.exists():
        return set(), set()
    packages = {_module_name(p, backend) for p in app_dir.rglob("__init__.py")}
    tracked = {_module_name(p, backend) for p in app_dir.rglob("*.py")} - packages - {"app", "app.main"}

    seeds = set(EXPLICIT_ROOTS)
    for pattern in ROOT_GLOBS:
        seeds.update(_module_name(p, backend) for p in backend.glob(pattern))

    seen: set[str] = set()
    queue = list(seeds)
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        queue.extend(module_edges.get(name, set()))

    return tracked & seen, tracked - seen


def test_the_reachability_walk_actually_fires():
    """反方向：造一棵合成树，死模块必须被点名——否则下面的"零不可达"是空的。"""
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        backend = Path(raw)
        (backend / "app").mkdir()
        (backend / "tests").mkdir()
        (backend / "app" / "__init__.py").write_text("", encoding="utf-8")
        (backend / "app" / "main.py").write_text("from app import live\n", encoding="utf-8")
        (backend / "app" / "live.py").write_text("X = 1\n", encoding="utf-8")
        (backend / "app" / "dead.py").write_text("Y = 2\n", encoding="utf-8")
        (backend / "tests" / "test_anything.py").write_text("from app.live import X\n", encoding="utf-8")

        reachable, unreachable = _split_reachable(backend)

    assert reachable == {"app.live"}, f"可达集合不对：{reachable}"
    assert unreachable == {"app.dead"}, f"死模块没被点名：{unreachable}"


def test_no_unreachable_module_lurks_in_app():
    reachable, unreachable = _split_reachable(BACKEND)
    # 非空断言：遍历失效会让"零不可达"变成假绿，所以先要求它认得出绝大多数模块。
    assert len(reachable) >= 180, f"只认到 {len(reachable)} 个可达模块，闭包遍历大概断了"
    unexpected = sorted(unreachable - set(ALLOWED_UNREACHABLE))
    assert not unexpected, f"这些 app 模块没人 import，要么接上要么删掉：{unexpected}"


def test_allowed_exceptions_are_all_still_unreachable():
    """allowlist 是空的（这正是本次要钉的状态）；将来留条目就必须说明它确实还不可达。"""
    _, unreachable = _split_reachable(BACKEND)
    stale = sorted(name for name in ALLOWED_UNREACHABLE if name not in unreachable)
    assert not stale, f"这些模块已经可达了，把 allowlist 条目删掉：{stale}"


def test_no_dynamic_import_of_app_modules():
    """闭包断言的前提：没人用 `import_module`/`__import__` 动态拉 app 模块。

    `app/utils/file_parser.py` 里的 `import_module` 只取可选第三方模块（pytesseract 等），
    那是刻意的软依赖，不在这条射程里。
    """
    pattern = re.compile(r"""(?:import_module|__import__)\s*\(\s*f?["']app\.""")
    hits = [
        str(path.relative_to(BACKEND))
        for path in sorted((BACKEND / "app").rglob("*.py"))
        if pattern.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert not hits, f"动态 import 会让可达性判断失真，先处理掉：{hits}"
