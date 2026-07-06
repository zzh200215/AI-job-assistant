# -*- coding: utf-8 -*-
"""ResumeParseAgent — 简历解析 Agent

解析简历文件为结构化 JSON，若已解析则跳过。
复用 resume_service.parse_and_save
"""
from typing import Dict, Any, List

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.services.resume_service import parse_and_save as do_parse_resume


class ResumeParseAgent(BaseAgent):
    name = "ResumeParseAgent"
    description = "简历解析 Agent — 解析简历为结构化 JSON"
    depends_on: List[str] = ["IntentAgent"]
    result_type = "resume_parsed"

    def run_impl(self, context: AgentContext) -> Dict[str, Any]:
        db = context.db
        resume_id = context.resume_id

        from app.models.history import Resume
        resume: Resume = db.get(Resume, resume_id)

        if resume and resume.parsed_json:
            return {"skipped": True, "reason": "简历已解析", "parsed": resume.parsed_json}

        obj = do_parse_resume(db, resume_id)
        return {"skipped": False, "parsed": obj.parsed_json or {}}

    def _make_summary(self, result: Dict[str, Any]) -> str:
        if result.get("skipped"):
            return "简历解析: 已跳过（已解析）"
        parsed = result.get("parsed", {})
        name = parsed.get("name", "未知")
        skills_count = len(parsed.get("skills", []))
        return f"简历解析: {name} | {skills_count} 项技能"
