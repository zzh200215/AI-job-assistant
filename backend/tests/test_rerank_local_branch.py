"""rerank 的本地 cross-encoder 分支第一次被执行（E20）。

覆盖率给的是硬事实：`rerank_service.py` 在 771 条测试里 missing **74-88**（加载模型）与
**99-122**（分批前向）——也就是说"生产可选用本地 cross-encoder 打分"这句话**一行都没跑过**，
今天所有请求走的都是 `_heuristic_relevance`（jieba 词重叠 + 硬编码权重）。

这里**不下载真模型**（`.venv` 里 `torch`/`transformers` 根本没装，装不装是环境决定），而是往
`sys.modules` 塞假模块，跑的是产品自己的那段代码：门径检查、加载缓存、批切片、按输入顺序回填、
`rerank_source` 标签、降级不许冒充模型。
"""

from __future__ import annotations

import sys
import types

import pytest

from app.core.config import settings
from app.services import rerank_service


class FakeTensor:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def view(self, *_args):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return self.values


class FakeOutput:
    def __init__(self, logits: FakeTensor) -> None:
        self.logits = logits


class FakeNoGrad:
    """`with torch.no_grad():` 走的是**类型**上的 `__enter__/__exit__`，实例属性不算数。"""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class FakeTorch:
    def no_grad(self):
        return FakeNoGrad()

    def sigmoid(self, tensor: FakeTensor):
        return tensor


class FakeState:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.fail = False
        self.load_attempts = 0
        self.forward_batches: list[int] = []
        self.tokenized: list[list[str]] = []


class FakeTokenizer:
    def __init__(self, state: FakeState) -> None:
        self.state = state

    def __call__(self, pairs, **_kwargs):
        self.state.tokenized.append([pair[1] for pair in pairs])
        return {"count": len(pairs)}


class FakeModel:
    def __init__(self, state: FakeState) -> None:
        self.state = state
        self._cursor = 0

    def eval(self):
        return self

    def __call__(self, count: int, **_kwargs):
        self.state.forward_batches.append(count)
        chunk = self.state.scores[self._cursor : self._cursor + count]
        self._cursor += count
        return FakeOutput(FakeTensor(chunk))


@pytest.fixture
def nn(monkeypatch, tmp_path):
    """假 transformers/torch + 干净的模块全局；退出时全部还原，避免污染同进程其他测试。"""
    for name in ("_RERANK_MODEL", "_RERANK_TOKENIZER", "_RERANK_LOAD_ERROR"):
        monkeypatch.setattr(rerank_service, name, None)

    saved = {
        name: getattr(settings, name) for name in ("RERANKER_MODEL_PATH", "RERANKER_BATCH_SIZE", "RERANKER_PROVIDER")
    }
    # 够跑两次完整前向（有的用例要"全量排序"和"截断排序"各来一遍），分数按输入顺序发
    state = FakeState(scores=[0.1, 0.9, 0.5] * 3)

    def load_tokenizer(_path):
        state.load_attempts += 1
        if state.fail:
            raise RuntimeError("no model on disk")
        return FakeTokenizer(state)

    transformers_stub = types.ModuleType("transformers")
    transformers_stub.AutoTokenizer = types.SimpleNamespace(from_pretrained=load_tokenizer)
    transformers_stub.AutoModelForSequenceClassification = types.SimpleNamespace(
        from_pretrained=lambda _path: FakeModel(state)
    )
    monkeypatch.setitem(sys.modules, "transformers", transformers_stub)
    monkeypatch.setitem(sys.modules, "torch", FakeTorch())

    settings.RERANKER_MODEL_PATH = str(tmp_path)  # 只要过得了 `os.path.exists` 这道门
    settings.RERANKER_BATCH_SIZE = 2
    settings.RERANKER_PROVIDER = "auto"
    try:
        yield state
    finally:
        for name, value in saved.items():
            setattr(settings, name, value)


def _candidates():
    return [
        {"text": "关键词优化", "vector_score": 0.2, "bm25_relevance": 0.1},
        {"text": "项目经历", "vector_score": 0.7, "bm25_relevance": 0.4},
        {"text": "实习证明", "vector_score": 0.1, "bm25_relevance": 0.9},
    ]


def test_the_local_branch_batches_and_keeps_input_order(nn):
    """`RERANKER_BATCH_SIZE=2` + 3 条候选 → 前向被调 2 次（2 与 1），分数按**输入顺序**回填。

    错位不会报错，只会把第 2 条的分数安到第 3 条头上——所以断言落在每条自己的分数上。
    """
    ranked = rerank_service.rerank_results("简历", _candidates())

    assert nn.forward_batches == [2, 1], f"前向批次形状错了：{nn.forward_batches}"
    assert [text for batch in nn.tokenized for text in batch] == ["关键词优化", "项目经历", "实习证明"]
    by_text = {item["text"]: item for item in ranked}
    assert by_text["关键词优化"]["rerank_score"] == 0.1
    assert by_text["项目经历"]["rerank_score"] == 0.9
    assert by_text["实习证明"]["rerank_score"] == 0.5
    assert {item["rerank_source"] for item in ranked} == {"local_cross_encoder"}


def test_top_k_truncates_after_ranking_not_before(nn):
    """top_k 截的是**排完序**的结果：先截再打分，模型就只会看到前两条候选，排序口径整体换掉。

    顺带记下这个函数的真实权重：`final = 向量*0.5 + BM25*0.3 + rerank*0.2`，所以模型给 0.9 的那条
    （项目经历）**不是**第一——第一是 BM25 满分的"实习证明"。断言因此对着"全量排序的前两条"比，
    而不是对着模型分比。
    """
    full = rerank_service.rerank_results("简历", _candidates())
    nn.forward_batches.clear()

    ranked = rerank_service.rerank_results("简历", _candidates(), top_k=2)

    assert nn.forward_batches == [2, 1], "截断后模型只看到了 2 条候选 → top_k 被用在了排序之前"
    assert [item["text"] for item in ranked] == [item["text"] for item in full[:2]]
    assert len(ranked) == 2


def test_a_broken_model_is_remembered_and_never_retried(nn):
    """加载失败必须被缓存：每条请求都重跑一次 `from_pretrained` 会把请求线程全卡在磁盘 IO 上。"""
    nn.fail = True

    first = rerank_service.rerank_results("简历", _candidates())
    second = rerank_service.rerank_results("简历", _candidates())

    assert nn.load_attempts == 1, f"加载失败后又被重试了 {nn.load_attempts - 1} 次"
    assert nn.forward_batches == []
    for ranked in (first, second):
        assert {item["rerank_source"] for item in ranked} == {"heuristic"}
        # 降级不许冒充模型：启发式给的分不能是模型那三个值
        assert {item["rerank_score"] for item in ranked}.isdisjoint({0.1, 0.9, 0.5})


def test_no_model_path_never_attempts_the_loader(nn):
    """对照组：`RERANKER_MODEL_PATH` 没设时一次都不该去 load——否则上面那条"降级了"是空话。"""
    settings.RERANKER_MODEL_PATH = ""

    ranked = rerank_service.rerank_results("简历", _candidates())

    assert nn.load_attempts == 0
    assert nn.forward_batches == []
    assert {item["rerank_source"] for item in ranked} == {"heuristic"}


def test_empty_candidates_short_circuit(nn):
    """`_local_rerank_scores([])` 必须直接返回 []：否则 tokenizer 收到空 pairs 会炸。"""
    assert rerank_service.rerank_results("简历", []) == []
    assert nn.forward_batches == []
    assert nn.load_attempts == 0


def test_dirty_vector_scores_neither_raise_nor_poison_the_blend(nn):
    """顺带执行 `_vector_distance_to_similarity` 的三条转换分支：脏值必须归 0、负距离要 clamp，
    不能让一条脏数据把整次召回炸掉或算出 NaN。"""
    candidates = _candidates()
    candidates[0]["vector_score"] = None
    candidates[1]["vector_score"] = "不是数"
    candidates[2]["vector_score"] = -0.5

    ranked = rerank_service.rerank_results("简历", candidates)

    assert len(ranked) == 3
    assert all(item["rerank_source"] == "local_cross_encoder" for item in ranked)
    assert all(item["final_score"] == item["final_score"] for item in ranked), "出现 NaN 了"  # NaN != NaN
