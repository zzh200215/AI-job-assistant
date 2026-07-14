"""Tool-assisted match analysis agent."""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext


class MatchAnalysisAgent(BaseAgent):
    name = "MatchAnalysisAgent"
    description = "Use safe tools to produce a structured resume/JD match report."
    depends_on: list[str] = ["ResumeParseAgent", "JDParseAgent"]
    result_type = "match_report"

    _TOOL_NAMES = ["search_knowledge", "calc_skill_coverage"]

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        resume_id = context.resume_id
        jd_id = context.jd_id
        if not resume_id or not jd_id:
            raise ValueError(f"missing resume_id({resume_id}) or jd_id({jd_id})")

        prompt = self._build_prompt(resume_id, jd_id)
        tools = self._get_tools()
        return self._call_llm_with_tools(prompt, tools)

    def _build_prompt(self, resume_id: int, jd_id: int) -> str:
        return f"""
You are a recruiting analyst. Analyze the match between the current resume and JD.

Inputs:
- resume_id: {resume_id}
- jd_id: {jd_id}

You already have the current task context. Do not request raw document-loading tools.

Workflow:
1. Use `calc_skill_coverage` to compare resume skills vs JD required skills.
2. Use `search_knowledge` to retrieve supporting knowledge from `skill_model`, `industry_report`, `resume_template`, and `interview_q` when useful.
3. Produce a final JSON report based on available evidence.

Return strict JSON with this schema:
{{
  "match_score": 85,
  "summary": "one-sentence summary",
  "strengths": ["...", "...", "..."],
  "gaps": ["...", "..."],
  "risk_points": ["..."],
  "dimension_scores": {{
    "skills": 0,
    "experience": 0,
    "education": 0,
    "industry": 0
  }},
  "recommendation": "recommended"
}}
"""

    def _get_tools(self) -> list:
        from app.agents.tools import list_tools

        return list_tools(self._TOOL_NAMES)

    def _call_llm_with_tools(self, prompt: str, tools: list) -> dict[str, Any]:
        from app.services.llm_service import chat_with_tools

        system_prompt = (
            "You are the match-analysis expert for the recruiting platform. "
            "Use tools only when needed, rely on evidence, and always return strict JSON."
        )

        try:
            result = chat_with_tools(
                prompt=prompt,
                tools=tools,
                system_prompt=system_prompt,
                max_tool_rounds=8,
            )
            result.setdefault("match_score", 0)
            result.setdefault("summary", "analysis incomplete")
            result.setdefault("strengths", [])
            result.setdefault("gaps", [])
            result.setdefault("risk_points", [])
            result.setdefault(
                "dimension_scores",
                {"skills": 0, "experience": 0, "education": 0, "industry": 0},
            )
            result.setdefault("recommendation", "hold")
            return result
        except (RuntimeError, ValueError) as exc:
            return {
                "match_score": 0,
                "summary": f"analysis unavailable: {str(exc)[:80]}",
                "strengths": [],
                "gaps": ["system analysis failed, retry later"],
                "risk_points": ["analysis incomplete, risks cannot be assessed reliably"],
                "dimension_scores": {"skills": 0, "experience": 0, "education": 0, "industry": 0},
                "recommendation": "hold",
                "_error": str(exc)[:200],
            }

    def _make_summary(self, result: dict[str, Any]) -> str:
        score = result.get("match_score", 0)
        recommendation = result.get("recommendation", "unknown")
        return f"match analysis: {score}/100 | {recommendation}"
