"""没有任何乱码：会被打印/返回给用户的中文字符串，不能是"按 GBK 读回后另存"的产物。

判据不靠手写坏字清单，也不要求能完整复原（有些串已经吞掉字节，复原不出来）：只要有**一段 3 字的
CJK 连续窗口**里连一个高频字（字频基准里出现 >=5 次）都没有，就不可能是人写的句子。

为什么只扫**字符串字面量**（ast 取），不扫整行：整行口径的误报全部落在注释里——实测 519 个
文本文件中，"撞车干扰""回落默认租户"这类正常中文注释被误判为乱码。字面量才是会到用户眼前的
东西，换成 ast 字面量后这些误报为 0。

已知边界（说明，不是遗漏）：
① 串里恰好混进一个高频字时看不见（如 `鐩镐技搴` 的"技"）。试过加"罕见字占比 >=60%"来补，
   结果误伤正常词"熟练掌握"，放弃。
② `.md` 文档不在覆盖面内：散文里生僻字连排是合法的（实测 2 处误报），而文档乱码不会到候选人眼前。
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND_SRC = BACKEND.parent / "frontend" / "src"
SCANNED_DIRS = ("app", "scripts", "migrations")
COMMON_AT_LEAST = 5
CJK_RUN = re.compile(r"[㐀-鿿]{3,}")


def _scanned_files() -> list[Path]:
    return sorted(p for d in SCANNED_DIRS for p in (BACKEND / d).rglob("*.py"))


def _frequency(texts: Iterable[str]) -> Counter:
    counter: Counter = Counter()
    for text in texts:
        counter.update(ch for ch in text if "\u4e00" <= ch <= "\u9fff")
    return counter


def _basis_texts() -> list[str]:
    """字频基准 = 真正发给用户的文案（前端 src + 后端 app），与被扫对象分开。"""
    files = [*FRONTEND_SRC.rglob("*.vue"), *FRONTEND_SRC.rglob("*.js"), *(BACKEND / "app").rglob("*.py")]
    texts = [p.read_text(encoding="utf-8", errors="replace") for p in files]
    assert len(texts) > 100, f"字频基准只有 {len(texts)} 个文件，遍历大概是坏的"
    return texts


def _string_literals(text: str) -> list[tuple[int, str]]:
    """所有字符串字面量（含 f-string 里的常量片段）；注释自然不在其中。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:  # 解析不了就退回整行口径，宁可粗也不漏
        return list(enumerate(text.splitlines(), 1))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((getattr(node, "lineno", 0) or 0, node.value))
    return found


def _is_mojibake(text: str, freq: Counter) -> bool:
    if "€" in text:  # U+20AC：UTF-8 续字节被 GBK 读成 '€'，正常中文串里不会出现
        return True
    # 3 字**滑窗**，不是整串判断：乱码嵌在正常中文里时（"AI 驱动的涓汉姹傛暀缁"），整串里那个
    # "的"会把坏串掩护过去——这是把坏串种进 index.html 才发现的，旧口径当时放过了它。
    return any(
        not any(freq.get(ch, 0) >= COMMON_AT_LEAST for ch in run[i : i + 3])
        for run in CJK_RUN.findall(text)
        for i in range(max(len(run) - 2, 0))
    )


def _suspicious_literals(text: str, freq: Counter) -> list[tuple[int, str]]:
    return [(n, v) for n, v in _string_literals(text) if _is_mojibake(v, freq)]


def test_no_mojibake_in_backend_string_literals():
    files = _scanned_files()
    assert files, "没扫到任何 .py，遍历大概是坏的"
    freq = _frequency(_basis_texts())
    offenders = {
        str(p.relative_to(BACKEND.parent)): [
            n for n, _ in _suspicious_literals(p.read_text(encoding="utf-8", errors="replace"), freq)
        ]
        for p in files
    }
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, f"这些行号上的字符串像 GBK 误读产生的乱码，请改回正常中文：{offenders}"


def test_the_rule_catches_the_old_corruption_and_skips_legitimate_comments():
    """正例：把本次修掉的那条坏串写成字面量，必须判出。
    反例：整行口径会误报的正常中文注释、以及"熟练掌握"这类正常词，字面量口径必须放行。"""
    freq = _frequency(_basis_texts())
    assert _suspicious_literals('MSG = "宸叉彁浜ら噸澶勭悊"\n', freq) == [(1, "宸叉彁浜ら噸澶勭悊")]
    # 注释里出现同样的生僻字组合不算：它到不了用户眼前（旧口径正是这里误报）
    assert _suspicious_literals("# 使「无 X-Tenant-Id → 回落默认租户」的断言不被自增 id 撞车干扰\n", freq) == []
    # 正常词：整行罕见字比例规则曾把它误判，这里确认没退回那个做法
    assert _suspicious_literals('TIP = "熟练掌握"\n', freq) == []
    # 句中乱码：坏串嵌在正常中文里（周围都是高频字）也必须判得出——整串口径在这里放过它
    assert _suspicious_literals('TIP = "AI 驱动的涓汉姹傛暀缁"\n', freq)
    assert _suspicious_literals('TIP = "AI 驱动的个人求职教练"\n', freq) == []
