"""没有任何乱码：app/ 下的中文不能出现"按 GBK 读回后另存"的产物。

这类损坏的特征是一整段本项目正文里几乎不出现的生僻字连在一起（UTF-8 字节被当作 GBK 解码）。
判据不靠手写坏字清单，也不要求能完整复原（有些已经被截断丢字节，复原不出来）：
一段 >=3 字的 CJK 连续串里连一个高频字（全仓出现 >=5 次）都没有，就不可能是人写的。

已知漏报：串里恰好混进高频字时看不见（如 `鐩镐技搴` 的"技"）。曾试过加"罕见字比例"补这个洞，
会误伤"熟练掌握"这类正常词，放弃。
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
CJK_RUN = re.compile(r"[㐀-鿿]{3,}")


def _sources() -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8") for p in sorted(APP.rglob("*.py"))}


def _frequency(texts: Iterable[str]) -> Counter:
    counter: Counter = Counter()
    for text in texts:
        counter.update(ch for ch in text if "\u4e00" <= ch <= "\u9fff")
    return counter


def _suspicious_lines(text, freq) -> list[int]:
    bad = []
    for n, line in enumerate(text.splitlines(), 1):
        if "€" in line:  # U+20AC：UTF-8 续字节被 GBK 读成 '€'，正常代码注释里不会出现
            bad.append(n)
            continue
        for run in CJK_RUN.findall(line):
            if not any(freq.get(ch, 0) >= 5 for ch in run):
                bad.append(n)
                break
    return bad


def test_no_mojibake_in_backend_sources():
    texts = _sources()
    assert texts, "没扫到任何 app/*.py，遍历大概是坏的"
    freq = _frequency(texts.values())
    offenders = {
        str(p.relative_to(APP.parent)): lines for p, text in texts.items() if (lines := _suspicious_lines(text, freq))
    }
    assert not offenders, f"这些行像 GBK 误读产生的乱码，请改回正常中文：{offenders}"


def test_the_check_would_actually_catch_the_old_corruption():
    """反证：把本次修掉的那条坏串再喂一遍，必须被判出来；同一份真实字频下，
    app 里一句正常中文注释必须判不出来。"""
    freq = _frequency(_sources().values())
    assert _suspicious_lines("X = 86400  # 24 灏忔椂\n", freq) == [1]
    assert _suspicious_lines("    # 只对粗排后的短名单跑 canonical rubric。\n", freq) == []
