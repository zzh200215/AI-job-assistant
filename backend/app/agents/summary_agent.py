"""SummaryAgent — 汇总报告 Agent

汇总所有 Agent 的输出，生成最终综合分析报告。
复用 agent_report prompt
"""

import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.agent_report import AGENT_REPORT_PROMPT
from app.prompts.rendering import render_prompt
from app.services.agent_steps import _build_jd_summary, _build_resume_summary
from app.services.llm_service import chat_json


class SummaryAgent(BaseAgent):
    name = "SummaryAgent"
    description = "汇总报告 Agent — 整合所有分析结果，生成最终报告"
    depends_on: list[str] = ["MatchAnalysisAgent", "ResumeOptimizeAgent", "InterviewQuestionAgent"]
    result_type = "final_report"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        db = context.db
        resume_id = context.resume_id
        jd_id = context.jd_id

        from app.models.history import JobDescription, Resume

        resume: Resume = db.get(Resume, resume_id)
        jd: JobDescription = db.get(JobDescription, jd_id)

        prompt = render_prompt(
            AGENT_REPORT_PROMPT,
            resume_summary=_build_resume_summary(resume),
            jd_summary=_build_jd_summary(jd),
            match_result=json.dumps(context.match_result or {}, ensure_ascii=False, indent=2),
            optimize_result=json.dumps(context.optimize_result or {}, ensure_ascii=False, indent=2),
            interview_result=json.dumps(context.interview_result or {}, ensure_ascii=False, indent=2),
            career_result=json.dumps(context.career_result or {}, ensure_ascii=False, indent=2),
            self_check_result=json.dumps([], ensure_ascii=False, indent=2),
        )
        result: dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        score = result.get("summary", {}).get("match_score", 0)
        rec = result.get("summary", {}).get("recommendation", "")
        return f"汇总报告: 综合匹配 {score}/100 | {rec}"
