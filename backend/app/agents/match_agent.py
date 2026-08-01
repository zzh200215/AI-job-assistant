"""MatchAgent — 匹配度评估智能体"""

import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.match_agent import MATCH_AGENT_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json, set_llm_trace_context
from app.services.match_score_calibration import apply_match_score_cap
from app.services.rag_service import search_knowledge


class MatchAgent(BaseAgent):
    name = "MatchAgent"
    description = "匹配度评估智能体 — 计算匹配分、输出优劣势、投递建议"
    depends_on: list[str] = ["ResumeAgent", "JobAgent"]
    result_type = "match_report"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        resume_report = context.get_agent_output("ResumeAgent", {}) or {}
        job_report = context.get_agent_output("JobAgent", {}) or {}

        # 从 job_report 提取检索关键词
        pos = job_report.get("position_info", {})
        title = pos.get("title", "")
        skills = [s.get("skill", "") for s in job_report.get("required_skills", [])[:5]]
        query = f"{title} {' '.join(skills)}".strip()

        # RAG 检索
        rag_results = search_knowledge(query, top_k=5, db=context.db, user_id=context.user_id)
        rag_text = "\n".join([f"【{r.get('doc_title', '')}】{r.get('text', '')[:200]}" for r in rag_results])

        prompt = render_prompt(
            MATCH_AGENT_PROMPT,
            resume_report=json.dumps(resume_report, ensure_ascii=False),
            job_report=json.dumps(job_report, ensure_ascii=False),
            rag_context=rag_text,
        )
        set_llm_trace_context(
            {
                "source": "MatchAgent.run_impl",
                "prompt_version": "match-agent-v1",
                "prompt_name": "match-agent",
                "prompt_family": "agent",
                "prompt_metadata": {
                    "prompt_version": "match-agent-v1",
                    "prompt_name": "match-agent",
                    "prompt_family": "agent",
                },
                "user_id": context.get("user_id"),
                "resume_id": context.get("resume_id"),
                "jd_id": context.get("jd_id"),
                "task_id": context.get("task_id"),
                "analysis_record_id": context.get("analysis_record_id"),
            }
        )
        result: dict[str, Any] = chat_json(prompt)
        apply_match_score_cap(
            result,
            json.dumps(resume_report, ensure_ascii=False),
            json.dumps(job_report, ensure_ascii=False),
        )
        result["_rag_references"] = rag_results  # 附上引用
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        score = result.get("match_score", 0)
        rec = result.get("recommendation", "未知")
        strengths = len(result.get("strengths", []))
        gaps = len(result.get("gaps", []))
        return f"匹配度: {score}/100 | {rec} | {strengths} 优势 | {gaps} 短板"
