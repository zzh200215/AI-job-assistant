"""`api_error(...)` 的 message 是全仓唯一"原样上屏"的通道，钉两条静态判据（D16）。

`frontend/src/api/request.js` 的响应拦截器在 `code != 0` 时把 `body.message` 直接交给
`ElMessage.error`，并挂到 `userMessage` 上给视图复用——也就是说**接口里写进 message 的每个字，
候选人都会读到**。两类错误因此都不能出：

1. **英文技术句**：`api_error(404, "task not found")` 会原样变成一条英文 toast；
2. **异常原文**：`api_error(500, f"启动分析失败: {exc}")` 会把 provider 的
   `HTTP 429 / fallback 链路均未成功` 端到屏幕上（2026-11-16 真浏览器验收撞见同族问题）。

唯一放行的是 `str(exc)` 但**异常是我们自己的领域异常**（`OrchestrationUnavailable`）：
那句中文是我们自己写的，而且 503 的"没有活着的 worker"正是要给人看的门禁原因。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "app" / "api"

CJK = re.compile(r"[\u4e00-\u9fff]")
# 会被当成"异常原文"的变量名；`{exc}` 与 `{e}` 都在内
_EXC_NAMES = {"exc", "e", "err", "error", "exception"}
# `str(exc)` 只在这些 except 分支里放行：异常类型是我们自己的、文案是我们写的
ALLOWED_STR_EXC_IN = {"OrchestrationUnavailable"}


def _handler_spans(tree: ast.AST) -> list[tuple[int, int, set[str]]]:
    """每个 except 分支的（起行, 止行, 异常类型名集合）。"""
    spans: list[tuple[int, int, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            names: set[str] = set()
            if isinstance(handler.type, ast.Name):
                names.add(handler.type.id)
            elif isinstance(handler.type, ast.Tuple):
                names.update(elt.id for elt in handler.type.elts if isinstance(elt, ast.Name))
            if handler.body:
                spans.append((handler.body[0].lineno, handler.body[-1].end_lineno, names))
    return spans


def _except_types_at(spans, lineno: int) -> set[str]:
    """包住这一行的**最内层** except 分支的类型集合。"""
    inside = [span for span in spans if span[0] <= lineno <= span[1]]
    if not inside:
        return set()
    innermost = max(inside, key=lambda span: span[0])
    return innermost[2]


def _api_error_calls(path: Path) -> list[tuple[ast.Call, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    spans = _handler_spans(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name == "api_error":
            found.append((node, _except_types_at(spans, node.lineno)))
    return found


def _message_node(call: ast.Call) -> ast.expr | None:
    return call.args[1] if len(call.args) >= 2 else None


def _scan() -> tuple[list[str], int]:
    problems: list[str] = []
    checked = 0
    for path in sorted(API_DIR.rglob("*.py")):
        for call, except_types in _api_error_calls(path):
            node = _message_node(call)
            if node is None:
                problems.append(f"{path.name}:{call.lineno} api_error 没带 message")
                continue
            checked += 1
            where = f"{path.name}:{call.lineno}"

            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if not CJK.search(node.value):
                    problems.append(f"{where} 文案没有中文（会原样变成英文 toast）：{node.value!r}")
                continue

            if isinstance(node, ast.JoinedStr):
                for part in node.values:
                    if not isinstance(part, ast.FormattedValue):
                        continue
                    source = ast.unparse(part.value)
                    if any(re.search(rf"\b{name}\b", source) for name in _EXC_NAMES):
                        problems.append(f"{where} f-string 插了异常对象：{source}")
                continue

            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str":
                if except_types & ALLOWED_STR_EXC_IN:
                    continue
                problems.append(f"{where} str(exc) 来自 {except_types or '未知异常'}，不是我们自己的措辞")
                continue

            # 变量/查表（如校验文案表）由调用方保证，静态不管
    return problems, checked


def test_every_api_error_message_is_our_own_chinese_copy():
    problems, checked = _scan()
    assert checked >= 15, f"只扫到 {checked} 处 api_error，扫描器自己坏了（改过目录结构？）"
    assert problems == [], "这几处的 message 会原样上屏：\n" + "\n".join(problems)
