# -*- coding: utf-8 -*-
"""
面试会话 REST API
- POST /api/interview/sessions      创建新面试
- GET  /api/interview/sessions      用户面试列表
- GET  /api/interview/sessions/{id} 面试详情（含报告）
- DELETE /api/interview/sessions/{id} 删除面试
"""
import json
import traceback
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import JobDescription, Resume
from app.models.interview_session import InterviewSession
from app.models.user import User
from app.prompts.interview import INTERVIEW_PROMPT
from app.schemas.interview_session import InterviewSessionCreate
from app.services.llm_service import chat_json
from app.services.rag_service import search_knowledge
from app.utils.job_access import get_accessible_job
from app.utils.response import ERR_COMMON, ERR_PARAM, fail, ok

router = APIRouter()


@router.post("/sessions", summary="创建 AI 模拟面试")
async def create_session(
    payload: InterviewSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建面试会话并自动生成题目。"""
    resume = db.query(Resume).filter(
        Resume.id == payload.resume_id,
        Resume.user_id == current_user.id,
        Resume.is_deleted == 0,
    ).first()
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    jd = get_accessible_job(db, payload.jd_id, current_user)
    if not jd:
        return fail(message="岗位 JD 不存在或无权限", code=ERR_PARAM)

    resume_json = resume.parsed_json or {}
    jd_json = jd.parsed_json or {}
    jd_title = jd_json.get("title") or jd.title or ""
    required_skills = _extract_skills(jd)

    type_hints = {
        "tech": ["interview_q", "skill_model"],
        "hr": ["interview_q"],
        "comprehensive": ["interview_q", "skill_model"],
    }
    search_types = type_hints.get(payload.interview_type, ["interview_q", "skill_model"])

    rag_parts: List[str] = []
    for doc_type in search_types:
        results = search_knowledge(f"{jd_title} {' '.join(required_skills[:5])}".strip(), doc_type=doc_type, top_k=3)
        if not results:
            continue
        rag_parts.append(f"===== {doc_type} =====")
        for item in results:
            rag_parts.append(f"《{item.get('doc_title', '')}》{item.get('text', '')[:300]}")
    rag_context = "\n".join(rag_parts)

    type_instructions = {
        "tech": "重点考察技术深度、系统设计、编码思路，技术题和项目题占比更高。",
        "hr": "重点考察表达、动机、协作、文化匹配，基础题和场景题占比更高。",
        "comprehensive": "兼顾技术、项目、HR、场景四类题，整体分布更均衡。",
    }
    prompt = INTERVIEW_PROMPT.format(
        rag_context=rag_context,
        resume_json=json.dumps(resume_json, ensure_ascii=False),
        jd_json=json.dumps(jd_json, ensure_ascii=False),
    )
    prompt += (
        f"\n【特别要求】{type_instructions.get(payload.interview_type, type_instructions['tech'])}"
        "\n请生成 10 道题，每类至少 2 道，并按真实面试顺序排列。"
    )

    try:
        questions_data = chat_json(prompt)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"生成面试题失败: {str(exc)}", code=ERR_COMMON)

    ordered_questions: List[Dict[str, Any]] = []
    for q_type in ["basic", "tech", "project", "scenario"]:
        for item in questions_data.get(q_type, []) or []:
            question_text = item.get("q") or item.get("question") or ""
            if not question_text:
                continue
            ordered_questions.append({
                "id": len(ordered_questions) + 1,
                "type": q_type,
                "category": _map_category(q_type),
                "question": question_text,
                "intent": item.get("intent", ""),
                "ref_answer": item.get("ref_answer") or item.get("expected_answer") or "",
            })

    if len(ordered_questions) < 10:
        extra_prompt = (
            f"请为以下 {payload.interview_type} 面试补充额外问题。"
            f"简历: {json.dumps(resume_json, ensure_ascii=False)[:300]}。"
            f"JD: {json.dumps(jd_json, ensure_ascii=False)[:300]}。"
            "输出 JSON {'questions':[{'q':'...','intent':'...','ref_answer':'...','type':'tech'}]}"
        )
        try:
            extra = chat_json(extra_prompt)
            for item in extra.get("questions", []) or []:
                if len(ordered_questions) >= 10:
                    break
                ordered_questions.append({
                    "id": len(ordered_questions) + 1,
                    "type": item.get("type", "tech"),
                    "category": _map_category(item.get("type", "tech")),
                    "question": item.get("q") or item.get("question") or "",
                    "intent": item.get("intent", ""),
                    "ref_answer": item.get("ref_answer", ""),
                })
        except Exception:
            pass

    session = InterviewSession(
        user_id=current_user.id,
        resume_id=payload.resume_id,
        jd_id=payload.jd_id,
        interview_type=payload.interview_type,
        status="created",
        questions=ordered_questions,
        messages=[],
        evaluation={},
        total_questions=len(ordered_questions),
        answered_count=0,
        timeout_count=0,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return ok(
        data=_serialize_session(session, db, resume=resume, jd=jd),
        message=f"面试已创建，共 {len(ordered_questions)} 道题",
    )


@router.get("/sessions", summary="用户面试列表")
async def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == current_user.id)
        .order_by(InterviewSession.created_at.desc())
        .all()
    )

    resume_ids = {item.resume_id for item in sessions if item.resume_id}
    jd_ids = {item.jd_id for item in sessions if item.jd_id}
    resumes = {
        item.id: item for item in db.query(Resume).filter(Resume.id.in_(resume_ids)).all()
    } if resume_ids else {}
    jds = {
        item.id: item for item in db.query(JobDescription).filter(JobDescription.id.in_(jd_ids)).all()
    } if jd_ids else {}

    return ok(data=[
        _serialize_session(item, db, resume=resumes.get(item.resume_id), jd=jds.get(item.jd_id))
        for item in sessions
    ])


@router.get("/sessions/{session_id}", summary="面试详情（含报告）")
async def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(InterviewSession).filter(
        InterviewSession.id == session_id,
        InterviewSession.user_id == current_user.id,
    ).first()
    if not session:
        return fail(message="面试不存在或无权限", code=ERR_PARAM)
    return ok(data=_serialize_session(session, db))


@router.delete("/sessions/{session_id}", summary="删除面试")
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(InterviewSession).filter(
        InterviewSession.id == session_id,
        InterviewSession.user_id == current_user.id,
    ).first()
    if not session:
        return fail(message="面试不存在或无权限", code=ERR_PARAM)
    db.delete(session)
    db.commit()
    return ok(message="面试已删除")


def _serialize_session(
    session: InterviewSession,
    db: Session,
    resume: Resume | None = None,
    jd: JobDescription | None = None,
) -> Dict[str, Any]:
    resume = resume or (db.query(Resume).filter(Resume.id == session.resume_id).first() if session.resume_id else None)
    jd = jd or (db.query(JobDescription).filter(JobDescription.id == session.jd_id).first() if session.jd_id else None)

    base = session.to_dict()
    base["resume_summary"] = _build_resume_summary(resume)
    base["jd_summary"] = _build_jd_summary(jd)
    base["question_stats"] = _question_stats(base.get("questions") or [])
    return base


def _build_resume_summary(resume: Resume | None) -> Dict[str, Any]:
    if not resume:
        return {}
    parsed = resume.parsed_json or {}
    return {
        "id": resume.id,
        "name": resume.name or resume.file_name,
        "file_name": resume.file_name,
        "years_exp": resume.years_exp,
        "current_title": parsed.get("current_title") or parsed.get("target_position") or "",
        "skills": parsed.get("skills") or parsed.get("core_skills") or [],
        "highlights": parsed.get("highlights") or parsed.get("project_highlights") or [],
    }


def _build_jd_summary(jd: JobDescription | None) -> Dict[str, Any]:
    if not jd:
        return {}
    parsed = jd.parsed_json or {}
    return {
        "id": jd.id,
        "title": jd.title,
        "company": jd.company,
        "location": jd.location,
        "salary_range": jd.salary_range,
        "industry": jd.industry,
        "required_skills": _extract_skills(jd),
        "responsibilities": parsed.get("responsibilities") or parsed.get("job_responsibilities") or [],
    }


def _extract_skills(jd: JobDescription) -> List[str]:
    parsed = jd.parsed_json or {}
    skills = parsed.get("required_skills") or parsed.get("skills") or jd.skill_tags or []
    if isinstance(skills, str):
        return [item.strip() for item in skills.split(",") if item.strip()]
    return [str(item).strip() for item in skills if str(item).strip()]


def _question_stats(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    categories: Dict[str, int] = {}
    types: Dict[str, int] = {}
    for item in questions:
        cat = item.get("category") or "通用"
        q_type = item.get("type") or "general"
        categories[cat] = categories.get(cat, 0) + 1
        types[q_type] = types.get(q_type, 0) + 1
    return {
        "total": len(questions),
        "categories": categories,
        "types": types,
    }


def _map_category(q_type: str) -> str:
    mapping = {
        "basic": "通用/HR",
        "tech": "技术基础",
        "project": "项目经验",
        "scenario": "场景应对",
    }
    return mapping.get(q_type, "通用")
