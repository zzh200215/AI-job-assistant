"""
面试会话 REST API
- POST /api/interview/sessions      创建新面试
- GET  /api/interview/sessions      用户面试列表
- GET  /api/interview/sessions/{id} 面试详情（含报告）
- DELETE /api/interview/sessions/{id} 删除面试
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi import Query as QueryParam
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_admin
from app.core.database import SessionLocal, get_db
from app.core.tenant_context import require_tenant, stamp_tenant, tenant_filter
from app.models.history import JobDescription, Resume
from app.models.interview_config import (
    InterviewQuestionBank,
    InterviewReportTemplate,
    InterviewScoringRule,
)
from app.models.interview_question import InterviewQuestion
from app.models.interview_session import InterviewSession
from app.models.user import User
from app.prompts.interview import INTERVIEW_PROMPT
from app.schemas.interview_session import InterviewSessionCreate
from app.services.interview_config_service import (
    get_question_bank,
    list_question_banks,
)
from app.services.interview_evaluation_service import evaluation_payloads
from app.services.llm_service import chat_json
from app.services.rag_service import search_knowledge
from app.services.skill_gap import jd_required_names
from app.utils.job_access import get_accessible_job
from app.utils.response import ERR_PARAM, fail, ok

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/sessions", summary="创建 AI 模拟面试")
async def create_session(
    payload: InterviewSessionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant=Depends(require_tenant),
):
    """Create a usable interview immediately, then personalize untouched questions in background."""
    resume = (
        db.query(Resume)
        .filter(
            Resume.id == payload.resume_id,
            Resume.user_id == current_user.id,
            Resume.is_deleted == 0,
        )
        .first()
    )
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

    # T3-2：租户题库配置优先（自定义静态题覆盖内置 starter 题库）
    bank = get_question_bank(db, tenant.tenant_id, payload.interview_type)
    custom_questions = bank.questions if (bank is not None and bank.questions) else None
    ordered_questions = _fallback_questions(
        jd_title,
        required_skills,
        payload.interview_type,
        custom_questions=custom_questions,
    )

    session = stamp_tenant(
        InterviewSession(
            user_id=current_user.id,
            resume_id=payload.resume_id,
            jd_id=payload.jd_id,
            interview_type=payload.interview_type,
            status="created",
            questions=ordered_questions,
            messages=[],
            evaluation={},
            evaluation_status="idle",
            memory_snapshot={"question_generation": {"status": "pending"}},
            total_questions=len(ordered_questions),
            answered_count=0,
            timeout_count=0,
        )
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Retrieval and the remote model used to run before this response was sent.
    # A slow provider could therefore leave the user staring at the start button
    # for minutes. The fallback set above is complete and safe to start with.
    background_tasks.add_task(
        _personalize_unstarted_questions,
        session.id,
        resume_json,
        jd_json,
        jd_title,
        required_skills,
        payload.interview_type,
        search_types,
    )

    return ok(
        data=_serialize_session(session, db, resume=resume, jd=jd),
        message=f"面试已创建，共 {len(ordered_questions)} 道题，正在补充个性化题目",
    )


@router.get("/sessions", summary="用户面试列表")
async def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sessions = (
        db.query(InterviewSession)
        .filter(
            tenant_filter(InterviewSession),
            InterviewSession.user_id == current_user.id,
        )
        .order_by(InterviewSession.created_at.desc())
        .all()
    )

    resume_ids = {item.resume_id for item in sessions if item.resume_id}
    jd_ids = {item.jd_id for item in sessions if item.jd_id}
    resumes = {item.id: item for item in db.query(Resume).filter(Resume.id.in_(resume_ids)).all()} if resume_ids else {}
    jds = (
        {item.id: item for item in db.query(JobDescription).filter(JobDescription.id.in_(jd_ids)).all()}
        if jd_ids
        else {}
    )

    return ok(
        data=[
            _serialize_session(item, db, resume=resumes.get(item.resume_id), jd=jds.get(item.jd_id))
            for item in sessions
        ]
    )


@router.get("/sessions/{session_id}", summary="面试详情（含报告）")
async def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(InterviewSession)
        .filter(
            tenant_filter(InterviewSession),
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id,
        )
        .first()
    )
    if not session:
        return fail(message="面试不存在或无权限", code=ERR_PARAM)
    return ok(data=_serialize_session(session, db))


@router.get("/sessions/{session_id}/evaluations", summary="获取异步逐题评分状态")
async def get_session_evaluations(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(InterviewSession)
        .filter(
            tenant_filter(InterviewSession),
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id,
        )
        .first()
    )
    if not session:
        return fail(message="面试不存在或无权限", code=ERR_PARAM)
    return ok(
        {
            "items": evaluation_payloads(db, session_id),
            "evaluation_status": session.evaluation_status or "idle",
            "memory_snapshot": session.memory_snapshot or {},
        }
    )


@router.delete("/sessions/{session_id}", summary="删除面试")
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = (
        db.query(InterviewSession)
        .filter(
            tenant_filter(InterviewSession),
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user.id,
        )
        .first()
    )
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
) -> dict[str, Any]:
    resume = resume or (db.query(Resume).filter(Resume.id == session.resume_id).first() if session.resume_id else None)
    jd = jd or (db.query(JobDescription).filter(JobDescription.id == session.jd_id).first() if session.jd_id else None)

    base = session.to_dict()
    base["resume_summary"] = _build_resume_summary(resume)
    base["jd_summary"] = _build_jd_summary(jd)
    base["question_stats"] = _question_stats(base.get("questions") or [])
    base["turn_evaluations"] = evaluation_payloads(db, session.id)
    return base


def _fallback_questions(
    title: str,
    required_skills: list[str],
    interview_type: str,
    custom_questions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return a full question set that can start without a model round trip.

    T3-2：custom_questions 来自租户题库配置（InterviewQuestionBank.questions），
    非空时完全替代内置 starter 题库；否则回落内置模板。
    """
    if custom_questions:
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(custom_questions, start=1):
            q_type = str(item.get("type") or "tech")
            text = str(item.get("question") or item.get("q") or "").strip()
            if not text:
                continue
            normalized.append(
                {
                    "id": index,
                    "type": q_type,
                    "category": _map_category(q_type),
                    "question": text,
                    "intent": str(item.get("intent") or ""),
                    "ref_answer": str(item.get("ref_answer") or item.get("expected_answer") or ""),
                    "source": "tenant_config",
                }
            )
        return normalized[:10]

    role = title or "目标岗位"
    skills = "、".join(required_skills[:3]) or "岗位核心能力"
    templates_by_type = {
        "tech": [
            ("basic", f"请用 2 分钟介绍一下你与「{role}」最相关的经历。", "表达与岗位匹配", "按背景、关键项目、岗位契合度组织回答。"),
            ("tech", f"围绕 {skills}，你最熟悉的一个技术难点是什么？如何定位并解决？", "技术深度", "说明问题边界、方案取舍、结果与复盘。"),
            ("project", "挑选一个最有挑战的项目，说明你的职责、关键决策和量化结果。", "项目影响力", "使用 STAR 结构，突出本人贡献。"),
            ("tech", "当系统出现性能或稳定性问题时，你会如何定位、止损和复盘？", "工程方法", "从监控、定位、修复、预防四步回答。"),
            ("scenario", "如果需求目标不清晰且时间有限，你会如何推进交付？", "协作与判断", "说明澄清优先级、风险同步和分阶段交付。"),
            ("tech", f"你会如何验证 {skills} 相关方案在生产环境中的效果？", "验证能力", "覆盖指标、灰度、回滚和长期监控。"),
            ("project", "描述一次你与产品、测试或其他工程角色意见不一致的经历。", "跨团队协作", "说明分歧、依据、决策和最终结果。"),
            ("scenario", "面对线上紧急故障，你会如何组织沟通并安排后续动作？", "应急处理", "先恢复服务，再同步影响并形成复盘。"),
            ("basic", f"你为什么选择「{role}」这个机会？", "求职动机", "结合岗位价值、能力积累和长期方向。"),
            ("scenario", "入职后的前 90 天，你会如何建立业务理解并产出成果？", "成长计划", "给出可衡量的学习、协作和交付计划。"),
        ],
        "hr": [
            ("basic", "请用 2 分钟做自我介绍，并说明下一份工作的核心期待。", "表达与动机", "突出经历主线与岗位匹配点。"),
            ("basic", f"你为什么对「{role}」感兴趣？", "求职动机", "结合业务理解与个人目标回答。"),
            ("project", "讲一次你推动他人接受新方案或改变协作方式的经历。", "影响力", "说明阻力、沟通方法和结果。"),
            ("scenario", "当优先级频繁变化时，你如何保证工作质量和预期管理？", "适应能力", "说明取舍标准和同步机制。"),
            ("project", "讲一次你从失败或反馈中调整做法的经历。", "成长性", "具体说明反思和后续改变。"),
            ("scenario", "如果团队成员交付延迟影响你，你会怎么处理？", "协作方式", "先澄清事实，再共同制定恢复计划。"),
            ("basic", "你最看重什么样的团队氛围和管理方式？", "文化匹配", "给出清晰且务实的偏好。"),
            ("project", "描述一次在资源受限条件下完成重要目标的经历。", "结果导向", "说明约束、行动和结果。"),
            ("scenario", "遇到不熟悉的任务时，你如何快速建立判断并取得帮助？", "学习能力", "说明学习路径和验证方式。"),
            ("basic", "未来两到三年你希望在哪些能力上取得进展？", "职业规划", "与岗位发展路径保持一致。"),
        ],
    }
    templates = templates_by_type.get(interview_type, templates_by_type["tech"])
    if interview_type == "comprehensive":
        templates = templates_by_type["tech"][:5] + templates_by_type["hr"][2:7]
    return [
        {
            "id": index,
            "type": q_type,
            "category": _map_category(q_type),
            "question": question,
            "intent": intent,
            "ref_answer": ref_answer,
            "source": "starter",
        }
        for index, (q_type, question, intent, ref_answer) in enumerate(templates, start=1)
    ]


def _normalize_generated_questions(raw: dict[str, Any], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize model JSON and retain fallback questions for any missing slots."""
    generated: list[dict[str, Any]] = []
    for default_type in ("basic", "tech", "project", "scenario"):
        for item in raw.get(default_type, []) or []:
            text = (item.get("q") or item.get("question") or "").strip()
            if not text:
                continue
            generated.append(
                {
                    "type": default_type,
                    "category": _map_category(default_type),
                    "question": text,
                    "intent": item.get("intent", ""),
                    "ref_answer": item.get("ref_answer") or item.get("expected_answer") or "",
                    "source": "personalized",
                }
            )

    for item in raw.get("questions", []) or []:
        if len(generated) >= 10:
            break
        text = (item.get("q") or item.get("question") or "").strip()
        if not text:
            continue
        q_type = item.get("type") or "tech"
        generated.append(
            {
                "type": q_type,
                "category": _map_category(q_type),
                "question": text,
                "intent": item.get("intent", ""),
                "ref_answer": item.get("ref_answer") or item.get("expected_answer") or "",
                "source": "personalized",
            }
        )

    merged = (generated + fallback)[:10]
    for index, item in enumerate(merged, start=1):
        item["id"] = index
    return merged


def _build_personalized_prompt(
    *,
    resume_json: dict[str, Any],
    jd_json: dict[str, Any],
    jd_title: str,
    required_skills: list[str],
    interview_type: str,
    search_types: list[str],
    prompt_template: str = "",
    db: Session | None = None,
    user_id: int | None = None,
) -> str:
    rag_parts: list[str] = []
    for doc_type in search_types:
        results = search_knowledge(
            f"{jd_title} {' '.join(required_skills[:5])}".strip(),
            doc_type=doc_type,
            top_k=3,
            db=db,
            user_id=user_id,
        )
        for item in results:
            rag_parts.append(f"《{item.get('doc_title', '')}》{item.get('text', '')[:300]}")

    type_instructions = {
        "tech": "重点考察技术深度、系统设计、编码思路，技术题和项目题占比更高。",
        "hr": "重点考察表达、动机、协作、文化匹配，基础题和场景题占比更高。",
        "comprehensive": "兼顾技术、项目、HR、场景四类题，整体分布更均衡。",
    }
    # T3-2：租户题库配置的 prompt_template 覆盖内置题型指令
    custom_instruction = prompt_template.strip()
    if custom_instruction:
        type_instructions[interview_type] = custom_instruction
    prompt = INTERVIEW_PROMPT.format(
        rag_context="\n".join(rag_parts),
        resume_json=json.dumps(resume_json, ensure_ascii=False),
        jd_json=json.dumps(jd_json, ensure_ascii=False),
    )
    return (
        f"{prompt}\n【特别要求】{type_instructions.get(interview_type, type_instructions['tech'])}"
        "\n请生成 10 道题，每类至少 2 道，并按真实面试顺序排列。"
    )


def _personalize_unstarted_questions(
    session_id: int,
    resume_json: dict[str, Any],
    jd_json: dict[str, Any],
    jd_title: str,
    required_skills: list[str],
    interview_type: str,
    search_types: list[str],
) -> None:
    """Enrich a session without ever delaying its creation response."""
    db = SessionLocal()
    try:
        session = db.get(InterviewSession, session_id)
        if not session or session.status == "completed":
            return

        fallback = list(session.questions or _fallback_questions(jd_title, required_skills, interview_type))
        # T3-2：后台个性化同样读租户题库配置（session.tenant_id 已打标）
        bank = get_question_bank(db, session.tenant_id, interview_type)
        if bank is not None and bank.questions:
            # T3-2：租户自定义静态题库优先。create_session 已用自定义题建会话，
            # 后台 LLM 个性化不得覆盖，否则自定义题库会被换成 10 道通用题。
            snapshot = dict(session.memory_snapshot or {})
            snapshot["question_generation"] = {"status": "custom_bank"}
            session.memory_snapshot = snapshot
            db.commit()
            return
        prompt_template = bank.prompt_template if bank is not None else ""
        prompt = _build_personalized_prompt(
            resume_json=resume_json,
            jd_json=jd_json,
            jd_title=jd_title,
            required_skills=required_skills,
            interview_type=interview_type,
            search_types=search_types,
            prompt_template=prompt_template,
            db=db,
            user_id=session.user_id if session else None,
        )
        personalized = _normalize_generated_questions(chat_json(prompt), fallback)

        started_rounds = [
            int((message.get("metadata") or {}).get("round") or 0)
            for message in (session.messages or [])
            if message.get("type") == "question" and not (message.get("metadata") or {}).get("is_follow_up")
        ]
        first_unstarted = max(started_rounds, default=0)
        current_questions = list(session.questions or [])
        current_questions[first_unstarted:] = personalized[first_unstarted:]
        session.questions = current_questions[:10]
        session.total_questions = len(session.questions)
        snapshot = dict(session.memory_snapshot or {})
        snapshot["question_generation"] = {"status": "completed"}
        session.memory_snapshot = snapshot
        db.commit()
    except Exception:
        logger.exception("Interview question personalization failed: session_id=%s", session_id)
        if session := db.get(InterviewSession, session_id):
            snapshot = dict(session.memory_snapshot or {})
            snapshot["question_generation"] = {"status": "fallback"}
            session.memory_snapshot = snapshot
            db.commit()
    finally:
        db.close()


def _build_resume_summary(resume: Resume | None) -> dict[str, Any]:
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


def _build_jd_summary(jd: JobDescription | None) -> dict[str, Any]:
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


def _extract_skills(jd: JobDescription) -> list[str]:
    """Required skills in the posting's own wording — the shared fallback chain in
    `skill_gap` decides *which* field counts; the names are passed through as
    written because they go into a prompt and onto the UI."""
    parsed = jd.parsed_json or {}
    names = jd_required_names(parsed) or [str(tag) for tag in (jd.skill_tags or []) if str(tag).strip()]
    return [name.strip() for name in names if name.strip()]


def _question_stats(questions: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, int] = {}
    types: dict[str, int] = {}
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


# ============================================================
# 面试题库
# ============================================================


@router.get("/question-bank", summary="浏览面试题库")
async def browse_question_bank(
    category: str = QueryParam("", description="分类过滤: basic/tech/project/scenario/behavioral"),
    sub_category: str = QueryParam("", description="子分类过滤"),
    difficulty: str = QueryParam("", description="难度过滤: easy/medium/hard"),
    keyword: str = QueryParam("", description="关键词搜索"),
    page: int = QueryParam(1, ge=1),
    page_size: int = QueryParam(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(InterviewQuestion)
    if category:
        q = q.filter(InterviewQuestion.category == category)
    if sub_category:
        q = q.filter(InterviewQuestion.sub_category == sub_category)
    if difficulty:
        q = q.filter(InterviewQuestion.difficulty == difficulty)
    if keyword:
        q = q.filter(InterviewQuestion.question.contains(keyword))

    total = q.count()
    items = (
        q.order_by(InterviewQuestion.use_count.desc(), InterviewQuestion.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok({"total": total, "items": [item.to_dict() for item in items]})


@router.get("/question-bank/categories", summary="获取题库分类统计")
async def question_bank_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(
            InterviewQuestion.category,
            InterviewQuestion.sub_category,
            InterviewQuestion.difficulty,
            db.func.count(InterviewQuestion.id),
        )
        .group_by(
            InterviewQuestion.category,
            InterviewQuestion.sub_category,
            InterviewQuestion.difficulty,
        )
        .all()
    )
    categories = {}
    for category, sub_category, difficulty, count in rows:
        cat = categories.setdefault(category, {"name": category, "sub_categories": {}, "total": 0})
        cat["total"] += count
        if sub_category:
            sub = cat["sub_categories"].setdefault(sub_category, {"name": sub_category, "total": 0, "difficulties": {}})
            sub["total"] += count
            sub["difficulties"][difficulty] = count
    return ok(list(categories.values()))


@router.get("/preparation/{jd_id}", summary="针对JD的面试准备建议")
async def interview_preparation(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据JD分析，给出针对性的面试准备建议和推荐练习题。"""
    from app.utils.job_access import get_accessible_job

    jd = get_accessible_job(db, jd_id, current_user)
    if not jd:
        return fail(message="岗位不存在或无权限", code=ERR_PARAM)

    jd_json = jd.parsed_json or {}
    required_skills = _extract_skills(jd)
    title = jd_json.get("title") or jd.title or ""

    # 从题库中匹配相关题目
    related_questions = []
    if required_skills:
        from sqlalchemy import or_

        skill_filters = [InterviewQuestion.question.contains(skill) for skill in required_skills[:5]]
        skill_filters += [InterviewQuestion.sub_category.contains(skill) for skill in required_skills[:5]]
        related_questions = (
            db.query(InterviewQuestion)
            .filter(or_(*skill_filters))
            .order_by(InterviewQuestion.use_count.desc())
            .limit(10)
            .all()
        )

    # 通用高频题
    common_questions = (
        db.query(InterviewQuestion)
        .filter(InterviewQuestion.category.in_(["basic", "behavioral"]))
        .order_by(InterviewQuestion.use_count.desc())
        .limit(5)
        .all()
    )

    # 用户历史面试表现分析
    past_sessions = (
        db.query(InterviewSession)
        .filter(
            tenant_filter(InterviewSession),
            InterviewSession.user_id == current_user.id,
            InterviewSession.status == "completed",
        )
        .order_by(InterviewSession.completed_at.desc())
        .limit(5)
        .all()
    )

    performance = _analyze_past_performance(past_sessions)

    # 生成准备建议
    suggestions = _build_preparation_suggestions(
        title=title,
        required_skills=required_skills,
        performance=performance,
    )

    return ok(
        {
            "jd": {
                "id": jd.id,
                "title": title,
                "company": jd.company,
                "required_skills": required_skills,
            },
            "suggestions": suggestions,
            "related_questions": [q.to_dict() for q in related_questions],
            "common_questions": [q.to_dict() for q in common_questions],
            "past_performance": performance,
        }
    )


@router.get("/performance", summary="面试表现趋势分析")
async def interview_performance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分析用户所有面试的表现趋势。"""
    sessions = (
        db.query(InterviewSession)
        .filter(
            tenant_filter(InterviewSession),
            InterviewSession.user_id == current_user.id,
            InterviewSession.status == "completed",
        )
        .order_by(InterviewSession.completed_at.asc())
        .all()
    )

    if not sessions:
        return ok(
            {
                "total_sessions": 0,
                "trend": [],
                "strengths": [],
                "weaknesses": [],
                "summary": "还没有完成过模拟面试，建议先创建一次面试体验。",
            }
        )

    trend = []
    all_dimension_scores = {"completeness": [], "accuracy": [], "depth": [], "expression": []}

    for session in sessions:
        evaluation = session.evaluation or {}
        dim_scores = evaluation.get("dimension_scores", {})
        overall = evaluation.get("overall_score", 0)

        for dim in all_dimension_scores:
            val = dim_scores.get(dim, 0)
            if val:
                all_dimension_scores[dim].append(val)

        trend.append(
            {
                "session_id": session.id,
                "interview_type": session.interview_type,
                "overall_score": overall,
                "dimension_scores": dim_scores,
                "answered_questions": evaluation.get("answered_questions", 0),
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            }
        )

    # 分析维度强弱
    avg_dims = {}
    for dim, scores in all_dimension_scores.items():
        avg_dims[dim] = round(sum(scores) / len(scores), 1) if scores else 0

    sorted_dims = sorted(avg_dims.items(), key=lambda x: x[1])
    weaknesses = [{"dimension": d, "avg_score": s} for d, s in sorted_dims if s > 0 and s < 65][:2]
    strengths = [{"dimension": d, "avg_score": s} for d, s in reversed(sorted_dims) if s >= 70][:2]

    overall_scores = [t["overall_score"] for t in trend if t["overall_score"] > 0]
    avg_overall = round(sum(overall_scores) / len(overall_scores), 1) if overall_scores else 0

    dim_labels = {
        "completeness": "完整性",
        "accuracy": "准确性",
        "depth": "深度",
        "expression": "表达力",
    }

    return ok(
        {
            "total_sessions": len(sessions),
            "avg_overall_score": avg_overall,
            "trend": trend,
            "dimension_averages": avg_dims,
            "strengths": [
                {"dimension": dim_labels.get(s["dimension"], s["dimension"]), "avg_score": s["avg_score"]}
                for s in strengths
            ],
            "weaknesses": [
                {"dimension": dim_labels.get(w["dimension"], w["dimension"]), "avg_score": w["avg_score"]}
                for w in weaknesses
            ],
            "improvement_priority": [
                f"重点提升「{dim_labels.get(w['dimension'], w['dimension'])}」维度，当前均分 {w['avg_score']}"
                for w in weaknesses
            ],
        }
    )


def _analyze_past_performance(sessions):
    """分析历史面试表现"""
    if not sessions:
        return {"has_data": False}

    overall_scores = []
    dim_totals = {"completeness": [], "accuracy": [], "depth": [], "expression": []}

    for session in sessions:
        evaluation = session.evaluation or {}
        score = evaluation.get("overall_score", 0)
        if score > 0:
            overall_scores.append(score)
        for dim in dim_totals:
            val = evaluation.get("dimension_scores", {}).get(dim, 0)
            if val:
                dim_totals[dim].append(val)

    avg_overall = round(sum(overall_scores) / len(overall_scores), 1) if overall_scores else 0
    dim_avgs = {dim: round(sum(vals) / len(vals), 1) for dim, vals in dim_totals.items() if vals}

    weakest_dim = min(dim_avgs, key=dim_avgs.get) if dim_avgs else None
    strongest_dim = max(dim_avgs, key=dim_avgs.get) if dim_avgs else None

    return {
        "has_data": True,
        "total_sessions": len(sessions),
        "avg_overall_score": avg_overall,
        "dimension_averages": dim_avgs,
        "weakest_dimension": weakest_dim,
        "strongest_dimension": strongest_dim,
    }


def _build_preparation_suggestions(title, required_skills, performance):
    """生成面试准备建议"""
    suggestions = []

    if required_skills:
        top_skills = required_skills[:5]
        suggestions.append(f"该岗位「{title}」核心技术栈为 {', '.join(top_skills)}，建议重点复习这些领域的常见面试题")

    if performance.get("has_data"):
        weakest = performance.get("weakest_dimension")
        dim_labels = {
            "completeness": "回答完整性",
            "accuracy": "准确性",
            "depth": "回答深度",
            "expression": "表达力",
        }
        if weakest:
            suggestions.append(
                f"根据你的历史面试数据，「{dim_labels.get(weakest, weakest)}」是最弱维度"
                f"（均分 {performance['dimension_averages'].get(weakest, 0)}），建议针对性练习"
            )
        avg = performance.get("avg_overall_score", 0)
        if avg < 60:
            suggestions.append("历史面试均分偏低，建议从基础题开始逐步提升，先确保每题覆盖核心要点")
        elif avg < 75:
            suggestions.append("基础已较扎实，建议多练习场景题和项目深挖，提升回答深度")
        else:
            suggestions.append("表现不错！可以挑战高难度题，关注系统性设计和架构类问题")
    else:
        suggestions.append("建议先完成1-2次模拟面试，系统会根据你的表现给出更精准的建议")

    suggestions.append("面试前30分钟快速浏览JD中的岗位职责，准备好与每个要求对应的经历或理解")

    return suggestions

# ============================================================
# T3-2 面试配置：题型配置查询 + 管理端配置
# ============================================================


@router.get("/config/types", summary="获取当前租户可见的面试题型配置（T3-2）")
def list_tenant_bank_types(
    db: Session = Depends(get_db),
    tenant=Depends(require_tenant),
):
    """返回当前租户可见的题型配置（租户自定义 → 平台默认 → 内置回落），前端设置页使用。"""
    return ok({"items": list_question_banks(db, tenant.tenant_id)})


@router.put("/admin/interview-config", summary="管理员：配置租户面试题库/评分规则/报告模板（T3-2）")
def upsert_interview_config(
    payload: dict,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """按 config_type 配置租户面试配置：

    - question_bank:  {"tenant_id", "type", "title"?, "prompt_template"?, "questions"?, "tags"?, "is_active"?}
    - scoring_rules:  {"tenant_id", "rules": [{"dimension","label"?, "weight"}]}（批量重建）
    - report_template: {"tenant_id", "template"}
    dimension 限定内置四维：completeness/accuracy/depth/expression（与逐题评分存储列一致）。
    """
    config_type = payload.get("config_type", "")
    tenant_id = payload.get("tenant_id")
    if not tenant_id or config_type not in ("question_bank", "scoring_rules", "report_template"):
        return fail(message="config_type(question_bank/scoring_rules/report_template) 与 tenant_id 必填", code=ERR_PARAM)

    if config_type == "question_bank":
        bank_type = payload.get("type", "")
        if not bank_type:
            return fail(message="type 必填", code=ERR_PARAM)
        row = (
            db.query(InterviewQuestionBank)
            .filter(
                InterviewQuestionBank.tenant_id == tenant_id,
                InterviewQuestionBank.type == bank_type,
            )
            .first()
        )
        if row is None:
            row = InterviewQuestionBank(tenant_id=tenant_id, type=bank_type)
            db.add(row)
        if "title" in payload:
            row.title = str(payload["title"])
        if "prompt_template" in payload:
            row.prompt_template = str(payload["prompt_template"])
        if "questions" in payload:
            row.questions = payload["questions"] if isinstance(payload["questions"], list) else None
        if "tags" in payload and isinstance(payload["tags"], list):
            row.tags = payload["tags"]
        if "is_active" in payload:
            row.is_active = 1 if payload["is_active"] else 0
        db.commit()
        db.refresh(row)
        return ok(
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "type": row.type,
                "title": row.title,
                "question_count": len(row.questions or []),
            }
        )

    if config_type == "scoring_rules":
        rules = payload.get("rules")
        if not isinstance(rules, list) or not rules:
            return fail(message="rules 必填（非空列表）", code=ERR_PARAM)
        allowed = {"completeness", "accuracy", "depth", "expression"}
        for rule in rules:
            if rule.get("dimension") not in allowed:
                return fail(message=f"dimension 仅支持 {sorted(allowed)}", code=ERR_PARAM)
        # 批量重建：删除该租户全部规则后插入（简单且原子）
        db.query(InterviewScoringRule).filter(InterviewScoringRule.tenant_id == tenant_id).delete()
        for index, rule in enumerate(rules):
            db.add(
                InterviewScoringRule(
                    tenant_id=tenant_id,
                    dimension=rule["dimension"],
                    label=str(rule.get("label") or rule["dimension"]),
                    weight=float(rule.get("weight") or 0),
                    sort_order=index,
                )
            )
        db.commit()
        return ok({"tenant_id": tenant_id, "rule_count": len(rules)})

    # report_template
    row = (
        db.query(InterviewReportTemplate)
        .filter(InterviewReportTemplate.tenant_id == tenant_id)
        .first()
    )
    if row is None:
        row = InterviewReportTemplate(tenant_id=tenant_id)
        db.add(row)
    row.template = str(payload.get("template") or "")
    if "is_active" in payload:
        row.is_active = 1 if payload["is_active"] else 0
    db.commit()
    db.refresh(row)
    return ok({"id": row.id, "tenant_id": row.tenant_id, "template_length": len(row.template or "")})
