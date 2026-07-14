"""检索路由器 — Agentic RAG 的"指挥官"。

固定流水线（每次都查 8 类知识、各取固定 top_k）的问题：
  - 信息相关性低的源也被检索，token / latency 浪费
  - 上下文塞入大量噪声反而干扰 LLM 推理

本模块用 LLM（mock 时回退到启发式）先判断本次 query 该查哪些 doc_type、各取多少。
对外接口：plan_retrieval(query, intent, resume_summary, jd_summary) -> RetrievalPlan
"""

from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass

from app.core.config import settings
from app.prompts.retrieval_plan import RETRIEVAL_PLAN_PROMPT

logger = logging.getLogger(__name__)

# 8 类合法 doc_type
_VALID_DOC_TYPES = {
    "resume_template",
    "jd_lib",
    "interview_q",
    "skill_model",
    "industry_report",
    "career_path",
    "salary_market",
    "transition_guide",
}

# 单次检索总条数上限，防止 LLM 给出过大值导致上下文膨胀
_MAX_TOTAL_CHUNKS = 15
_MAX_TOP_K_PER_SOURCE = 5

# planner 缓存：相同 query+intent 不重复决策
_PLAN_CACHE: OrderedDict[str, RetrievalPlan] = OrderedDict()
_PLAN_CACHE_MAX = 128
_PLAN_CACHE_LOCK = threading.Lock()


@dataclass
class RetrievalPlan:
    """检索计划：每个 doc_type 该取多少条、决策原因、来源（llm / heuristic）"""

    doc_types: dict[str, int]
    reasoning: str = ""
    source: str = "heuristic"  # llm / heuristic / fallback

    def is_empty(self) -> bool:
        return not self.doc_types or sum(self.doc_types.values()) == 0


def _cache_key(query: str, intent: str) -> str:
    raw = f"{intent}|{query}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def clear_plan_cache() -> None:
    """清空 planner 缓存（测试用）"""
    with _PLAN_CACHE_LOCK:
        _PLAN_CACHE.clear()


# ===================== 启发式回退 =====================

# 关键词 → doc_type top_k
_INTENT_RULES = {
    "resume_optimize": {"resume_template": 3, "skill_model": 2},
    "match_analysis": {"jd_lib": 3, "skill_model": 2, "industry_report": 1},
    "interview_prep": {"interview_q": 4, "skill_model": 2},
    "career_planning": {"career_path": 3, "industry_report": 2, "salary_market": 2, "transition_guide": 1},
    "full_analysis": {
        "resume_template": 2,
        "jd_lib": 2,
        "interview_q": 2,
        "skill_model": 2,
        "industry_report": 1,
        "career_path": 1,
    },
}

_QUERY_KEYWORDS = [
    (("简历", "优化", "改简历", "诊断"), "resume_optimize"),
    (("匹配", "适合", "投递", "岗位选择"), "match_analysis"),
    (("面试", "面经", "追问", "回答"), "interview_prep"),
    (("职业", "规划", "成长", "学习路线", "转行"), "career_planning"),
]


def _heuristic_plan(query: str, intent: str) -> RetrievalPlan:
    """LLM 不可用时的回退：按 intent 或 query 关键字命中预设方案。"""
    if intent in _INTENT_RULES:
        return RetrievalPlan(
            doc_types=dict(_INTENT_RULES[intent]),
            reasoning=f"启发式：intent={intent} 命中预设规则",
            source="heuristic",
        )

    text = (query or "").lower()
    for keywords, mapped_intent in _QUERY_KEYWORDS:
        if any(kw in text for kw in keywords):
            return RetrievalPlan(
                doc_types=dict(_INTENT_RULES[mapped_intent]),
                reasoning=f"启发式：query 命中 '{mapped_intent}' 关键字",
                source="heuristic",
            )

    return RetrievalPlan(
        doc_types=dict(_INTENT_RULES["full_analysis"]),
        reasoning="启发式：未命中明确意图，回退综合方案",
        source="heuristic",
    )


# ===================== LLM 决策 =====================


def _normalize_plan(raw: dict) -> dict[str, int]:
    """
    清洗 LLM 输出：
      - 只保留合法 doc_type
      - top_k 限制到 [1, _MAX_TOP_K_PER_SOURCE]
      - 总条数超过 _MAX_TOTAL_CHUNKS 时按比例缩减
    """
    doc_types_raw = raw.get("doc_types") if isinstance(raw, dict) else None
    if not isinstance(doc_types_raw, dict):
        return {}

    cleaned: dict[str, int] = {}
    for key, value in doc_types_raw.items():
        if key not in _VALID_DOC_TYPES:
            continue
        try:
            top_k = int(value)
        except (TypeError, ValueError):
            continue
        if top_k <= 0:
            continue
        cleaned[key] = min(top_k, _MAX_TOP_K_PER_SOURCE)

    total = sum(cleaned.values())
    if total > _MAX_TOTAL_CHUNKS:
        ratio = _MAX_TOTAL_CHUNKS / total
        cleaned = {k: max(1, int(v * ratio)) for k, v in cleaned.items()}

    return cleaned


def _llm_plan(query: str, intent: str, resume_summary: str, jd_summary: str) -> RetrievalPlan | None:
    """调用 LLM 出检索计划。失败返回 None 由上游回退。"""
    # 延迟 import 避免循环依赖
    from app.services.llm_service import chat_json

    prompt = RETRIEVAL_PLAN_PROMPT.format(
        intent=intent or "full_analysis",
        query=(query or "")[:500],
        resume_summary=(resume_summary or "")[:300] or "（无）",
        jd_summary=(jd_summary or "")[:300] or "（无）",
    )

    try:
        raw = chat_json(prompt)
    except Exception as exc:
        logger.warning("retrieval planner LLM 调用失败，回退启发式: %s", exc)
        return None

    cleaned = _normalize_plan(raw if isinstance(raw, dict) else {})
    if not cleaned:
        logger.warning("retrieval planner LLM 输出无有效 doc_type，回退启发式")
        return None

    reasoning = ""
    if isinstance(raw, dict):
        reasoning = str(raw.get("reasoning", ""))[:200]

    return RetrievalPlan(doc_types=cleaned, reasoning=reasoning, source="llm")


# ===================== 对外主接口 =====================


def plan_retrieval(
    query: str,
    intent: str = "full_analysis",
    resume_summary: str = "",
    jd_summary: str = "",
    *,
    use_llm: bool | None = None,
) -> RetrievalPlan:
    """决定本次检索路由。

    use_llm=None 时按 settings.RAG_USE_PLANNER 决定；显式传 False 强制启发式。
    """
    # mock provider 不浪费一次 LLM 调用
    provider = (settings.LLM_PROVIDER or "mock").lower()
    enabled = settings.RAG_USE_PLANNER if use_llm is None else use_llm
    use_llm_resolved = enabled and provider != "mock"

    cache_k = _cache_key(query or "", intent or "")
    with _PLAN_CACHE_LOCK:
        cached = _PLAN_CACHE.get(cache_k)
        if cached is not None:
            _PLAN_CACHE.move_to_end(cache_k)
            return cached

    plan: RetrievalPlan | None = None
    if use_llm_resolved:
        plan = _llm_plan(query, intent, resume_summary, jd_summary)

    if plan is None:
        plan = _heuristic_plan(query, intent)

    with _PLAN_CACHE_LOCK:
        _PLAN_CACHE[cache_k] = plan
        if len(_PLAN_CACHE) > _PLAN_CACHE_MAX:
            _PLAN_CACHE.popitem(last=False)

    return plan
