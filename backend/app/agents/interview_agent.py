"""InterviewAgent — 面试辅导智能体"""

import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.interview_agent import INTERVIEW_AGENT_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json
from app.services.rag_service import search_knowledge


class InterviewAgent(BaseAgent):
    name = "InterviewAgent"
    description = "面试辅导智能体 — 生成技术/项目/HR/场景题+回答思路"
    depends_on: list[str] = ["ResumeAgent", "JobAgent", "MatchAgent"]
    result_type = "interview_report"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        resume_report = context.get_agent_output("ResumeAgent", {}) or {}
        job_report = context.get_agent_output("JobAgent", {}) or {}
        match_report = context.match_result or {}

        # RAG 检索面试题库
        pos = job_report.get("position_info", {})
        title = pos.get("title", "")
        rag_results = search_knowledge(title, doc_type="interview_q", top_k=5)
        rag_text = "\n".join([f"【{r.get('doc_title', '')}】{r.get('text', '')[:200]}" for r in rag_results])

        prompt = render_prompt(
            INTERVIEW_AGENT_PROMPT,
            resume_report=json.dumps(resume_report, ensure_ascii=False),
            job_report=json.dumps(job_report, ensure_ascii=False),
            match_report=json.dumps(match_report, ensure_ascii=False),
            rag_context=rag_text,
        )
        result: dict[str, Any] = chat_json(prompt)
        result["_rag_references"] = rag_results
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        total = result.get("total_questions", 0)
        tech = len(result.get("tech_questions", []))
        project = len(result.get("project_questions", []))
        return f"面试辅导: 共 {total} 题 | 技术 {tech} 道 | 项目 {project} 道"
