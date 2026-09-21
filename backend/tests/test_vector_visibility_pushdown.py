"""向量检索的可见性必须下推进 Chroma 查询。

`n_results` 是**候选槽位数**，不是"从可见集合里取 N 条"。先在 Python 里过滤等于：
一个明明看得到文档的用户，因为前 N 个槽位被不可见文档占掉而拿到 0 条——真实语料上
实测 7 条查询里 3 条召回为 0。这些测试锁两件事：查询里带了可见集合，以及空集合不会被
塞成 Chroma 0.5.0 不接受的 `$in: []`。
"""

from app.services import multi_recall, rag_service
from app.utils.knowledge_access import VISIBLE_PUSHDOWN_LIMIT, knowledge_where_filter

# 前 10 条属于用户看不见的 doc 99，可见的只有后面 4 条
_CORPUS = [{"id": f"c{i}", "doc_id": "99", "doc_type": "jd_lib", "text": f"invisible {i}"} for i in range(10)] + [
    {"id": f"v{i}", "doc_id": "7", "doc_type": "salary_market", "text": f"visible {i}"} for i in range(4)
]


def _matches(chunk: dict, where: dict | None) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_matches(chunk, clause) for clause in where["$and"])
    if "doc_id" in where:
        return chunk["doc_id"] in where["doc_id"]["$in"]
    if "doc_type" in where:
        return chunk["doc_type"] == where["doc_type"]
    raise AssertionError(f"未预期的 where 形状: {where}")


class _ChromaLikeCollection:
    """按 Chroma 的语义实现：where 先过滤，再按 n_results 截断。

    `honor_where=False` 用来复现"没下推"的世界（= 修复前的行为），不是伪造通过。
    """

    def __init__(self, honor_where: bool = True):
        self.seen_where: list[dict | None] = []
        self.honor_where = honor_where

    def count(self) -> int:
        return len(_CORPUS)

    def query(self, query_embeddings=None, n_results=10, where=None):
        self.seen_where.append(where)
        pool = [c for c in _CORPUS if _matches(c, where)] if self.honor_where else list(_CORPUS)
        pool = pool[:n_results]
        return {
            "ids": [[c["id"] for c in pool]],
            "documents": [[c["text"] for c in pool]],
            "metadatas": [[{"doc_id": c["doc_id"], "doc_type": c["doc_type"]} for c in pool]],
            "distances": [[0.1] * len(pool)],
        }


def _patch_collection(monkeypatch, module, collection):
    monkeypatch.setattr(f"app.services.{module}.get_knowledge_collection", lambda: collection)


def test_vector_recall_pushes_the_visible_set_into_the_query(monkeypatch):
    collection = _ChromaLikeCollection()
    _patch_collection(monkeypatch, "multi_recall", collection)

    got = multi_recall._vector_recall("q", top_k=5, query_embedding=[0.1, 0.2], visible_doc_ids={"7"})

    assert [w for w in collection.seen_where if w] == [{"doc_id": {"$in": ["7"]}}]
    assert len(got) == 4, "可见的 4 个切片应全部拿到"
    assert {r["doc_id"] for r in got} == {"7"}


def test_without_pushdown_the_same_user_gets_nothing(monkeypatch):
    """非空洞性证明：不下推时，同样的查询一条都召不回——这正是修复前的行为。"""
    collection = _ChromaLikeCollection(honor_where=False)
    _patch_collection(monkeypatch, "multi_recall", collection)

    got = multi_recall._vector_recall("q", top_k=5, query_embedding=[0.1, 0.2], visible_doc_ids={"7"})

    assert got == []


def test_doc_type_and_visibility_are_anded_because_chroma_takes_one_operator():
    where = knowledge_where_filter(doc_type="salary_market", visible_doc_ids={"7", "3"})

    # Chroma 0.5.0 的 where 只接受"恰好一个操作符"，裸多键会抛
    assert list(where) == ["$and"]
    assert {"doc_type": "salary_market"} in where["$and"]
    assert {"doc_id": {"$in": ["3", "7"]}} in where["$and"]


def test_anded_clause_actually_filters_both_ways_on_a_chroma_like_store(monkeypatch):
    collection = _ChromaLikeCollection()
    _patch_collection(monkeypatch, "multi_recall", collection)

    got = multi_recall._vector_recall(
        "q", doc_type="salary_market", top_k=5, query_embedding=[0.1], visible_doc_ids={"7"}
    )

    assert len(got) == 4
    assert {r["doc_type"] for r in got} == {"salary_market"}


def test_empty_visible_set_is_never_sent_as_an_empty_in_clause(monkeypatch):
    """Chroma 对 `$in: []` 是直接抛错，不是匹配空集；空集合走调用方的提前返回。"""
    assert knowledge_where_filter(doc_type=None, visible_doc_ids=set()) is None
    assert knowledge_where_filter(doc_type="jd_lib", visible_doc_ids=set()) == {"doc_type": "jd_lib"}

    collection = _ChromaLikeCollection()
    _patch_collection(monkeypatch, "rag_service", collection)
    monkeypatch.setattr("app.services.rag_service.get_visible_knowledge_doc_ids", lambda db, **kwargs: set())

    results = rag_service.search_knowledge("q", top_k=3, query_embedding=[0.1], db=object(), user_id=5)

    assert results == []
    assert all("$in" not in str(where) for where in collection.seen_where), collection.seen_where


def test_oversized_visible_set_falls_back_to_post_filtering(monkeypatch):
    """集合太大就别把几万个 id 展开进 SQL：退回取回后过滤，行为与修复前一致。"""
    huge = {str(i) for i in range(1000, 1000 + VISIBLE_PUSHDOWN_LIMIT + 1)}  # 不含语料里的 doc 99 / 7

    where = knowledge_where_filter(doc_type="jd_lib", visible_doc_ids=huge)

    assert where == {"doc_type": "jd_lib"}  # 没有 doc_id 子句

    collection = _ChromaLikeCollection()
    _patch_collection(monkeypatch, "multi_recall", collection)
    got = multi_recall._vector_recall("q", top_k=5, query_embedding=[0.1], visible_doc_ids=huge)

    assert got == []  # 不下推也要被 post-filter 兜住，不能漏出看不见的文档


def test_rag_service_search_knowledge_pushes_visibility_down_too(monkeypatch):
    collection = _ChromaLikeCollection()
    _patch_collection(monkeypatch, "rag_service", collection)
    monkeypatch.setattr("app.services.rag_service.get_visible_knowledge_doc_ids", lambda db, **kwargs: {"7"})

    results = rag_service.search_knowledge("q", top_k=3, query_embedding=[0.1], db=object(), user_id=5)

    assert collection.seen_where == [{"doc_id": {"$in": ["7"]}}]
    assert len(results) == 3  # n_results=3，过滤后仍是可见文档，不再被截成 0
    assert {r["doc_id"] for r in results} == {"7"}
