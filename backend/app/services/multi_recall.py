"""
多路召回（Multi-Path Recall）

RAG 检索的三种召回路径：
  1. 向量召回 — Chroma 余弦相似度
  2. BM25 关键词召回 — 基于 Chroma 内文本，jieba 分词 + 内存 BM25 评分
  3. Query 改写召回 — LLM 改写原始 query，再走向量检索（复用已有的 query_rewrite）

最终融合：RRF（Reciprocal Rank Fusion）
  rank_score(chunk) = Σ 1 / (k + rank_in_path)
  k 默认 60，对 top-5 结果影响差异明显。

对外暴露：
  multi_recall(query, doc_type, top_k, db) → List[Dict]
"""

import logging
import math
import threading
import time
from collections import defaultdict

from app.core.chroma_client import get_knowledge_collection
from app.core.config import settings
from app.services import retrieval_log
from app.services.embedding_service import embed_text
from app.services.rerank_service import rerank_results
from app.utils.knowledge_access import get_visible_knowledge_doc_ids

logger = logging.getLogger(__name__)

# RRF 融合参数
_RRF_K = 60


# ===================== 0) 中文分词器（惰性加载）=====================


def _tokenize(text: str) -> list[str]:
    """中文分词 + 过滤停用词"""
    text = (text or "").strip()
    if not text:
        return []
    try:
        import jieba

        return [t.strip() for t in jieba.cut(text) if t.strip() and len(t.strip()) > 0]
    except ImportError:
        # jieba 不可用时，回退到字符级 ngram
        import re

        tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text)
        result: list[str] = []
        for token in tokens:
            if re.fullmatch(r"[A-Za-z0-9_]+", token):
                result.append(token)
                continue
            if len(token) == 1:
                result.append(token)
            else:
                result.extend(token[i : i + 2] for i in range(len(token) - 1))
        return result


# ===================== 1) 向量召回 =====================


def _vector_recall(
    query: str,
    doc_type: str | None = None,
    top_k: int = None,
    query_embedding=None,
    visible_doc_ids: set[str] | None = None,
) -> list[dict]:
    """Chroma 向量检索"""
    if top_k is None:
        top_k = settings.RAG_TOP_K

    collection = get_knowledge_collection()
    if collection.count() == 0:
        return []

    where_filter = None
    if doc_type:
        where_filter = {"doc_type": doc_type}

    try:
        if query_embedding is None:
            query_embedding = embed_text(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k * 2, collection.count()),  # 多召回一些供融合
            where=where_filter,
        )
    except Exception as e:
        logger.warning("向量召回失败: %s", e)
        return []

    return _build_vector_results(query_embedding, results, top_k * 2, visible_doc_ids=visible_doc_ids)


def _build_vector_results(query_embedding, results, limit: int, visible_doc_ids: set[str] | None = None) -> list[dict]:
    """将 Chroma 查询结果转为统一格式"""
    retrieved = []
    if not results or not results.get("ids") or not results["ids"][0]:
        return retrieved

    for i, chunk_id in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
        doc_id = str(meta.get("doc_id", ""))
        if visible_doc_ids is not None and doc_id not in visible_doc_ids:
            continue
        retrieved.append(
            {
                "chunk_id": chunk_id,
                "text": results["documents"][0][i] if results.get("documents") else "",
                "doc_title": meta.get("doc_title", ""),
                "doc_type": meta.get("doc_type", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "doc_id": doc_id,
                "file_name": meta.get("file_name", ""),
                "score": results["distances"][0][i] if results.get("distances") else 0,
                "recall_path": "vector",
            }
        )
        if len(retrieved) >= limit:
            break
    return retrieved[:limit]


# ===================== 2) BM25 关键词召回 =====================


class _BM25Index:
    """极简的内存 BM25 索引（基于 Chroma 切片文本）。

    只计算 BM25F 的基本形式：
        score = Σ  (tf * (k+1)) / (tf + k * (1 - b + b * dl / avgdl))
    其中 k=1.2, b=0.75（BM25 标准参数）
    """

    _instance: "_BM25Index | None" = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> "_BM25Index":
        """取索引；语料条数一变就整份换掉。

        以前是"第一个用的人建，之后永久复用"，于是进程启动后入库的文档在关键词这一路
        永远召不到（`_dirty` 声明了却从没被读过）。重建失败时继续用旧的那份——
        Chroma 抖一下不该把好索引换成空的。换指针是单次赋值，读侧不会看到半份索引。
        """
        current = cls._instance
        if current is not None:
            live = _collection_count()
            if live < 0 or live == current._corpus_count:
                return current

        with cls._lock:
            rebuilt = _BM25Index()
            if rebuilt.build_failed and cls._instance is not None:
                logger.warning("BM25 索引重建失败，继续沿用旧的一份（可能已陈旧）")
                return cls._instance
            cls._instance = rebuilt
            return rebuilt

    def __init__(self):
        self.doc_ids: list[str] = []  # chunk_id
        self.texts: list[str] = []  # 切片原文
        self.doc_types: list[str] = []  # doc_type
        self.doc_tokens: list[set] = []  # 每个文档的分词集合（用于快速匹配）
        self.idf: dict[str, float] = {}  # idf[term]
        self.doc_freq: dict[str, int] = {}  # df[term] = #docs containing term
        self.avg_dl = 0.0
        self._corpus_count = -1  # 建这份索引时语料有多少条；-1 = 没建成
        self.build_failed = False
        self._build()

    def _build(self):
        """扫描 Chroma 所有切片文本，构建倒排索引。"""
        try:
            collection = get_knowledge_collection()
            total = collection.count()
            self._corpus_count = total
            if total == 0:
                return

            data = collection.get(include=["documents", "metadatas"])
            if not data or not data.get("ids"):
                # count()>0 却读不到内容：当作没建成，保留上一份好索引而不是换成空的
                self.build_failed = True
                self._corpus_count = -1
                return

            ids_list = data["ids"]
            texts_list = data.get("documents", []) or []
            metas_list = data.get("metadatas") or []

            # Chroma get() 返回平铺列表（非嵌套列表）
            if isinstance(texts_list, list) and len(texts_list) > 0 and isinstance(texts_list[0], list):
                texts_list = texts_list[0]

            self.doc_ids = ids_list
            self.texts = texts_list
            self.doc_types = [(m or {}).get("doc_type", "") for m in metas_list]

            # 预分词（每个文档保存 token 集合）
            self.doc_tokens = []
            for text in texts_list:
                tokens = _tokenize(text)
                self.doc_tokens.append(set(tokens))

            n_docs = len(self.texts)
            if n_docs == 0:
                return

            total_chars = sum(len(t) for t in self.texts)
            self.avg_dl = total_chars / n_docs

            # 构建倒排索引
            from collections import Counter, defaultdict

            term_df: dict[str, int] = defaultdict(int)
            term_tf: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

            for i, text in enumerate(self.texts):
                tokens = _tokenize(text)
                unique_tokens = set(tokens)  # 对 df 去重
                for token in unique_tokens:
                    term_df[token] += 1
                # 对 tf 保留计数
                for token, count in Counter(tokens).items():
                    term_tf[token][self.doc_ids[i]] = count

            self.doc_freq = dict(term_df)
            self.idf = {}
            for term, df in term_df.items():
                # idf = ln((N - df + 0.5) / (df + 0.5) + 1)
                self.idf[term] = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)

        except Exception as e:
            logger.warning("BM25 索引构建失败: %s", e)
            self.doc_ids = []
            self.idf = {}
            self._corpus_count = -1
            self.build_failed = True

    def score(self, query_tokens: list[str], doc_type: str | None = None, top_k: int = None) -> list[tuple[str, float]]:
        """
        返回 sorted list of (chunk_id, bm25_score)。
        可选按 doc_type 过滤。
        """
        if top_k is None:
            top_k = settings.RAG_TOP_K

        if not self.doc_ids or not self.idf:
            return []

        k = 1.2
        b = 0.75
        scores: dict[str, float] = defaultdict(float)

        # 缓存已分词的 query_tokens
        query_terms = set(query_tokens)

        for term, idf_val in self.idf.items():
            if idf_val <= 0 or term not in query_terms:
                continue
            # term 在 query 中，遍历所有包含该 term 的文档
            for i, doc_id in enumerate(self.doc_ids):
                if doc_type and self.doc_types[i] != doc_type:
                    continue
                # 用预分词集合做匹配，避免中文子串误匹配
                if term in self.doc_tokens[i]:
                    dl = len(self.texts[i])
                    numerator = k + 1
                    denom = 1 + k * (1 - b + b * dl / self.avg_dl) if self.avg_dl > 0 else 1
                    scores[doc_id] += idf_val * numerator / denom

        # 排序取 top_k
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[: top_k * 2]


# ===================== BM25 索引的失效入口 =====================


def _collection_count() -> int:
    """当前语料条数；取不到返回 -1，让 `_BM25Index.get()` 沿用现有索引而不是重建/清空。"""
    try:
        return int(get_knowledge_collection().count())
    except Exception as exc:
        logger.warning("读取知识 collection 条数失败，BM25 沿用现有索引: %s", exc)
        return -1


def invalidate_bm25_index() -> None:
    """知识变更后丢掉 BM25 索引，下次检索重建。

    条数会变的增删 `get()` 自己能发现；这个入口是给"条数一样但内容变了"的路径用的
    （重切片、整库重建后 chunk 数完全可能不变）。
    """
    _BM25Index._instance = None


# ===================== 3) Query 改写召回 =====================


def _rewrite_recall(
    original_query: str,
    doc_type: str | None = None,
    top_k: int = None,
    resume_summary: str = "",
    jd_summary: str = "",
    visible_doc_ids: set[str] | None = None,
) -> list[dict]:
    """
    用 LLM 改写原始 query 为多个检索变体，逐一遍历做向量召回。
    """
    if top_k is None:
        top_k = settings.RAG_TOP_K

    try:
        from app.services.query_rewrite_service import rewrite_queries

        rewritten = rewrite_queries(
            original_query=original_query,
            resume_summary=resume_summary,
            jd_summary=jd_summary,
            max_queries=3,  # 改写只额外生成 3 个
        )
        # 去掉 original 类型，只改写非原始 query
        rewrite_queries = [q for q in rewritten if q.query_type != "original"]
    except Exception as e:
        logger.warning("Query 改写召回 LLM 调用失败: %s", e)
        return []

    if not rewrite_queries:
        return []

    all_results = []
    for rq in rewrite_queries:
        if not rq.query_text:
            continue
        try:
            vec_results = _vector_recall(
                rq.query_text,
                doc_type=doc_type,
                top_k=top_k,
                visible_doc_ids=visible_doc_ids,
            )
            for r in vec_results:
                r["recall_path"] = f"rewrite:{rq.query_type}"
            all_results.extend(vec_results)
        except Exception as e:
            logger.warning("改写召回失败(%s): %s", rq.query_type, e)

    return all_results[: top_k * 3]


# ===================== RRF 融合 =====================


def _rrf_fuse(
    vector_results: list[dict],
    bm25_results: list[tuple[str, float]],
    rewrite_results: list[dict],
    top_k: int = None,
    visible_doc_ids: set[str] | None = None,
) -> list[dict]:
    """
    Reciprocal Rank Fusion 融合三路结果。

    对每个 chunk_id，按在各路结果中的排名计算分数：
      rrf_score = Σ 1 / (k + rank)
    最终按 rrf_score 排序取 top_k。
    """
    if top_k is None:
        top_k = settings.RAG_TOP_K

    # 从向量结果中建立 chunk_id → metadata 的映射（用于回填 bm25 召回项）
    meta_by_cid: dict[str, dict] = {}
    for r in vector_results:
        meta_by_cid[r["chunk_id"]] = {
            "text": r.get("text", ""),
            "doc_title": r.get("doc_title", ""),
            "doc_type": r.get("doc_type", ""),
            "chunk_index": r.get("chunk_index", 0),
            "doc_id": r.get("doc_id", ""),
            "file_name": r.get("file_name", ""),
        }

    # BM25 can return chunks outside the vector candidate set. Hydrate those
    # chunks before fusion so lexical-only matches retain their text and type.
    missing_ids = [chunk_id for chunk_id, _score in bm25_results if chunk_id not in meta_by_cid]
    if missing_ids:
        try:
            collection = get_knowledge_collection()
            data = collection.get(ids=missing_ids, include=["documents", "metadatas"])
            documents = data.get("documents") or []
            metadatas = data.get("metadatas") or []
            for index, chunk_id in enumerate(data.get("ids") or []):
                metadata = metadatas[index] if index < len(metadatas) else {}
                meta_by_cid[chunk_id] = {
                    "text": documents[index] if index < len(documents) else "",
                    "doc_title": (metadata or {}).get("doc_title", ""),
                    "doc_type": (metadata or {}).get("doc_type", ""),
                    "chunk_index": (metadata or {}).get("chunk_index", 0),
                    "doc_id": (metadata or {}).get("doc_id", ""),
                    "file_name": (metadata or {}).get("file_name", ""),
                }
        except Exception as exc:
            logger.warning("Failed to hydrate BM25-only chunks: %s", exc)

    best_by_chunk: dict[str, dict] = {}

    for path_name, results in [
        ("vector", vector_results),
        ("bm25", bm25_results),
        ("rewrite", rewrite_results),
    ]:
        for rank, item in enumerate(results, start=1):
            cid = item[0] if path_name == "bm25" else item["chunk_id"]
            # BM25 路不经过 _build_vector_results 过滤，融合时统一按可见集合裁剪，
            # 防止词法命中的不可见文档（他人/他租户）混入最终结果。
            if visible_doc_ids is not None:
                meta = meta_by_cid.get(cid, {})
                doc_id = str(meta.get("doc_id", ""))
                if doc_id not in visible_doc_ids:
                    continue
            rrf = 1.0 / (_RRF_K + rank)
            score = item[1] if path_name == "bm25" else item.get("score", 0)

            meta = meta_by_cid.get(cid, {})

            if cid not in best_by_chunk:
                best_by_chunk[cid] = {
                    "chunk_id": cid,
                    "text": meta.get("text", ""),
                    "doc_title": meta.get("doc_title", ""),
                    "doc_type": meta.get("doc_type", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "doc_id": meta.get("doc_id", ""),
                    "file_name": meta.get("file_name", ""),
                    "rrf_score": rrf,
                    "vector_score": score if path_name == "vector" else None,
                    "bm25_relevance": score if path_name == "bm25" else 0,
                    "recalled_by": [path_name],
                }
            else:
                entry = best_by_chunk[cid]
                entry["rrf_score"] += rrf
                if path_name == "bm25":
                    entry["bm25_relevance"] = max(entry["bm25_relevance"], score)
                if path_name not in entry["recalled_by"]:
                    entry["recalled_by"].append(path_name)

    # 补全缺失值
    for entry in best_by_chunk.values():
        if entry["vector_score"] is None:
            entry["vector_score"] = 0.0
        entry["bm25_relevance"] = entry.get("bm25_relevance", 0) or 0.0

    # 按 rrf_score 降序取 top_k
    sorted_results = sorted(best_by_chunk.values(), key=lambda x: x["rrf_score"], reverse=True)
    return sorted_results[:top_k]


# ===================== 对外主接口 =====================


def multi_recall(
    query: str,
    db: object | None = None,
    user_id: int | None = None,
    doc_type: str | None = None,
    top_k: int = None,
    resume_summary: str = "",
    jd_summary: str = "",
) -> list[dict]:
    """
    多路召回主接口。

    三路并行召回 → RRF 融合 → 按统一格式返回。
    如果某路失败，自动降级为剩余路的融合。

    返回格式（每条）:
        {
            "chunk_id": str,
            "text": str,             # 文本内容
            "doc_title": str,
            "doc_type": str,
            "chunk_index": int,
            "doc_id": str,
            "file_name": str,
            "score": float,          # 向量距离（用于展示）
            "rrf_score": float,      # RRF 融合分数（用于排序）
            "vector_score": float,   # 向量召回距离
            "bm25_relevance": float, # BM25 相关性分数
            "recalled_by": List[str], # 哪些路召回了该切片
        }
    """
    if top_k is None:
        top_k = settings.RAG_TOP_K
    started = time.time()

    # 安全底线：没有 DB 会话就无法做租户/用户可见性过滤。
    # 宁可不检索（返回空）也不允许跨租户/跨用户泄漏（fail-closed）。
    if db is None:
        logger.warning(
            "multi_recall called without db session; refusing unqualified retrieval " "(query=%r, doc_type=%r)",
            query[:50],
            doc_type,
        )
        return []
    visible_doc_ids = get_visible_knowledge_doc_ids(db, user_id=user_id)
    if visible_doc_ids == set():
        return []

    # === 计算 query 向量（三路复用） ===
    try:
        q_emb = embed_text(query)
    except Exception as e:
        logger.warning("multi_recall 预计算 query 向量失败: %s", e)
        q_emb = None

    # === 1) 向量召回 ===
    vector_results = _vector_recall(
        query,
        doc_type=doc_type,
        top_k=top_k,
        query_embedding=q_emb,
        visible_doc_ids=visible_doc_ids,
    )

    # === 2) BM25 关键词召回 ===
    bm25_raw = _bm25_score(query, doc_type=doc_type, top_k=top_k)

    # === 3) Query 改写召回 ===
    rewrite_results = _rewrite_recall(
        query,
        doc_type=doc_type,
        top_k=top_k,
        resume_summary=resume_summary,
        jd_summary=jd_summary,
        visible_doc_ids=visible_doc_ids,
    )

    # === 4) RRF 融合 ===
    fused = _rrf_fuse(
        vector_results,
        bm25_raw,
        rewrite_results,
        top_k=max(top_k * 2, top_k),
        visible_doc_ids=visible_doc_ids,
    )
    reranked = rerank_results(query, fused, top_k=top_k)

    # === 5) 回填文本（RRF 融合后，从向量结果中按 chunk_id 回填 text） ===
    vector_by_cid: dict[str, str] = {}
    for r in vector_results:
        cid = r["chunk_id"]
        if cid and not vector_by_cid.get(cid):
            vector_by_cid[cid] = r.get("text", "")

    for r in reranked:
        cid = r.get("chunk_id", "")
        if not r.get("text") and vector_by_cid.get(cid):
            r["text"] = vector_by_cid[cid][:300]

    retrieval_log.record(
        query=query,
        doc_type=doc_type,
        top_k=top_k,
        results=reranked,
        duration_ms=int((time.time() - started) * 1000),
    )
    return reranked


def _bm25_score(query: str, doc_type: str | None = None, top_k: int = None) -> list[tuple[str, float]]:
    """调用内存 BM25 索引，返回 (chunk_id, score) 列表"""
    if top_k is None:
        top_k = settings.RAG_TOP_K

    try:
        index = _BM25Index.get()
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        return index.score(query_tokens, doc_type=doc_type, top_k=top_k)
    except Exception as e:
        logger.warning("BM25 召回失败: %s", e)
        return []
