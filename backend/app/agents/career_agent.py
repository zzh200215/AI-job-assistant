"""CareerAgent — 职业规划智能体（增强版）

新增:
  - 行业报告 RAG 检索，注入提示词
  - 可交互的可视化成长路线图 JSON
  - 技能雷达图数据
  - 细化的项目实践方向
"""

import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.career_agent import CAREER_AGENT_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json
from app.services.rag_service import search_knowledge


class CareerAgent(BaseAgent):
    name = "CareerAgent"
    description = "职业规划智能体 — 能力分析、可视化成长路线、项目实践推荐"
    depends_on: list[str] = ["ResumeAgent", "JobAgent", "MatchAgent"]
    result_type = "career_report"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        resume_report = context.get_agent_output("ResumeAgent", {}) or {}
        job_report = context.get_agent_output("JobAgent", {}) or {}
        match_report = context.match_result or {}

        # RAG: 检索行业报告 + 能力模型
        job_data = job_report.get("position_info", {})
        title = job_data.get("title", "")
        industry = job_data.get("industry", "")

        rag_parts = []
        for dtype in ["industry_report", "skill_model", "career_path", "salary_market", "transition_guide"]:
            results = search_knowledge(
                f"{title} {industry}", doc_type=dtype, top_k=3, db=context.db, user_id=context.user_id
            )
            if results:
                rag_parts.append(f"===== {dtype} =====")
                for r in results:
                    rag_parts.append(f"【{r.get('doc_title', '')}】{r.get('text', '')[:400]}")
        industry_context = "\n".join(rag_parts) if rag_parts else "暂无行业参考数据"

        prompt = render_prompt(
            CAREER_AGENT_PROMPT,
            resume_report=json.dumps(resume_report, ensure_ascii=False),
            job_report=json.dumps(job_report, ensure_ascii=False),
            match_report=json.dumps(match_report, ensure_ascii=False),
            industry_context=industry_context,
        )
        result: dict[str, Any] = chat_json(prompt)
        result["_rag_references"] = rag_parts  # 附上引用
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        stage = result.get("current_status", {}).get("career_stage", "未知")
        radar = result.get("skill_radar", {}).get("dimensions", [])
        phases = len(result.get("visual_roadmap", {}).get("phases", []))
        gaps = len(result.get("skill_gaps", []))
        return f"职业规划: {stage} | {gaps} 技能缺口 | {phases} 个成长阶段 | {len(radar)} 维度雷达"
