"""Agent tool registry."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

ToolFn = Callable[..., dict[str, Any]]


class Tool:
    def __init__(self, name: str, description: str, parameters: dict, fn: ToolFn):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.fn = fn

    def to_openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, **kwargs) -> dict[str, Any]:
        try:
            result = self.fn(**kwargs)
            return {"success": True, "result": result}
        except Exception as exc:
            logger.warning("tool %s execution failed: %s", self.name, exc)
            return {"success": False, "error": f"tool '{self.name}' failed: {type(exc).__name__}: {exc}"}


def _tool_search_knowledge(query: str, doc_type: str = None, top_k: int = 3) -> dict:
    from app.core.database import SessionLocal
    from app.services.multi_recall import multi_recall

    # 工具执行无显式 user_id，仍必须带 DB 会话做租户级可见性过滤（fail-closed）。
    # 未注入租户上下文时回落默认租户，只可检索租户级 + 平台共享文档，杜绝跨租户泄漏。
    db = SessionLocal()
    try:
        results = multi_recall(query, db=db, doc_type=doc_type, top_k=top_k)
    finally:
        db.close()
    return {
        "results": [
            {
                "chunk_id": item.get("chunk_id", ""),
                "title": item.get("doc_title", ""),
                "doc_type": item.get("doc_type", ""),
                "text": (item.get("text", "") or "")[:800],
                "score": round(item.get("rrf_score", item.get("score", 0)), 4),
            }
            for item in results
        ],
        "total": len(results),
    }


def _tool_calc_skill_coverage(resume_skills: list[str], jd_skills: list[str]) -> dict:
    if not jd_skills:
        return {"coverage": 0.0, "matched": [], "missing": [], "total_jd": 0}

    resume_set = {skill.strip().lower() for skill in resume_skills if skill}
    jd_set = {skill.strip().lower() for skill in jd_skills if skill}
    matched = [skill for skill in jd_skills if skill.strip().lower() in resume_set]
    missing = [skill for skill in jd_skills if skill.strip().lower() not in resume_set]
    coverage = round(len(matched) / len(jd_set) * 100, 1)
    return {
        "coverage": coverage,
        "matched": matched,
        "missing": missing,
        "total_jd": len(jd_set),
        "total_resume": len(resume_set),
    }


_BUILTIN_TOOLS: dict[str, Tool] = {
    "search_knowledge": Tool(
        name="search_knowledge",
        description="Search the knowledge base and return the most relevant chunks.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text."},
                "doc_type": {
                    "type": "string",
                    "description": "Optional knowledge document type filter.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of chunks to return.",
                },
            },
            "required": ["query"],
        },
        fn=_tool_search_knowledge,
    ),
    "calc_skill_coverage": Tool(
        name="calc_skill_coverage",
        description="Calculate coverage between resume skills and JD required skills.",
        parameters={
            "type": "object",
            "properties": {
                "resume_skills": {"type": "array", "items": {"type": "string"}},
                "jd_skills": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["resume_skills", "jd_skills"],
        },
        fn=_tool_calc_skill_coverage,
    ),
}


def get_tool(name: str) -> Tool | None:
    return _BUILTIN_TOOLS.get(name)


def list_tools(names: list[str] = None) -> list[Tool]:
    if names is None:
        return list(_BUILTIN_TOOLS.values())

    result = []
    for name in names:
        tool = _BUILTIN_TOOLS.get(name)
        if tool:
            result.append(tool)
        else:
            logger.warning("tool '%s' does not exist and was skipped", name)
    return result


def tool_names() -> list[str]:
    return list(_BUILTIN_TOOLS.keys())


def register_tool(name: str, tool: Tool) -> None:
    if name in _BUILTIN_TOOLS:
        logger.warning("tool '%s' already exists and will be overwritten", name)
    _BUILTIN_TOOLS[name] = tool
