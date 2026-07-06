# -*- coding: utf-8 -*-
"""
一次调用 = 一次完整分析（带 RAG 知识检索）：
- 匹配度报告
- 简历优化建议
- 面试题
三者结果合并写入 tb_analysis_record 一行

新增 RAG 流程：
  1. 从 JD 解析结果提取检索关键词
  2. 从 Chroma 检索相关知识
  3. 注入三个 prompt 的 {rag_context} 占位符
  4. 返回 references 供前端展示
"""
import json
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.models.history import Resume, JobDescription, AnalysisRecord
from app.prompts.match import MATCH_PROMPT
from app.prompts.optimize import OPTIMIZE_PROMPT
from app.prompts.interview import INTERVIEW_PROMPT
from app.prompts.rendering import render_prompt
from app.services.llm_service import chat_json, set_llm_trace_context
from app.services.rag_service import build_rag_context_multi, get_knowledge_references
from app.utils.service_access import get_accessible_job_for_user, get_owned_resume


def run_full_analysis(db: Session, resume_id: int, jd_id: int, remark: str = "", user_id: int = None) -> AnalysisRecord:
    """
    MVP + RAG：串行调用 3 个 prompt，每个 prompt 都注入 Chroma 检索的知识。
    """
    resume: Resume = get_owned_resume(db, resume_id, user_id) if user_id is not None else db.get(Resume, resume_id)
    jd: JobDescription = (
        get_accessible_job_for_user(db, jd_id, user_id)
        if user_id is not None
        else db.get(JobDescription, jd_id)
    )
    if not resume or not jd:
        raise ValueError("简历或 JD 不存在，请检查 ID")
    if not resume.parsed_json or not jd.parsed_json:
        raise ValueError("简历或 JD 还未解析，请先调用解析接口")

    resume_json = json.dumps(resume.parsed_json, ensure_ascii=False)
    jd_json = json.dumps(jd.parsed_json, ensure_ascii=False)

    # ---- RAG: 构建检索上下文 ----
    # 从 JD 中提取岗位名称和技能作为检索关键词
    jd_title = jd.parsed_json.get("title", "") or jd.title or ""
    jd_skills = jd.parsed_json.get("required_skills", []) or []
    jd_keywords = jd.parsed_json.get("keywords", []) or []
    query_parts = [jd_title] + jd_skills[:5] + jd_keywords[:5]
    query = " ".join(query_parts)

    # ---- 从简历提取摘要（供 planner 参考） ----
    resume_self_eval = (resume.parsed_json or {}).get("self_evaluation", "") or ""
    jd_context = jd.parsed_json.get("responsibilities_summary", "") or ""
    intent = "full_analysis"

    rag_ctx = build_rag_context_multi(
        query, db, user_id=user_id,
        intent=intent,
        resume_summary=resume_self_eval,
        jd_summary=jd_context,
    )
    references = get_knowledge_references(query, db, user_id=user_id)

    # ---- 1) 匹配度 ----
    try:
        match_prompt = render_prompt(
            MATCH_PROMPT,
            rag_context=rag_ctx.get("all", ""),
            resume_json=resume_json,
            jd_json=jd_json,
        )
        set_llm_trace_context(
            {
                "source": "match_service.run_full_analysis",
                "prompt_version": "match-service-v1",
                "prompt_name": "match",
                "prompt_family": "analysis",
                "db": db,
                "user_id": user_id,
                "resume_id": resume_id,
                "jd_id": jd_id,
                "prompt_metadata": {
                    "prompt_version": "match-service-v1",
                    "prompt_name": "match",
                    "prompt_family": "analysis",
                },
            }
        )
        match: Dict[str, Any] = chat_json(match_prompt)
        match["match_score"] = max(0, min(100, int(match.get("match_score") or 0)))
    except (RuntimeError, ValueError) as e:
        raise RuntimeError(f"匹配度分析失败: {e}")

    # ---- 2) 优化建议 ----
    try:
        optimize_prompt = render_prompt(
            OPTIMIZE_PROMPT,
            rag_context=rag_ctx.get("resume_templates", "") + "\n" + rag_ctx.get("skill_models", ""),
            resume_json=resume_json,
            jd_json=jd_json,
        )
        set_llm_trace_context(
            {
                "source": "match_service.run_full_analysis",
                "prompt_version": "optimize-service-v1",
                "prompt_name": "optimize",
                "prompt_family": "analysis",
                "db": db,
                "user_id": user_id,
                "resume_id": resume_id,
                "jd_id": jd_id,
                "prompt_metadata": {
                    "prompt_version": "optimize-service-v1",
                    "prompt_name": "optimize",
                    "prompt_family": "analysis",
                },
            }
        )
        optimize: Dict[str, Any] = chat_json(optimize_prompt)
    except (RuntimeError, ValueError) as e:
        raise RuntimeError(f"简历优化建议生成失败: {e}")

    # ---- 3) 面试题 ----
    try:
        interview_prompt = render_prompt(
            INTERVIEW_PROMPT,
            rag_context=rag_ctx.get("interview_questions", "") + "\n" + rag_ctx.get("skill_models", ""),
            resume_json=resume_json,
            jd_json=jd_json,
        )
        set_llm_trace_context(
            {
                "source": "match_service.run_full_analysis",
                "prompt_version": "interview-service-v1",
                "prompt_name": "interview",
                "prompt_family": "analysis",
                "db": db,
                "user_id": user_id,
                "resume_id": resume_id,
                "jd_id": jd_id,
                "prompt_metadata": {
                    "prompt_version": "interview-service-v1",
                    "prompt_name": "interview",
                    "prompt_family": "analysis",
                },
            }
        )
        interview: Dict[str, Any] = chat_json(interview_prompt)
    except (RuntimeError, ValueError) as e:
        raise RuntimeError(f"面试题生成失败: {e}")

    # ---- 4) 写库 ----
    try:
        record = AnalysisRecord(
            user_id=user_id,
            resume_id=resume_id,
            jd_id=jd_id,
            match_score=int(match.get("match_score", 0)),
            match_report=match,
            optimize_suggestions=optimize,
            interview_questions=interview,
            remark=remark,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        # 把 references 挂到 record 上（不持久化，仅用于 API 返回）
        record._references = references
        return record
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"分析结果保存到数据库失败: {str(e)}")
