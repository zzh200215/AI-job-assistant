# -*- coding: utf-8 -*-
"""ResumeOptimizeAgent — 简历优化 Agent

RAG 检索简历模板 + 生成优化建议。
复用 optimize prompt + rag_service
"""
import json
from typing import Dict, Any, List

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.optimize import OPTIMIZE_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json
from app.services.rag_service import search_knowledge


class ResumeOptimizeAgent(BaseAgent):
    name = "ResumeOptimizeAgent"
    description = "简历优化 Agent — RAG 检索简历模板 + 生成优化建议"
    depends_on: List[str] = ["MatchAnalysisAgent"]
    result_type = "optimize_suggestions"

    def run_impl(self, context: AgentContext) -> Dict[str, Any]:
        db = context.db
        resume_id = context.resume_id
        jd_id = context.jd_id

        from app.models.history import Resume, JobDescription
        resume: Resume = db.get(Resume, resume_id)
        jd: JobDescription = db.get(JobDescription, jd_id)

        resume_json = json.dumps(resume.parsed_json or {}, ensure_ascii=False)
        jd_json = json.dumps(jd.parsed_json or {}, ensure_ascii=False)

        # RAG 检索简历模板和能力模型
        parsed_jd = jd.parsed_json or {}
        title = parsed_jd.get("title", "") or jd.title or ""
        skills = parsed_jd.get("required_skills", []) or []
        query = f"{title} {' '.join(skills[:5])}".strip()

        rag_parts = []
        for dtype in ["resume_template", "skill_model"]:
            results = search_knowledge(query, doc_type=dtype, top_k=3)
            if results:
                rag_parts.append(f"===== {dtype} =====")
                for r in results:
                    rag_parts.append(f"【{r.get('doc_title', '')}】{r.get('text', '')[:300]}")
        rag_context = "\n".join(rag_parts)

        prompt = render_prompt(
            OPTIMIZE_PROMPT,
            rag_context=rag_context,
            resume_json=resume_json,
            jd_json=jd_json,
        )
        result: Dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: Dict[str, Any]) -> str:
        sections = len(result.get("sections", []))
        keywords_to_add = len(result.get("keywords_to_add", []))
        return f"简历优化: {sections} 个板块建议 | {keywords_to_add} 个关键词补充"
