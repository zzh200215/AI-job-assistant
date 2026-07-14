"""RAG Query Rewrite 服务

根据用户原始问题、简历摘要、JD 摘要，调用 LLM 生成多个更适合向量检索的 query。
如果 LLM 失败，回退到原始 query。
"""

import logging
from dataclasses import dataclass

from app.services.llm_service import chat_json

logger = logging.getLogger(__name__)


@dataclass
class RewrittenQuery:
    """改写后的检索 query"""

    query_text: str  # 实际用于向量检索的文本
    query_type: str  # 类型: skill / responsibility / interview / competency / original
    purpose: str  # 用途说明（给前端展示）
    priority: int = 1  # 优先级，数字越小越优先


# ===================== Prompt 模板 =====================

_QUERY_REWRITE_PROMPT_TEMPLATE = """你是一名智能招聘系统的 RAG 查询优化专家。
你的任务是根据用户的原始问题、简历摘要和目标岗位 JD 摘要，生成 **3-5 个**更适合向量数据库检索的查询语句。

## 输入信息

### 原始问题
{original_query}

### 简历摘要
{resume_summary}

### JD 摘要
{jd_summary}

## 生成要求

1. **技能关键词方向 (skill)**：提取核心技术栈、工具、框架的关键词组合，用于检索技能模型和面试题库。
2. **岗位职责方向 (responsibility)**：基于 JD 中的职责描述，生成用于检索岗位描述库和行业报告的 query。
3. **面试题方向 (interview)**：生成针对该岗位常见面试考察点的检索 query。
4. **能力模型方向 (competency)**：生成针对该岗位所需软技能、能力模型、职业发展路径的检索 query。

## 输出格式

必须严格返回 JSON 数组，不要包含 markdown 代码块标记，不要包含任何解释文字：

[
  {{
    "query_text": "检索用的文本，5-20字",
    "query_type": "skill",
    "purpose": "检索技能模型和面试题库中的 Python 后端相关技术点",
    "priority": 1
  }},
  ...
]

## 约束
- query_text 必须简洁，去除口语化表达，保留核心关键词
- 总数控制在 3-5 个
- priority 越小优先级越高（1 最高）
- 如果原始问题本身已经很精确，可以保留一个 original 类型
"""


def _build_prompt(original_query: str, resume_summary: str, jd_summary: str) -> str:
    return _QUERY_REWRITE_PROMPT_TEMPLATE.format(
        original_query=original_query or "无",
        resume_summary=resume_summary or "无",
        jd_summary=jd_summary or "无",
    )


def rewrite_queries(
    original_query: str,
    resume_summary: str | None = None,
    jd_summary: str | None = None,
    max_queries: int = 5,
) -> list[RewrittenQuery]:
    """
    调用 LLM 生成改写后的检索 query 列表。

    参数:
        original_query: 用户原始问题
        resume_summary: 简历摘要（可选）
        jd_summary: JD 摘要（可选）
        max_queries: 最大 query 数量

    返回:
        RewrittenQuery 列表。若 LLM 失败，则回退到仅包含原始 query 的列表。
    """
    if not original_query or not original_query.strip():
        return []

    prompt = _build_prompt(original_query, resume_summary or "", jd_summary or "")

    try:
        result = chat_json(prompt)
        # 兼容 LLM 返回 { "queries": [...] } 或直接返回 [...]
        items = result if isinstance(result, list) else result.get("queries", [])

        queries: list[RewrittenQuery] = []
        seen = set()

        for item in items[:max_queries]:
            text = str(item.get("query_text", "")).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            queries.append(
                RewrittenQuery(
                    query_text=text,
                    query_type=str(item.get("query_type", "unknown")),
                    purpose=str(item.get("purpose", "")),
                    priority=int(item.get("priority", 99)),
                )
            )

        # 确保至少保留原始 query
        if not any(q.query_type == "original" for q in queries):
            queries.append(
                RewrittenQuery(
                    query_text=original_query,
                    query_type="original",
                    purpose="用户原始问题，作为兜底检索",
                    priority=99,
                )
            )

        # 按 priority 排序
        queries.sort(key=lambda x: x.priority)
        logger.info(f"[QueryRewrite] 生成 {len(queries)} 个改写 query")
        return queries

    except Exception as e:
        logger.warning(f"[QueryRewrite] LLM 改写失败，回退到原始 query: {e}")
        return [
            RewrittenQuery(
                query_text=original_query,
                query_type="original",
                purpose="用户原始问题（LLM 改写失败回退）",
                priority=99,
            )
        ]
