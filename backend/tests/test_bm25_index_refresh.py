"""E5：BM25 关键词索引必须跟着语料变。

以前 `_BM25Index` 是"谁第一个用谁建、之后永久复用"，`_dirty` 声明了却从没被读过 ——
于是进程启动之后入库的知识文档在关键词这一路永远召不到，被删掉的切片还会继续被打分。
"""

import pytest

from app.services import multi_recall


class _FakeCollection:
    """够用的 Chroma 替身：只实现 BM25 建索引真正会调的 count() / get()。"""

    def __init__(self, docs: dict[str, tuple[str, str]]):
        self.docs = dict(docs)
        self.count_fails = False

    def count(self) -> int:
        if self.count_fails:
            raise RuntimeError("chroma 暂时读不了")
        return len(self.docs)

    def get(self, include=None, **kwargs):
        ids = list(self.docs)
        return {
            "ids": ids,
            "documents": [self.docs[cid][0] for cid in ids],
            "metadatas": [{"doc_id": f"doc_{cid}", "doc_type": self.docs[cid][1], "chunk_index": 0} for cid in ids],
        }

    def add(self, ids, documents, metadatas, embeddings=None):
        for cid, text, meta in zip(ids, documents, metadatas, strict=False):
            self.docs[cid] = (text, meta.get("doc_type", ""))


@pytest.fixture
def store(monkeypatch):
    fake = _FakeCollection(
        {
            "c_python": ("Python 后端面试指南", "interview"),
            "c_resume": ("简历模板使用说明", "resume_template"),
        }
    )
    monkeypatch.setattr(multi_recall, "get_knowledge_collection", lambda: fake)
    multi_recall._BM25Index._instance = None
    yield fake
    multi_recall._BM25Index._instance = None


def _hits(query: str) -> set[str]:
    return {chunk_id for chunk_id, _score in multi_recall._bm25_score(query, top_k=5)}


def test_document_ingested_after_startup_becomes_searchable(store):
    """新入库的文档不用等重启就能被关键词路召到——改之前这条必红。"""
    assert "c_k8s" not in _hits("kubernetes")

    store.add(
        ids=["c_k8s"],
        documents=["kubernetes 集群运维手册"],
        metadatas=[{"doc_id": "doc_c_k8s", "doc_type": "guide", "chunk_index": 0}],
    )

    assert "c_k8s" in _hits("kubernetes")


def test_deleted_document_stops_being_scored(store):
    assert "c_python" in _hits("Python")

    del store.docs["c_python"]

    assert "c_python" not in _hits("Python")


def test_same_count_rewrite_needs_the_explicit_invalidate(store):
    """条数不变的重写，计数自检看不出来——这正是 invalidate 存在的理由。"""
    assert "c_resume" in _hits("简历")

    store.docs["c_resume"] = ("docker 镜像构建说明", "resume_template")
    assert "c_resume" in _hits("简历")  # 索引仍指向旧文本（诚实记录这个局限）

    multi_recall.invalidate_bm25_index()

    assert "c_resume" not in _hits("简历")
    assert "c_resume" in _hits("docker")


def test_unreadable_count_keeps_the_working_index_instead_of_wiping_it(store):
    """Chroma 抖一下不该把建好的索引换成空的（`_bm25_score` 会把异常吞成 []，更难发现）。"""
    assert "c_python" in _hits("Python")

    store.count_fails = True

    assert "c_python" in _hits("Python")
