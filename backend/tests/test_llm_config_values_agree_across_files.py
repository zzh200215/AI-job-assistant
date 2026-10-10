"""D186：`LLM_TIMEOUT` / `LLM_MODEL` 这类值在树里有 5 个家，必须逐字节相同。

D185 那次是我手动把五处一起从 60 改到 120 的——**没有任何门会拦住下一次的半改**。
这正是 D166 记过的那族（同一个量在多处各写一遍，迟早分叉），而那次的解法就是词表守卫。
这里判的是配置面：代码默认值、两个 `.env.*.example`、两份 compose 的 `${VAR:-default}`。

判据两条，缺一条就是空转：
① 五处取到的值必须完全相同；
② 每一处都**必须真的读到值**（读到 None 说明锚点/键名变了，那才是最容易骗过测试的形状）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"

# 键 → 在哪些文件里以哪种写法出现。元组第三项是取值的正则（group(1) 就是值）。
SOURCES: dict[str, list[tuple[Path, str]]] = {
    "LLM_TIMEOUT": [
        (BACKEND / ".env.example", r"^LLM_TIMEOUT=(.*)$"),
        (ROOT / ".env.production.example", r"^LLM_TIMEOUT=(.*)$"),
        (ROOT / "docker-compose.yml", r"LLM_TIMEOUT: \$\{LLM_TIMEOUT:-(.*?)\}"),
        (ROOT / "docker-compose.prod.yml", r"LLM_TIMEOUT: \$\{LLM_TIMEOUT:-(.*?)\}"),
    ],
    "LLM_MODEL": [
        (BACKEND / ".env.example", r"^LLM_MODEL=(.*)$"),
        (ROOT / ".env.production.example", r"^LLM_MODEL=(.*)$"),
        (ROOT / "docker-compose.yml", r"LLM_MODEL: \$\{LLM_MODEL:-(.*?)\}"),
        (ROOT / "docker-compose.prod.yml", r"LLM_MODEL: \$\{LLM_MODEL:-(.*?)\}"),
    ],
}


def _from_file(path: Path, pattern: str) -> str:
    text = path.read_text(encoding="utf-8")
    hits = re.findall(pattern, text, re.MULTILINE)
    assert hits, f"{path.relative_to(ROOT)} 里读不到 {pattern} —— 锚点变了，这条守卫在数空气"
    assert len(hits) == 1, f"{path.relative_to(ROOT)} 里 {pattern} 命中 {len(hits)} 次，判据要重取"
    return hits[0].strip()


def _code_default(key: str) -> str:
    """类上的默认值，不是实例的——实例会被本机 `backend/.env` 覆盖。"""
    field = Settings.model_fields[key]
    assert field.default is not None, f"Settings.{key} 没有默认值，这条守卫没有对照物"
    return str(field.default)


@pytest.mark.parametrize("key", sorted(SOURCES))
def test_the_value_is_single_valued_across_the_tree(key: str):
    values = {"app/core/config.py (default)": _code_default(key)}
    for path, pattern in SOURCES[key]:
        values[str(path.relative_to(ROOT))] = _from_file(path, pattern)

    distinct = sorted(set(values.values()))
    assert len(distinct) == 1, f"{key} 在树里有 {len(distinct)} 个不同值：{values}"


def test_the_two_examples_and_two_composes_are_all_present():
    """防空转的第二半：文件少一个，上面那条就会因为"只读到一处"而假绿。"""
    for key, sources in SOURCES.items():
        assert len(sources) == 4, f"{key} 的对照文件数变了：{len(sources)}"
        for path, _ in sources:
            assert path.exists(), f"配置文件不见了，这条守卫失去意义：{path}"
    # 现量的那一个值就是本条存在的理由：动它必须连带改五处
    assert _code_default("LLM_TIMEOUT") == "120"
    assert _code_default("LLM_MODEL") == "gpt-4o-mini"
