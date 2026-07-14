"""
Agent 工作流 — 具体步骤实现
每个步骤都是一个可调用的异步函数，接收 context 并返回结果 dict。

步骤列表:
  1. intent_recognition        — 意图识别
  2. resume_parse              — 解析简历(已解析则跳过)
  3. jd_parse                  — 解析JD(已解析则跳过)
  4. task_planning             — 任务拆解
  5. knowledge_retrieval       — 多轮知识检索
  6. matching_analysis         — 匹配度分析
  7. resume_optimization       — 简历优化
  8. interview_question_gen    — 面试题生成
  9. self_check                — 自我校验
  10. final_report             — 汇总报告
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription, Resume
from app.orchestration.context import AgentContext
from app.prompts.agent_intent import AGENT_INTENT_PROMPT
from app.prompts.agent_planning import AGENT_PLANNING_PROMPT
from app.prompts.agent_report import AGENT_REPORT_PROMPT
from app.prompts.agent_self_check import AGENT_SELF_CHECK_PROMPT
from app.prompts.interview import INTERVIEW_PROMPT
from app.prompts.match import MATCH_PROMPT
from app.prompts.optimize import OPTIMIZE_PROMPT
from app.prompts.rendering import render_prompt
from app.services.jd_service import parse_and_save as do_parse_jd
from app.services.llm_service import chat_json
from app.services.match_score_calibration import apply_match_score_cap
from app.services.multi_recall import multi_recall
from app.services.rag_confidence_service import evaluate_rag_confidence
from app.services.resume_service import parse_and_save as do_parse_resume


def _make_step_input(step_name: str, **kwargs) -> dict[str, Any]:
    return {"step": step_name, **kwargs}


# ==================== 1) 意图识别 ====================


def step_intent_recognition(ctx: AgentContext, db: Session) -> dict[str, Any]:
    resume_id = ctx["resume_id"]
    jd_id = ctx["jd_id"]

    resume: Resume = db.get(Resume, resume_id)
    jd: JobDescription = db.get(JobDescription, jd_id)

    resume_summary = _build_resume_summary(resume)
    jd_summary = _build_jd_summary(jd)

    prompt = render_prompt(
        AGENT_INTENT_PROMPT,
        resume_id=resume_id,
        jd_id=jd_id,
        resume_summary=resume_summary,
        jd_summary=jd_summary,
    )
    result: dict[str, Any] = chat_json(prompt)

    # 写入 ctx
    ctx["intent"] = result.get("intent", "full_analysis")
    ctx["intent_detail"] = result
    ctx["required_steps"] = result.get(
        "required_steps",
        [
            "intent_recognition",
            "resume_parse",
            "jd_parse",
            "task_planning",
            "knowledge_retrieval",
            "matching_analysis",
            "resume_optimization",
            "interview_question_generation",
            "self_check",
            "final_report",
        ],
    )
    return result


# ==================== 2) 简历解析 ====================


def step_resume_parse(ctx: AgentContext, db: Session) -> dict[str, Any]:
    resume_id = ctx["resume_id"]
    resume: Resume = db.get(Resume, resume_id)
    if resume and resume.parsed_json:
        return {"skipped": True, "reason": "简历已解析", "parsed": resume.parsed_json}

    obj = do_parse_resume(db, resume_id)
    return {"skipped": False, "parsed": obj.parsed_json or {}}


# ==================== 3) JD 解析 ====================


def step_jd_parse(ctx: AgentContext, db: Session) -> dict[str, Any]:
    jd_id = ctx["jd_id"]
    jd: JobDescription = db.get(JobDescription, jd_id)
    if jd and jd.parsed_json:
        return {"skipped": True, "reason": "JD已解析", "parsed": jd.parsed_json}

    obj = do_parse_jd(db, jd_id)
    return {"skipped": False, "parsed": obj.parsed_json or {}}


# ==================== 4) 任务拆解 ====================


def step_task_planning(ctx: AgentContext, db: Session) -> dict[str, Any]:
    resume_id = ctx["resume_id"]
    jd_id = ctx["jd_id"]

    resume: Resume = db.get(Resume, resume_id)
    jd: JobDescription = db.get(JobDescription, jd_id)

    resume_summary = _build_resume_summary(resume)
    jd_summary = _build_jd_summary(jd)
    intent = ctx.get("intent", "full_analysis")

    prompt = render_prompt(
        AGENT_PLANNING_PROMPT,
        intent=intent,
        resume_summary=resume_summary,
        jd_summary=jd_summary,
    )
    plan: list = chat_json(prompt)
    if not isinstance(plan, list):
        plan = [plan]

    ctx["plan"] = plan
    return {"plan": plan, "steps_count": len(plan)}


# ==================== 5) 知识检索 ====================


def step_knowledge_retrieval(ctx: AgentContext, db: Session) -> dict[str, Any]:
    jd_id = ctx["jd_id"]
    jd: JobDescription = db.get(JobDescription, jd_id)
    if not jd or not jd.parsed_json:
        return {"results": [], "message": "JD未解析，跳过检索"}

    parsed = jd.parsed_json
    title = parsed.get("title", "") or jd.title or ""
    skills = parsed.get("required_skills", []) or []
    keywords = parsed.get("keywords", []) or []

    query_parts = [title] + (skills[:5] if skills else []) + (keywords[:5] if keywords else [])
    query = " ".join(query_parts)

    resume_id = ctx.get("resume_id")
    resume: Resume = db.get(Resume, resume_id) if resume_id else None
    resume_summary = (resume.parsed_json or {}).get("self_evaluation", "") or ""
    jd_summary = parsed.get("responsibilities_summary", "") or ""

    # ---- 多路召回（向量 + BM25 + 改写 → RRF 融合） ----
    retrievals = {}
    for dtype in [
        "resume_template",
        "jd_lib",
        "interview_q",
        "skill_model",
        "industry_report",
        "career_path",
        "salary_market",
        "transition_guide",
    ]:
        results = multi_recall(
            query,
            db=db,
            user_id=ctx.get("user_id"),
            doc_type=dtype,
            top_k=3,
            resume_summary=resume_summary,
            jd_summary=jd_summary,
        )
        # 去掉内部字段（rrf_score 等），保留原始格式兼容上游
        clean = []
        for r in results:
            clean.append(
                {
                    "chunk_id": r["chunk_id"],
                    "text": r.get("text", ""),
                    "doc_title": r.get("doc_title", ""),
                    "doc_type": r.get("doc_type", ""),
                    "chunk_index": r.get("chunk_index", 0),
                    "score": r.get("vector_score", r.get("score", 0)),
                    "vector_similarity": r.get("vector_similarity", 0),
                    "keyword_score": r.get("keyword_score", 0),
                    "rerank_score": r.get("rerank_score", 0),
                    "rerank_source": r.get("rerank_source", ""),
                    "final_score": r.get("final_score", 0),
                    "recalled_by": r.get("recalled_by", []),
                }
            )
        retrievals[dtype] = clean

    rag_confidence = evaluate_rag_confidence(query, retrievals)

    ctx["retrieval_results"] = retrievals
    ctx["rag_confidence"] = rag_confidence
    return {
        "query": query,
        "retrievals": retrievals,
        "rag_confidence": rag_confidence,
    }


# ==================== 6) 匹配度分析 ====================


def step_matching_analysis(ctx: AgentContext, db: Session) -> dict[str, Any]:
    resume_id = ctx["resume_id"]
    jd_id = ctx["jd_id"]

    resume: Resume = db.get(Resume, resume_id)
    jd: JobDescription = db.get(JobDescription, jd_id)
    resume_json = json.dumps(resume.parsed_json or {}, ensure_ascii=False)
    jd_json = json.dumps(jd.parsed_json or {}, ensure_ascii=False)

    # 组装 RAG 上下文
    retrievals = ctx.get("retrieval_results", {})
    rag_parts = []
    for dtype, results in retrievals.items():
        if results:
            rag_parts.append(f"===== {dtype} =====")
            for r in results:
                rag_parts.append(f"【{r.get('doc_title', '')}】{r.get('text', '')[:300]}")
    rag_context = "\n".join(rag_parts)

    prompt = render_prompt(
        MATCH_PROMPT,
        rag_context=rag_context,
        resume_json=resume_json,
        jd_json=jd_json,
    )
    result: dict[str, Any] = chat_json(prompt)
    apply_match_score_cap(result, resume_json, jd_json)

    ctx["match_result"] = result
    return result


# ==================== 7) 简历优化 ====================


def step_resume_optimization(ctx: AgentContext, db: Session) -> dict[str, Any]:
    resume_id = ctx["resume_id"]
    jd_id = ctx["jd_id"]

    resume: Resume = db.get(Resume, resume_id)
    jd: JobDescription = db.get(JobDescription, jd_id)
    resume_json = json.dumps(resume.parsed_json or {}, ensure_ascii=False)
    jd_json = json.dumps(jd.parsed_json or {}, ensure_ascii=False)

    # 组装简历模板参考
    retrievals = ctx.get("retrieval_results", {})
    rag_parts = []
    for dtype in ["resume_template", "skill_model"]:
        results = retrievals.get(dtype, [])
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
    result: dict[str, Any] = chat_json(prompt)

    ctx["optimize_result"] = result
    return result


# ==================== 8) 面试题生成 ====================


def step_interview_question_gen(ctx: AgentContext, db: Session) -> dict[str, Any]:
    resume_id = ctx["resume_id"]
    jd_id = ctx["jd_id"]

    resume: Resume = db.get(Resume, resume_id)
    jd: JobDescription = db.get(JobDescription, jd_id)
    resume_json = json.dumps(resume.parsed_json or {}, ensure_ascii=False)
    jd_json = json.dumps(jd.parsed_json or {}, ensure_ascii=False)

    retrievals = ctx.get("retrieval_results", {})
    rag_parts = []
    for dtype in ["interview_q", "skill_model"]:
        results = retrievals.get(dtype, [])
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

    # 容错：chat_json 失败时返回空结构，不阻塞整个工作流
    try:
        result: dict[str, Any] = chat_json(prompt)
    except Exception as e:
        result = {
            "basic": [],
            "project": [],
            "tech": [],
            "scenario": [],
            "error": f"AI 生成面试题失败: {str(e)[:100]}",
            "total_questions": 0,
        }

    ctx["interview_result"] = result
    return result


# ==================== 8.5) 职业规划 ====================


def step_career_planning(ctx: AgentContext, db: Session) -> dict[str, Any]:
    """基于简历、JD、匹配度、行业数据生成个性化职业规划"""
    resume_id = ctx["resume_id"]
    jd_id = ctx["jd_id"]

    resume: Resume = db.get(Resume, resume_id)
    jd: JobDescription = db.get(JobDescription, jd_id)
    if not resume:
        raise ValueError(f"简历不存在: resume_id={resume_id}")
    if not jd:
        raise ValueError(f"岗位不存在: jd_id={jd_id}")

    # parsed_json 可能为空（简历/JD 尚未解析），统一兜底为空 dict 避免 None.get 崩溃
    resume_parsed = resume.parsed_json or {}
    jd_parsed = jd.parsed_json or {}

    # 组装各 Agent 的中间结果
    resume_report = {
        "basic_info": {
            "name": resume_parsed.get("name", ""),
            "years_exp": resume_parsed.get("years_exp", 0),
            "skills": resume_parsed.get("skills", []),
            "current_title": resume_parsed.get("current_title", ""),
            "education": resume_parsed.get("education", ""),
            "major": resume_parsed.get("major", ""),
        },
        "work_experience": resume_parsed.get("work_experience", []),
        "project_experience": resume_parsed.get("project_experience", []),
    }
    job_report = {
        "position_info": {
            "title": jd_parsed.get("title", jd.title),
            "company": jd.company,
            "industry": jd_parsed.get("industry", jd.industry),
            "salary_range": jd.salary_range,
        },
        "required_skills": jd_parsed.get("required_skills", []),
        "key_challenges": jd_parsed.get("key_challenges", []),
    }
    match_report = ctx.get("match_result", {})

    # RAG 行业数据
    retrievals = ctx.get("retrieval_results", {})
    rag_parts = []
    for dtype in ["industry_report", "skill_model", "career_path", "salary_market", "transition_guide"]:
        results = retrievals.get(dtype, [])
        if results:
            rag_parts.append(f"===== {dtype} =====")
            for r in results:
                rag_parts.append(f"【{r.get('doc_title', '')}】{r.get('text', '')[:400]}")
    industry_context = "\n".join(rag_parts) if rag_parts else "暂无行业参考数据"

    from app.prompts.career_agent import CAREER_AGENT_PROMPT

    prompt = render_prompt(
        CAREER_AGENT_PROMPT,
        resume_report=json.dumps(resume_report, ensure_ascii=False),
        job_report=json.dumps(job_report, ensure_ascii=False),
        match_report=json.dumps(match_report, ensure_ascii=False),
        industry_context=industry_context,
    )
    try:
        result: dict[str, Any] = chat_json(prompt)
    except Exception as e:
        result = {
            "current_status": {"level": "", "career_stage": "", "strengths": [], "development_areas": []},
            "skill_gaps": [],
            "visual_roadmap": {"phases": [], "total_duration_months": 0, "career_direction": ""},
            "skill_radar": {"dimensions": []},
            "project_recommendations": [],
            "short_term_plan": {"timeline": "1-3个月", "goals": ["完善技能树"], "actions": []},
            "mid_term_plan": {"timeline": "3-12个月", "goals": ["深入专业领域"], "actions": []},
            "long_term_plan": {"timeline": "1-3年", "goals": ["成为领域专家"], "career_direction": ""},
            "overall_advice": f"AI 规划暂不可用: {str(e)[:60]}",
            "industry_insight": {"current_trends": [], "demanded_skills": [], "career_alternatives": []},
        }

    ctx["career_result"] = result
    return result


# ==================== 9) 自我校验 ====================


def step_self_check(ctx: AgentContext, db: Session) -> dict[str, Any]:
    check_targets = {
        "matching_analysis": ctx.get("match_result"),
        "resume_optimization": ctx.get("optimize_result"),
        "interview_question_generation": ctx.get("interview_result"),
    }

    checks = []
    all_passed = True
    for target, content in check_targets.items():
        # None 表示该步骤被意图识别判定为不需要执行，跳过校验
        if content is None:
            continue
        if not content:
            checks.append(
                {
                    "check_target": target,
                    "passed": False,
                    "score": 0,
                    "issues": [{"severity": "high", "description": "内容为空", "suggestion": "需要重新生成"}],
                    "retry_needed": True,
                }
            )
            all_passed = False
            continue

        prompt = render_prompt(
            AGENT_SELF_CHECK_PROMPT,
            check_target=target,
            content=json.dumps(content, ensure_ascii=False, indent=2)[:3000],
        )
        try:
            result: dict[str, Any] = chat_json(prompt)
        except Exception:
            result = {
                "passed": False,
                "score": 0,
                "issues": [{"severity": "high", "description": "校验AI调用失败"}],
                "retry_needed": True,
            }

        checks.append(
            {
                "check_target": target,
                "passed": result.get("passed", False),
                "score": result.get("score", 0),
                "issues": result.get("issues", []),
                "improvement": result.get("improvement", {}),
                "retry_needed": result.get("retry_needed", False),
            }
        )
        if result.get("retry_needed"):
            all_passed = False

    ctx["self_checks"] = checks
    return {"passed": all_passed, "checks": checks}


# ==================== 10) 最终报告 ====================


def step_final_report(ctx: AgentContext, db: Session) -> dict[str, Any]:
    resume_id = ctx["resume_id"]
    jd_id = ctx["jd_id"]

    resume: Resume = db.get(Resume, resume_id)
    jd: JobDescription = db.get(JobDescription, jd_id)

    prompt = render_prompt(
        AGENT_REPORT_PROMPT,
        resume_summary=_build_resume_summary(resume),
        jd_summary=_build_jd_summary(jd),
        match_result=json.dumps(ctx.get("match_result", {}), ensure_ascii=False, indent=2),
        optimize_result=json.dumps(ctx.get("optimize_result", {}), ensure_ascii=False, indent=2),
        interview_result=json.dumps(ctx.get("interview_result", {}), ensure_ascii=False, indent=2),
        career_result=json.dumps(ctx.get("career_result", {}), ensure_ascii=False, indent=2),
        self_check_result=json.dumps(ctx.get("self_checks", []), ensure_ascii=False, indent=2),
    )
    result: dict[str, Any] = chat_json(prompt)

    ctx["final_report"] = result
    return result


# ==================== 辅助函数 ====================


def _build_resume_summary(resume: Resume | None) -> str:
    if not resume:
        return "无简历信息"
    parsed = resume.parsed_json or {}
    parts = [
        f"姓名: {parsed.get('name', '未知')}",
        f"工作年限: {parsed.get('years_exp', 0)}年",
        f"技能: {', '.join((parsed.get('skills') or [])[:8])}",
        f"当前公司: {parsed.get('current_company', '未知')}",
        f"当前职位: {parsed.get('current_title', '未知')}",
    ]
    return "\n".join(parts)


def _build_jd_summary(jd: JobDescription | None) -> str:
    if not jd:
        return "无JD信息"
    parsed = jd.parsed_json or {}
    parts = [
        f"岗位: {parsed.get('title', jd.title or '未知')}",
        f"公司: {parsed.get('company', jd.company or '未知')}",
        f"地点: {parsed.get('location', '未知')}",
        f"薪资: {parsed.get('salary_range', '未知')}",
        f"必备技能: {', '.join((parsed.get('required_skills') or [])[:8])}",
    ]
    return "\n".join(parts)
