"""RAG confidence scoring based on retrieval evidence."""

from typing import Any


def _as_similarity(item: dict[str, Any]) -> float:
    final_score = item.get("final_score")
    if isinstance(final_score, int | float):
        return max(0.0, min(1.0, float(final_score)))

    vector_similarity = item.get("vector_similarity")
    if isinstance(vector_similarity, int | float):
        return max(0.0, min(1.0, float(vector_similarity)))

    raw_score = item.get("score")
    if isinstance(raw_score, int | float):
        return 1.0 / (1.0 + max(float(raw_score), 0.0))
    return 0.0


def _breakdown_item(name: str, score: float, weight: float, detail: str) -> dict[str, Any]:
    return {
        "name": name,
        "score": round(score, 1),
        "weight": weight,
        "detail": detail,
    }


def evaluate_rag_confidence(query: str, retrievals: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    all_items: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    unique_docs = set()
    for doc_type, items in (retrievals or {}).items():
        counts[doc_type] = len(items or [])
        for item in items or []:
            all_items.append(item)
            unique_docs.add((item.get("doc_title", ""), item.get("doc_type", doc_type)))

    total_chunks = len(all_items)
    similarities = sorted((_as_similarity(item) for item in all_items), reverse=True)
    avg_similarity = sum(similarities[:5]) / max(1, min(len(similarities), 5))
    source_coverage = sum(1 for value in counts.values() if value > 0)

    recall_score = min(total_chunks / 12.0, 1.0) * 100
    similarity_score = avg_similarity * 100
    skill_model_score = 100.0 if counts.get("skill_model", 0) > 0 else 30.0
    similar_jd_score = 100.0 if counts.get("jd_lib", 0) > 0 else 35.0

    final_score = round(
        recall_score * 0.35 + similarity_score * 0.35 + skill_model_score * 0.15 + similar_jd_score * 0.15
    )

    if final_score >= 80:
        level = "high"
        label = "高"
    elif final_score >= 60:
        level = "medium"
        label = "中"
    else:
        level = "low"
        label = "低"

    strengths: list[str] = []
    risks: list[str] = []
    if total_chunks >= 8:
        strengths.append("召回证据较充足，支持后续分析。")
    else:
        risks.append("召回片段偏少，结果可能受单一文档影响。")

    if avg_similarity >= 0.72:
        strengths.append("Top chunk 与查询的相关性较高。")
    elif avg_similarity < 0.55:
        risks.append("召回平均相关性偏低，建议补充更精确的检索词或知识文档。")

    if counts.get("skill_model", 0) > 0:
        strengths.append("已命中岗位能力模型，可支撑技能判断。")
    else:
        risks.append("未命中岗位能力模型，技能评估可信度会下降。")

    if counts.get("jd_lib", 0) > 0:
        strengths.append("已命中相似 JD，可辅助岗位对齐。")
    else:
        risks.append("未命中相似 JD，岗位语境支撑不足。")

    summary = (
        f"共召回 {total_chunks} 个片段、{len(unique_docs)} 份文档，"
        f"平均相关性 {avg_similarity:.2f}，当前 RAG 置信度为{label}。"
    )

    return {
        "query": query,
        "score": final_score,
        "level": level,
        "label": label,
        "summary": summary,
        "signals": {
            "total_chunks": total_chunks,
            "unique_docs": len(unique_docs),
            "avg_similarity": round(avg_similarity, 4),
            "source_coverage": source_coverage,
            "has_skill_model": counts.get("skill_model", 0) > 0,
            "has_similar_jd": counts.get("jd_lib", 0) > 0,
            "doc_type_counts": counts,
        },
        "breakdown": [
            _breakdown_item("召回数量", recall_score, 0.35, f"共召回 {total_chunks} 个片段"),
            _breakdown_item("平均相关性", similarity_score, 0.35, f"Top 片段平均相关性 {avg_similarity:.2f}"),
            _breakdown_item("岗位能力模型", skill_model_score, 0.15, "是否命中 skill_model"),
            _breakdown_item("相似 JD", similar_jd_score, 0.15, "是否命中 jd_lib"),
        ],
        "strengths": strengths,
        "risks": risks,
    }


def confidence_from_flat_results(query: str, results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in results or []:
        doc_type = item.get("doc_type") or "general"
        grouped.setdefault(doc_type, []).append(item)
    return evaluate_rag_confidence(query, grouped)
