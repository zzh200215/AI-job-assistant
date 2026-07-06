# -*- coding: utf-8 -*-
"""JobAgent — 岗位分析智能体"""
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models.history import JobDescription
from app.orchestration.context import AgentContext
from app.prompts.job_agent import JOB_AGENT_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json


class JobAgent(BaseAgent):
    name = "JobAgent"
    description = "岗位分析智能体 — 拆解 JD、提取技能、识别隐性要求"
    depends_on: List[str] = []
    result_type = "job_report"

    def run_impl(self, context: AgentContext) -> Dict[str, Any]:
        jd_id = context.jd_id
        db: Session = context.db
        jd = db.get(JobDescription, jd_id)
        if not jd:
            raise ValueError(f"JD {jd_id} 不存在")

        jd_json = json.dumps(jd.parsed_json or {}, ensure_ascii=False)
        prompt = render_prompt(JOB_AGENT_PROMPT, jd_json=jd_json)

        result: Dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: Dict[str, Any]) -> str:
        title = result.get("position_info", {}).get("title", "未知")
        skills = len(result.get("required_skills", []))
        hidden = len(result.get("hidden_requirements", []))
        return f"岗位分析: {title} | {skills} 项技能 | {hidden} 个隐性要求"
