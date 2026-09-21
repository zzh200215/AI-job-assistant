"""RAG retrieval helpers."""

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from app.core.chroma_client import get_knowledge_collection
from app.core.config import settings
from app.services import retrieval_log
from app.services.embedding_service import embed_text
from app.services.query_rewrite_service import RewrittenQuery
from app.services.rerank_service import rerank_results
from app.services.retrieval_planner import RetrievalPlan, plan_retrieval
from app.utils.knowledge_access import get_visible_knowledge_doc_ids, knowledge_where_filter

# 8 类知识源 → 返回字典的展示 key（保持对外结构稳定）
_DOC_TYPE_TO_KEY = {
    "resume_template": "resume_templates",
    "jd_lib": "jd_library",
    "interview_q": "interview_questions",
    "skill_model": "skill_models",
    "industry_report": "industry_reports",
    "career_path": "career_paths",
    "salary_market": "salary_market",
    "transition_guide": "transition_guides",
}

_DOC_TYPE_TO_LABEL = {
    "resume_template": "优秀简历模板参考",
    "jd_lib": "岗位描述库参考",
    "interview_q": "面试题库参考",
    "skill_model": "能力模型参考",
    "industry_report": "行业报告参考",
    "career_path": "职业发展路径",
    "salary_market": "招聘与薪资市场",
    "transition_guide": "校招社招转行资料",
}

logger = logging.getLogger(__name__)


def _filter_visible_results(
    results: dict,
    *,
    visible_doc_ids: set[str] | None,
    top_k: int,
) -> list[dict]:
    retrieved: list[dict] = []
    ids = (results or {}).get("ids") or []
    if not ids or not ids[0]:
        return retrieved

    documents = (results or {}).get("documents") or []
    metadatas = (results or {}).get("metadatas") or []
    distances = (results or {}).get("distances") or []
    row_ids = ids[0]
    row_docs = documents[0] if documents else []
    row_metas = metadatas[0] if metadatas else []
    row_distances = distances[0] if distances else []

    score_threshold = settings.RAG_SCORE_THRESHOLD or 0.0

    for index, chunk_id in enumerate(row_ids):
        metadata = row_metas[index] if index < len(row_metas) else {}
        doc_id = str((metadata or {}).get("doc_id", ""))
        if visible_doc_ids is not None and doc_id not in visible_doc_ids:
            continue

        distance = row_distances[index] if index < len(row_distances) else 0
        # Chroma 默认返回距离，距离越大相关性越低；阈值 > 0 时丢弃低相关 chunk
        if score_threshold > 0 and distance and distance > score_threshold:
            continue

        retrieved.append(
            {
                "chunk_id": chunk_id,
                "text": row_docs[index] if index < len(row_docs) else "",
                "doc_title": (metadata or {}).get("doc_title", ""),
                "doc_type": (metadata or {}).get("doc_type", ""),
                "chunk_index": (metadata or {}).get("chunk_index", 0),
                "doc_id": doc_id,
                "score": distance,
            }
        )
        if len(retrieved) >= top_k:
            break

    return retrieved


def search_knowledge(
    query: str,
    doc_type: str | None = None,
    top_k: int = None,
    query_embedding: list[float] | None = None,
    db: Session | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
) -> list[dict]:
    if top_k is None:
        top_k = settings.RAG_TOP_K

    # 安全底线：没有 DB 会话就无法做租户/用户可见性过滤。
    # 宁可不检索（返回空）也不允许跨租户/跨用户泄漏（fail-closed）。
    # 置于 Chroma 访问之前，无 db 时完全不触碰知识库。
    if db is None:
        logger.warning(
            "search_knowledge called without db session; refusing unqualified retrieval " "(query=%r, doc_type=%r)",
            query[:50],
            doc_type,
        )
        return []

    started = time.time()

    def _log(results: list[dict]) -> list[dict]:
        """把这次读取记进节点的收集器（不在节点里时是空操作）。

        空结果与查询失败同样要留行：一次分析里"查了 6 次、次次 0 命中"本身就是结论。
        """
        retrieval_log.record(
            query=query,
            doc_type=doc_type,
            top_k=top_k,
            results=results,
            duration_ms=int((time.time() - started) * 1000),
        )
        return results

    collection = get_knowledge_collection()
    if collection.count() == 0:
        return _log([])

    visible_doc_ids = get_visible_knowledge_doc_ids(db, user_id=user_id, organization_id=organization_id)
    if visible_doc_ids == set():
        return _log([])

    where_filter = knowledge_where_filter(doc_type=doc_type, visible_doc_ids=visible_doc_ids)

    try:
        if query_embedding is None:
            query_embedding = embed_text(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            where=where_filter,
        )
    except Exception as exc:
        logger.warning(
            "knowledge retrieval failed, falling back to empty result: %s (query=%r, doc_type=%r)",
            exc,
            query[:50],
            doc_type,
        )
        return _log([])

    return _log(_filter_visible_results(results, visible_doc_ids=visible_doc_ids, top_k=top_k))


def build_rag_context(query: str, db: Session, user_id: int | None = None) -> str:
    results = search_knowledge(query, db=db, user_id=user_id)
    if not results:
        return ""

    lines = ["===== 参考知识 ====="]
    for item in results:
        lines.append(f"【来源】 {item['doc_title']}({item['doc_type']})")
        lines.append(item["text"])
        lines.append("---")
    return "\n".join(lines)


def build_rag_context_multi(
    query: str,
    db: Session | None = None,
    user_id: int | None = None,
    *,
    intent: str = "full_analysis",
    resume_summary: str = "",
    jd_summary: str = "",
) -> dict[str, str]:
    """Agentic 检索：先用 planner 决定查哪些 doc_type、各取多少，再分别检索。

    返回结构保持与旧版兼容：固定 8 个 key + "all" + "_plan"（调试用）。
    未被 planner 选中的 doc_type 对应 value 为空字符串。
    """
    plan: RetrievalPlan = plan_retrieval(
        query=query,
        intent=intent,
        resume_summary=resume_summary,
        jd_summary=jd_summary,
    )
    logger.info(
        "rag plan source=%s intent=%s doc_types=%s reasoning=%s",
        plan.source,
        intent,
        plan.doc_types,
        plan.reasoning,
    )

    try:
        q_emb = embed_text(query)
    except Exception as exc:
        logger.warning("precomputing query embedding failed, falling back to per-call embedding: %s", exc)
        q_emb = None

    def _search(doc_type: str, top_k: int) -> list[dict]:
        return search_knowledge(
            query,
            doc_type=doc_type,
            top_k=top_k,
            query_embedding=q_emb,
            db=db,
            user_id=user_id,
        )

    def _format(label: str, items: list[dict]) -> str:
        if not items:
            return ""
        lines = [f"===== {label} ====="]
        for item in items:
            lines.append(f"【{item['doc_title']}】")
            lines.append(item["text"])
            lines.append("---")
        return "\n".join(lines)

    output: dict[str, str] = dict.fromkeys(_DOC_TYPE_TO_KEY.values(), "")
    all_blocks: list[str] = []

    for doc_type, top_k in plan.doc_types.items():
        items = _search(doc_type, top_k)
        label = _DOC_TYPE_TO_LABEL.get(doc_type, doc_type)
        block = _format(label, items)
        key = _DOC_TYPE_TO_KEY.get(doc_type)
        if key:
            output[key] = block
        if block:
            all_blocks.append(block)

    output["all"] = "\n".join(all_blocks)
    output["_plan"] = f"source={plan.source} doc_types={plan.doc_types} reasoning={plan.reasoning}"
    return output


def get_knowledge_references(query: str, db: Session | None = None, user_id: int | None = None) -> list[dict]:
    results = search_knowledge(query, db=db, user_id=user_id)
    seen_docs: dict[str, dict] = {}
    for item in results:
        key = item["doc_title"]
        if key not in seen_docs:
            seen_docs[key] = {
                "doc_title": item["doc_title"],
                "doc_type": item["doc_type"],
                "chunks": [],
            }
        seen_docs[key]["chunks"].append(
            {
                "text": item["text"][:200],
                "score": round(item["score"], 4),
            }
        )
    return list(seen_docs.values())


def search_knowledge_multi_queries(
    rewritten_queries: list[RewrittenQuery],
    doc_type: str | None = None,
    top_k_per_query: int = None,
    db: Session | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
) -> list[dict]:
    if top_k_per_query is None:
        top_k_per_query = settings.RAG_TOP_K

    all_results: list[dict] = []
    for rewritten in rewritten_queries:
        if not rewritten.query_text:
            continue
        chunk_results = search_knowledge(
            query=rewritten.query_text,
            doc_type=doc_type,
            top_k=top_k_per_query,
            db=db,
            user_id=user_id,
            organization_id=organization_id,
        )
        for item in chunk_results:
            item["query_used"] = rewritten.query_text
            item["query_type"] = rewritten.query_type
            item["query_purpose"] = rewritten.purpose
        all_results.extend(chunk_results)

    merged = merge_and_dedup_results(all_results)
    for item in merged:
        item["vector_score"] = item.get("score", 0.0)
        item["bm25_relevance"] = 0.0
        item["recalled_by"] = [query.get("type", "") for query in item.get("queries", []) if query.get("type")]
    rerank_query = " ".join(item.query_text for item in rewritten_queries[:2]) if rewritten_queries else ""
    return rerank_results(query=rerank_query, results=merged, top_k=len(merged))


def merge_and_dedup_results(results: list[dict]) -> list[dict]:
    best_by_chunk: dict[str, dict] = {}

    for item in results:
        chunk_id = item["chunk_id"]
        if chunk_id not in best_by_chunk:
            best_by_chunk[chunk_id] = dict(item)
            best_by_chunk[chunk_id]["queries"] = [{"text": item["query_used"], "type": item["query_type"]}]
            continue

        existing = best_by_chunk[chunk_id]
        if item["score"] < existing["score"]:
            existing["score"] = item["score"]
            existing["query_used"] = item["query_used"]
            existing["query_type"] = item["query_type"]
            if "query_purpose" in item:
                existing["query_purpose"] = item["query_purpose"]
        existing["queries"].append({"text": item["query_used"], "type": item["query_type"]})

    for item in best_by_chunk.values():
        seen = set()
        unique = []
        for query in item["queries"]:
            key = (query["text"], query["type"])
            if key not in seen:
                seen.add(key)
                unique.append(query)
        item["queries"] = unique

    return sorted(best_by_chunk.values(), key=lambda value: value["score"])


def build_rag_context_with_rewrite(
    rewritten_queries: list[RewrittenQuery],
    doc_type: str | None = None,
    top_k_per_query: int = None,
    db: Session | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
) -> str:
    results = search_knowledge_multi_queries(
        rewritten_queries=rewritten_queries,
        doc_type=doc_type,
        top_k_per_query=top_k_per_query,
        db=db,
        user_id=user_id,
        organization_id=organization_id,
    )
    if not results:
        return ""

    lines = ["===== 参考知识 ====="]
    for item in results:
        lines.append(f"【来源】 {item['doc_title']}({item['doc_type']}) | 召回query: {item['query_type']}")
        lines.append(item["text"])
        lines.append("---")
    return "\n".join(lines)


def get_knowledge_references_with_rewrite(
    rewritten_queries: list[RewrittenQuery],
    doc_type: str | None = None,
    top_k_per_query: int = None,
    db: Session | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
) -> list[dict]:
    results = search_knowledge_multi_queries(
        rewritten_queries=rewritten_queries,
        doc_type=doc_type,
        top_k_per_query=top_k_per_query,
        db=db,
        user_id=user_id,
        organization_id=organization_id,
    )

    seen_docs: dict[str, dict] = {}
    for item in results:
        key = item["doc_title"]
        if key not in seen_docs:
            seen_docs[key] = {
                "doc_title": item["doc_title"],
                "doc_type": item["doc_type"],
                "chunks": [],
            }
        seen_docs[key]["chunks"].append(
            {
                "text": item["text"][:200],
                "score": round(item["score"], 4),
                "query_type": item.get("query_type", ""),
                "query_used": item.get("query_used", ""),
            }
        )
    return list(seen_docs.values())
