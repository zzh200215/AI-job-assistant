"""ResumeAgent — 简历诊断智能体"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models.history import Resume
from app.orchestration.context import AgentContext
from app.prompts.rendering import render_prompt
from app.prompts.resume_agent import RESUME_AGENT_PROMPT
from app.services.llm_service import chat_json


class ResumeAgent(BaseAgent):
    name = "ResumeAgent"
    description = "简历诊断智能体 — 提取简历结构、发现问题、优化建议"
    depends_on: list[str] = []
    result_type = "resume_report"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        resume_id = context.resume_id
        db: Session = context.db
        resume = db.get(Resume, resume_id)
        if not resume:
            raise ValueError(f"简历 {resume_id} 不存在")

        resume_json = json.dumps(resume.parsed_json or {}, ensure_ascii=False)
        prompt = render_prompt(RESUME_AGENT_PROMPT, resume_json=resume_json)

        result: dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        name = result.get("basic_info", {}).get("name", "未知")
        score = result.get("format_score", 0)
        issues = len(result.get("weaknesses", []))
        return f"简历诊断: {name} | 格式评分 {score} | 发现 {issues} 个问题"
