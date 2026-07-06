# -*- coding: utf-8 -*-
"""JDParseAgent — JD 解析 Agent

解析岗位 JD 为结构化 JSON，若已解析则跳过。
复用 jd_service.parse_and_save
"""
from typing import Dict, Any, List

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.services.jd_service import parse_and_save as do_parse_jd


class JDParseAgent(BaseAgent):
    name = "JDParseAgent"
    description = "JD 解析 Agent — 解析岗位描述为结构化 JSON"
    depends_on: List[str] = ["IntentAgent"]
    result_type = "jd_parsed"

    def run_impl(self, context: AgentContext) -> Dict[str, Any]:
        db = context.db
        jd_id = context.jd_id

        from app.models.history import JobDescription
        jd: JobDescription = db.get(JobDescription, jd_id)

        if jd and jd.parsed_json:
            return {"skipped": True, "reason": "JD已解析", "parsed": jd.parsed_json}

        obj = do_parse_jd(db, jd_id)
        return {"skipped": False, "parsed": obj.parsed_json or {}}

    def _make_summary(self, result: Dict[str, Any]) -> str:
        if result.get("skipped"):
            return "JD 解析: 已跳过（已解析）"
        parsed = result.get("parsed", {})
        title = parsed.get("title", "未知")
        skills_count = len(parsed.get("required_skills", []))
        return f"JD 解析: {title} | {skills_count} 项技能要求"
