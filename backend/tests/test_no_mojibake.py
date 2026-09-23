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
③ 滑窗这条腿要求游程 >=3 字，所以坏串里只要有一个字落在私用区就会被截短到看不见——这正是
   `JobSearch.vue:972` 的 `建议` 在 D11/D12 之后仍然活着的原因。补的是 PRIVATE_USE 那条结构判据，
   不是把窗口降到 2 字（降到 2 字会误伤 14 个正常二字词，见该常量处的说明）。
"""

from __future__ import annotations

import ast
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND_SRC = BACKEND.parent / "frontend" / "src"
SCANNED_DIRS = ("app", "scripts", "migrations")
COMMON_AT_LEAST = 5
CJK_RUN = re.compile(r"[㐀-鿿]{3,}")

# 第二条腿是结构性的，与字频无关：私用区码位（U+E000-U+F8FF）与替换符（U+FFFD）不可能出自人写的
# 中文文案，只能来自一次误读——GBK 的用户自定义行 0xAA-0xF7 在 CP936 解码下正好落进私用区。
# 为什么需要这条腿：坏串里只要有一个字落在私用区，下面的 CJK 游程就被截短到 3 字以下，滑窗看不见。
# 为什么不能改成"把窗口降到 2 字"：前端那份实测有 14 个正常的二字游程两字都不在高频表里
# （硕士/博士/北京/封装/剩余/左右…），降窗口等于把守卫换成误报器。
# 用 chr() 而不是 \u 转义：让这条判据的源码里只有 ASCII，不把私用码位本身写进仓库。
PRIVATE_USE_LO, PRIVATE_USE_HI, REPLACEMENT_CHAR = chr(0xE000), chr(0xF8FF), chr(0xFFFD)
# 最大 CJK 游程（不是滑窗）：只有 1-2 字的游程才归这条腿管，3 字以上交给上面的频率判据。
CJK_ANY_RUN = re.compile(f"[{chr(0x3400)}-{chr(0x9fff)}]+")

_WRITTEN: set[str] | None = None


def _written_chars() -> set[str]:
    """这个仓库"真写得出来"的字符集合。复原判据要用它兜一层：`说` 的 GBK 字节 CBB5 也是合法
    UTF-8，解出来是 U+02F5——既不是字母也不是组合符号（类别 Sk），光靠类别会漏进来。而 U+02F5
    在本仓出现 0 次、`·` 出现 85 次，用"有没有人这么写过"分得开，且不需要列任何清单。"""
    global _WRITTEN
    if _WRITTEN is None:
        _WRITTEN = {ch for text in _basis_texts() for ch in text}
    return _WRITTEN


def _is_letter_or_mark(ch: str) -> bool:
    return unicodedata.category(ch)[0] in {"L", "M"}


def _short_run_misdecoded(text: str) -> bool:
    """1-2 字游程的"可复原"判据：把游程按 GBK 编回字节，再严格按 UTF-8 解一次；解出来**不含字母
    也不含组合符号**（只剩标点/符号/ASCII）才算一次误读。为什么需要它：`·` 的 UTF-8 字节 C2 B7
    被按 GBK 读回就是高频字 U+8DEF，游程只有 1 字，频率法与私用区法都看不见（前端 2026-09-23
    就是这么在界面上跑了很久"优先投递 路 83"）。为什么必须要求"不含字母"：只看"能复原"的话，
    实测 1155 个 1-2 字游程命中 53 处、其中 46 处是正常词（状态/未知/专业/每页/硕士…，它们的
    GBK 字节恰好也是合法 UTF-8）；加上这条后命中 7 处、误报 0，那 7 处全是同一个分隔符。
    """
    for run in CJK_ANY_RUN.findall(text):
        if len(run) > 2:
            continue
        try:
            back = run.encode("gbk").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue  # 编不回 GBK，或字节不是合法 UTF-8 —— 那就不是这条判据说的误读
        if back == run or any(_is_letter_or_mark(ch) for ch in back):
            continue
        if not all(ch in _written_chars() for ch in back):
            continue  # 复原出来的字符本仓从不写，那就不是"人写错了"，是巧合
        return True
    return False


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
    if any(PRIVATE_USE_LO <= ch <= PRIVATE_USE_HI or ch == REPLACEMENT_CHAR for ch in text):
        return True  # 私用码位/替换符：不要求能复原，也不是清单，是编码族留下的结构性痕迹
    if _short_run_misdecoded(text):
        return True  # 1-2 字游程：频率法看不见，只能靠"能不能原样解回去"
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
    # 私用区这条腿的两方向自证。正例是前端 JobSearch.vue:972 当年的实际码位序列：`建议` 的 UTF-8 字节
    # 按 GBK 读回 = U+5BE4 U+9E3F U+E185，最后一个字落在私用区，于是 CJK 游程只剩 2 字、滑窗对它失明。
    # 码位用 chr() 拼，免得把私用字符本身写进仓库（那正是这条判据要抓的东西）。
    garbled = chr(0x5BE4) + chr(0x9E3F) + chr(0xE185)
    restored = chr(0x5EFA) + chr(0x8BAE)
    assert _suspicious_literals(f'MSG = "{garbled}"\n', freq) == [(1, garbled)]
    assert _suspicious_literals(f'MSG = "{restored}"\n', freq) == []
    assert _suspicious_literals(f'MSG = "对接上游{chr(0xFFFD)}服务"\n', freq), "替换符同样只来自一次误读"
    # 第三条腿：分隔符被误读成高频字（`·` 的字节 C2 B7 按 GBK 读回就是 U+8DEF），必须判出；
    # 而"能复原、但复原出来是字母"的正常词必须放过——这一条把 46 个误报挡在外面。
    lu = chr(0x8DEF)
    assert _suspicious_literals(f'TAG = "优先投递 {lu} 83"\n', freq)
    assert _suspicious_literals('TAG = "优先投递 · 83"\n', freq) == []
    assert _suspicious_literals('LABEL = "状态"\n', freq) == []
    assert _suspicious_literals('LABEL = "每页"\n', freq) == []
    # 这条是"复原出来的字符必须本仓真写得出来"那层存在的理由：`说` 复原成 U+02F5，
    # 类别是 Sk（既非字母也非组合符号），只有"本仓写过 0 次"能把它挡在外面。
    assert _suspicious_literals('LABEL = "说 JD 要求全缺"\n', freq) == []
