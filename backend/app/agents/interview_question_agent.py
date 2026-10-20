"""InterviewQuestionAgent — 面试题生成 Agent

RAG 检索面试题库 + 生成四类面试题。
复用 interview prompt + rag_service
"""

import json
from typing import Any

from app.agents.base_agent import BaseAgent
from app.orchestration.context import AgentContext
from app.prompts.interview import INTERVIEW_PROMPT
from app.prompts.interview import PROMPT_VERSION as _PROMPT_VERSION
from app.prompts.rendering import render_prompt
from app.services.interview_question_source import (
    fetch_interview_question_context,
    format_rag_context,
    normalize_question,
)
from app.services.llm_service import chat_json


class InterviewQuestionAgent(BaseAgent):
    # 与 app.prompts.interview 那份 prompt 同源，别在这儿再抄一遍字面量。
    prompt_version = _PROMPT_VERSION

    name = "InterviewQuestionAgent"
    description = "面试题生成 Agent — RAG 检索面试题库 + 生成四类面试题"
    depends_on: list[str] = ["MatchAnalysisAgent"]
    result_type = "interview_questions"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        db = context.db
        resume_id = context.resume_id
        jd_id = context.jd_id

        from app.models.history import JobDescription, Resume

        resume: Resume = db.get(Resume, resume_id)
        jd: JobDescription = db.get(JobDescription, jd_id)

        resume_json = json.dumps(resume.parsed_json or {}, ensure_ascii=False)
        jd_json = json.dumps(jd.parsed_json or {}, ensure_ascii=False)

        # 与模拟面试那条入口共用同一个查询词、文档类型与格式化（P4 收尾）。
        parsed_jd = jd.parsed_json or {}
        title = parsed_jd.get("title", "") or jd.title or ""
        skills = parsed_jd.get("required_skills", []) or []
        rag_context = format_rag_context(
            fetch_interview_question_context(db, title=title, skills=skills, user_id=context.user_id)
        )

        prompt = render_prompt(
            INTERVIEW_PROMPT,
            rag_context=rag_context,
            resume_json=resume_json,
            jd_json=jd_json,
        )
        result: dict[str, Any] = chat_json(prompt)
        if isinstance(result, dict):
            questions = []
            for q_type in ("basic", "tech", "project", "scenario"):
                for item in result.get(q_type) or []:
                    normalized = normalize_question(
                        item,
                        q_type=q_type,
                        index=len(questions) + 1,
                        source="analysis_agent",
                    )
                    if normalized:
                        questions.append(normalized)
            # 原始四桶保留给旧读方；`questions` 是与模拟面试同一套 schema 的平铺视图。
            result = {**result, "questions": questions}
        return result

    def _make_summary(self, result: dict[str, Any]) -> str:
        total = result.get("total_questions", 0)
        tech = len(result.get("tech", []))
        project = len(result.get("project", []))
        basic = len(result.get("basic", []))
        scenario = len(result.get("scenario", []))
        return f"面试题: 共 {total} 题 | 基础 {basic} | 技术 {tech} | 项目 {project} | 场景 {scenario}"
