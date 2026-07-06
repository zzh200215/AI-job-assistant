# -*- coding: utf-8 -*-
"""IntentAgent — 意图识别 Agent

识别用户分析意图（全量分析 / 仅匹配 / 仅优化 / 仅面试题），
决定后续哪些步骤需要执行。
"""
import json
from typing import Dict, Any, List

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.agent_intent import AGENT_INTENT_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json
from app.services.agent_steps import _build_resume_summary, _build_jd_summary


class IntentAgent(BaseAgent):
    name = "IntentAgent"
    description = "意图识别 Agent — 识别用户分析意图，决定后续步骤"
    depends_on: List[str] = []
    result_type = "intent"

    def run_impl(self, context: AgentContext) -> Dict[str, Any]:
        db = context.db
        resume_id = context.resume_id
        jd_id = context.jd_id

        from app.models.history import Resume, JobDescription
        resume: Resume = db.get(Resume, resume_id)
        jd: JobDescription = db.get(JobDescription, jd_id)

        resume_summary = _build_resume_summary(resume)
        jd_summary = _build_jd_summary(jd)

        prompt = render_prompt(
            AGENT_INTENT_PROMPT,
            resume_id=resume_id,
            jd_id=jd_id,
            resume_summary=resume_summary,
            jd_summary=jd_summary,
        )
        result: Dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: Dict[str, Any]) -> str:
        intent = result.get("intent", "unknown")
        confidence = result.get("confidence", 0)
        return f"意图识别: {intent} (置信度 {confidence})"
