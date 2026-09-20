"""IntentAgent — 意图识别 Agent

识别用户分析意图（全量分析 / 仅匹配 / 仅优化 / 仅面试题），
决定后续哪些步骤需要执行。
"""

from typing import Any

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.agent_intent import AGENT_INTENT_PROMPT
from app.prompts.rendering import render_prompt
from app.services.analysis_summaries import jd_digest, resume_digest
from app.services.llm_service import chat_json


class IntentAgent(BaseAgent):
    name = "IntentAgent"
    description = "意图识别 Agent — 识别用户分析意图，决定后续步骤"
    depends_on: list[str] = []
    result_type = "intent"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        db = context.db
        resume_id = context.resume_id
        jd_id = context.jd_id

        from app.models.history import JobDescription, Resume

        resume: Resume = db.get(Resume, resume_id)
        jd: JobDescription = db.get(JobDescription, jd_id)

        resume_summary = resume_digest(resume)
        jd_summary = jd_digest(jd)

        prompt = render_prompt(
            AGENT_INTENT_PROMPT,
            resume_id=resume_id,
            jd_id=jd_id,
            resume_summary=resume_summary,
            jd_summary=jd_summary,
        )
        result: dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        intent = result.get("intent", "unknown")
        confidence = result.get("confidence", 0)
        return f"意图识别: {intent} (置信度 {confidence})"
