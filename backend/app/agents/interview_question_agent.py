# -*- coding: utf-8 -*-
"""InterviewQuestionAgent — 面试题生成 Agent

RAG 检索面试题库 + 生成四类面试题。
复用 interview prompt + rag_service
"""
import json
from typing import Dict, Any, List

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.interview import INTERVIEW_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json
from app.services.rag_service import search_knowledge


class InterviewQuestionAgent(BaseAgent):
    name = "InterviewQuestionAgent"
    description = "面试题生成 Agent — RAG 检索面试题库 + 生成四类面试题"
    depends_on: List[str] = ["MatchAnalysisAgent"]
    result_type = "interview_questions"

    def run_impl(self, context: AgentContext) -> Dict[str, Any]:
        db = context.db
        resume_id = context.resume_id
        jd_id = context.jd_id

        from app.models.history import Resume, JobDescription
        resume: Resume = db.get(Resume, resume_id)
        jd: JobDescription = db.get(JobDescription, jd_id)

        resume_json = json.dumps(resume.parsed_json or {}, ensure_ascii=False)
        jd_json = json.dumps(jd.parsed_json or {}, ensure_ascii=False)

        # RAG 检索面试题库
        parsed_jd = jd.parsed_json or {}
        title = parsed_jd.get("title", "") or jd.title or ""
        skills = parsed_jd.get("required_skills", []) or []
        query = f"{title} {' '.join(skills[:5])}".strip()

        rag_parts = []
        for dtype in ["interview_q", "skill_model"]:
            results = search_knowledge(query, doc_type=dtype, top_k=3)
            if results:
                rag_parts.append(f"===== {dtype} =====")
                for r in results:
                    rag_parts.append(f"【{r.get('doc_title', '')}】{r.get('text', '')[:300]}")
        rag_context = "\n".join(rag_parts)

        prompt = render_prompt(
            INTERVIEW_PROMPT,
            rag_context=rag_context,
            resume_json=resume_json,
            jd_json=jd_json,
        )
        result: Dict[str, Any] = chat_json(prompt)
        return result

    def _make_summary(self, result: Dict[str, Any]) -> str:
        total = result.get("total_questions", 0)
        tech = len(result.get("tech", []))
        project = len(result.get("project", []))
        basic = len(result.get("basic", []))
        scenario = len(result.get("scenario", []))
        return f"面试题: 共 {total} 题 | 基础 {basic} | 技术 {tech} | 项目 {project} | 场景 {scenario}"
