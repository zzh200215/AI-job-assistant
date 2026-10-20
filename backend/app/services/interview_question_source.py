"""P4：面试题源的两个入口共用同一套检索路径与题目 schema。

这两处以前各自拼查询、各自决定 top_k 与文档类型：
- 智能分析页的 `InterviewQuestionAgent`；
- 模拟面试建会话后的 `_build_personalized_prompt`。

差异不是学术问题：同一份 JD 在两个入口会召回到不同的题库片段，题目 schema 也只在模拟面试
那条路上被归一化。这里把"查什么、怎么格式化、题目长什么样"收成一处；两边的 prompt 仍各自
保留（一个是分析报告，一个是会话题面），但喂进去的题源材料与输出的题目形状不再分叉。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.interview_config_service import QUESTION_TYPE_LABELS
from app.services.rag_service import search_knowledge

CONTEXT_SNIPPET_CHARS = 300
DEFAULT_SEARCH_TYPES = ("interview_q", "skill_model")
SEARCH_TYPES_BY_INTERVIEW_TYPE: dict[str, tuple[str, ...]] = {
    "tech": ("interview_q", "skill_model"),
    "hr": ("interview_q",),
    "comprehensive": ("interview_q", "skill_model"),
    "stress": ("interview_q",),
    "group": ("interview_q",),
}


def search_types_for(interview_type: str | None) -> list[str]:
    """题型 → 该查哪些知识库。未知题型按默认两类查，不悄悄少查一类。"""
    return list(SEARCH_TYPES_BY_INTERVIEW_TYPE.get(str(interview_type or ""), DEFAULT_SEARCH_TYPES))


def build_rag_query(title: str, skills: list[str] | tuple[str, ...] | None, *, limit: int = 5) -> str:
    return f"{title or ''} {' '.join(str(skill) for skill in (skills or [])[:limit])}".strip()


def fetch_interview_question_context(
    db: Session | None,
    *,
    title: str,
    skills: list[str] | tuple[str, ...] | None,
    search_types: list[str] | tuple[str, ...] | None = None,
    top_k: int = 3,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """按同一查询词与 top_k 拉题库；返回按文档类型分组的结果，格式化交给调用方。"""
    query = build_rag_query(title, skills)
    groups: list[dict[str, Any]] = []
    for doc_type in search_types or DEFAULT_SEARCH_TYPES:
        results = search_knowledge(query, doc_type=doc_type, top_k=top_k, db=db, user_id=user_id)
        groups.append({"doc_type": doc_type, "results": list(results or [])})
    return groups


def format_rag_context(groups: list[dict[str, Any]]) -> str:
    """两个 prompt 共用的题源文本：保留文档类型头，单条截到 300 字。"""
    parts: list[str] = []
    for group in groups or []:
        results = group.get("results") or []
        if not results:
            continue
        parts.append(f"===== {group.get('doc_type', '')} =====")
        for item in results:
            parts.append(f"【{item.get('doc_title', '')}】{item.get('text', '')[:CONTEXT_SNIPPET_CHARS]}")
    return "\n".join(parts)


def normalize_question(
    item: Any,
    *,
    q_type: str,
    index: int = 1,
    source: str = "personalized",
) -> dict[str, Any] | None:
    """把模型返回的一道题收敛成会话题源 schema；题面为空返回 None（不占位）。"""
    if not isinstance(item, dict):
        return None
    text = str(item.get("q") or item.get("question") or "").strip()
    if not text:
        return None
    return {
        "id": index,
        "type": q_type,
        "category": QUESTION_TYPE_LABELS.get(q_type, "通用"),
        "question": text,
        "intent": str(item.get("intent") or ""),
        "ref_answer": str(item.get("ref_answer") or item.get("expected_answer") or ""),
        "source": source,
    }
