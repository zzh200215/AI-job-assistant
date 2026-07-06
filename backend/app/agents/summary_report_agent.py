# -*- coding: utf-8 -*-
"""SummaryAgent — 结果汇总智能体"""
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.rendering import render_prompt
from app.prompts.summary_agent import SUMMARY_AGENT_PROMPT
from app.services.llm_service import chat_json


class SummaryAgent(BaseAgent):
    name = "SummaryAgent"
    description = "结果汇总智能体 — 整合5个智能体的结果，生成最终报告"
    depends_on: List[str] = ["ResumeAgent", "JobAgent", "MatchAgent", "InterviewAgent", "CareerAgent"]
    result_type = "summary_report"

    def run_impl(self, context: AgentContext) -> Dict[str, Any]:
        prompt = render_prompt(
            SUMMARY_AGENT_PROMPT,
            resume_result=json.dumps(context.get_agent_output("ResumeAgent", {}) or {}, ensure_ascii=False),
            job_result=json.dumps(context.get_agent_output("JobAgent", {}) or {}, ensure_ascii=False),
            match_result=json.dumps(context.match_result or {}, ensure_ascii=False),
            interview_result=json.dumps(context.interview_result or {}, ensure_ascii=False),
            career_result=json.dumps(context.career_result or {}, ensure_ascii=False),
        )
        result: Dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: Dict[str, Any]) -> str:
        score = result.get("summary", {}).get("match_score", 0)
        actions = len(result.get("action_items", []))
        return f"汇总报告: 综合匹配 {score}/100 | {actions} 个行动项"
