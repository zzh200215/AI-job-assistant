"""中文分词到底走哪条分支（E25 的第二半，2026-10-07 D138 改了判据方向）。

E25（2026-10-05）量到的事实是：`jieba` **不在** `backend/requirements.txt` 里，所以按 requirements
装出来的任何环境（本机、CI、生产镜像）里 `import jieba` 必失败，两处 `_tokenize` 都走
`except ImportError` 的字符 n-gram 兜底——而 §3.1 / §8 一直写"生产用 jieba 词重叠"。那一批的修法是把
文档改成实际生效的那条，并留一条**故意会红的绊线**：谁把 jieba 变成声明依赖，谁就得同步改文档、重跑两道门。

这条绊线在 2026-10-07 红了，按它自己写的规矩办：`jieba==0.42.1` 进 `requirements.txt`，
文档随之改成"生产走 jieba，n-gram 是缺依赖时的兜底"，RAG 与 Recommend 两道评测门重跑（数字见
`docs/upgrade-plan.md` D138）。本文件三条腿盯的就是这三件事，方向与 E25 那次**相反**，
所以留着而不是重写历史：读的人能看到同一个判据在两个方向上各红过一次。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.services import multi_recall, rerank_service

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"
SAMPLES = ("关键词优化", "resume 关键词优化", "")

TOKENIZERS = {
    "rerank_service": rerank_service._tokenize,
    "multi_recall": multi_recall._tokenize,
}


def _without_jieba(tokenize, text: str) -> list[str]:
    """临时让 `import jieba` 抛 ImportError，取兜底那一条分支的输出。"""
    original = sys.modules.get("jieba")
    sys.modules["jieba"] = None
    try:
        return tokenize(text)
    finally:
        if original is None:
            sys.modules.pop("jieba", None)
        else:
            sys.modules["jieba"] = original


@pytest.mark.parametrize("name", sorted(TOKENIZERS))
def test_jieba_is_what_runs_when_the_dependency_is_present(name):
    """生产分支：依赖在场时整词必须原样出来——n-gram 兜底做不到这一点，只会给片段。

    这里**不设跳过条件**：`_tokenize` 是惰性 import，跳过判据会随测试顺序变绿变红，
    那等于没有判据。依赖被摘掉时这条和最后那条一起红，正是我们想要的两条腿。
    """
    tokenize = TOKENIZERS[name]
    assert "关键词" in tokenize("关键词优化"), f"{name} 带着 jieba 却没切出整词"


@pytest.mark.parametrize("name", sorted(TOKENIZERS))
def test_the_fallback_branch_still_produces_tokens(name):
    """反方向：把依赖摘掉也不能空手——空 token 列表不报错，只会让关键词这一路静默召不到东西。"""
    tokenize = TOKENIZERS[name]
    for sample in SAMPLES:
        tokens = _without_jieba(tokenize, sample)
        if sample:
            assert tokens, f"{name} 对 {sample!r} 兜底成空 token"
        else:
            assert tokens == [], f"{name} 对空串应给空列表，拿到 {tokens}"
    # 兜底给不出"关键词"这个整词，只能给片段——这正是它与 jieba 的真实差别
    fallback = _without_jieba(tokenize, "关键词优化")
    assert "关键词" not in fallback or len(fallback) > 3


@pytest.mark.parametrize("name", sorted(TOKENIZERS))
def test_both_tokenizers_route_through_the_module(name):
    """装上假 jieba 就必须改用它：证明 jieba 分支不是死代码，也证明两处只有一一个出口。"""
    called: list[str] = []

    class FakeJieba:
        @staticmethod
        def cut(text):
            called.append(text)
            return ["假", "分词"]

    original = sys.modules.get("jieba")
    sys.modules["jieba"] = FakeJieba
    try:
        tokens = TOKENIZERS[name]("任意文本")
    finally:
        if original is None:
            sys.modules.pop("jieba", None)
        else:
            sys.modules["jieba"] = original

    assert called == ["任意文本"], f"{name} 装了 jieba 也没用它"
    assert tokens == ["假", "分词"]


def test_jieba_is_a_declared_dependency():
    """绊线的另一头（D138 反转方向）：谁把 jieba 从 requirements 摘掉，这条就让谁红。

    摘掉不会报错，只会静默换分词——BM25 与 rerank 的分数都会动，而线上没人会看见"分支变了"这件事。
    真要摘，就同步改 §3.1 / §8 的说法并重跑 RAG / Recommend 两道门。
    """
    declared = {
        line.split("==")[0].split(">=")[0].strip().lower()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    }
    assert "jieba" in declared, (
        "jieba 不再是声明依赖 —— 线上分词会静默退回字符 n-gram。"
        "请同步改写 docs/upgrade-plan.md §3.1 与 §8，并重跑 RAG/Recommend 评测门。"
    )
