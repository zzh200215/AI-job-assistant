"""中文分词到底走哪条分支（E25 的第二半）。

§3.1 与 §8 的 rerank 那行一直写着"生产用 jieba 词重叠"。实测：`jieba` **不在
`backend/requirements.txt` 里**（`weasyprint` 在），所以按 requirements 装出来的任何环境
（本机、CI、生产镜像）里 `import jieba` 都失败，两处 `_tokenize` 都走 `except ImportError`
的字符 n-gram 兜底。这条测试把"哪条分支在跑"钉成事实，并在真有人加上 jieba 时强制他回头改文档
与重跑评测门 —— 而不是让文档一直描述一条跑不到的代码。
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


@pytest.mark.parametrize("name", sorted(TOKENIZERS))
def test_the_fallback_branch_is_what_runs_today(name):
    """`sys.modules["jieba"] = None` 让 `import jieba` 稳定抛 ImportError。

    兜底必须有产出：空 token 列表不会报错，只会让关键词这一路静默召不到任何东西。
    """
    tokenize = TOKENIZERS[name]
    original = sys.modules.get("jieba")
    sys.modules["jieba"] = None
    try:
        for sample in SAMPLES:
            tokens = tokenize(sample)
            if sample:
                assert tokens, f"{name} 对 {sample!r} 兜底成空 token"
            else:
                assert tokens == [], f"{name} 对空串应给空列表，拿到 {tokens}"
        # 兜底给不出"关键词"这个整词，只能给片段——这正是它与 jieba 的真实差别
        assert "关键词" not in tokenize("关键词优化") or len(tokenize("关键词优化")) > 3
    finally:
        if original is None:
            sys.modules.pop("jieba", None)
        else:
            sys.modules["jieba"] = original


@pytest.mark.parametrize("name", sorted(TOKENIZERS))
def test_the_jieba_branch_is_live_code_if_installed(name):
    """反方向：jieba 分支不是死代码。装上假 jieba 就必须改用它，否则上面那条断言毫无意义。"""
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


def test_jieba_is_not_a_declared_dependency():
    """绊线：**故意**在有人把 jieba 写进 requirements 时变红。

    那时要做的不是删断言，而是把 §3.1 / §8 里"jieba 词重叠"的说法改成实际生效的那条，
    并重跑 RAG / Recommend 两道评测门 —— 分词一变，BM25 与 rerank 的分数都会动。
    """
    declared = {line.split("==")[0].strip().lower() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()}
    assert "jieba" not in declared, (
        "jieba 成了声明依赖 —— 线上分词不再是 n-gram 兜底。"
        "请同步改写 docs/upgrade-plan.md §3.1 与 §8 里关于 jieba 的描述，并重跑 RAG/Recommend 评测门。"
    )
