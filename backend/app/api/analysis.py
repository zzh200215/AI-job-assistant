"""Analysis APIs for smart matching, optimization, and references."""

import json
import traceback

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.agent import AgentStepLog, AgentTask
from app.models.history import AnalysisRecord, Resume
from app.models.user import User
from app.orchestration.protocol import normalize_step_name
from app.schemas.analysis import ExplainMatchReq, FullAnalysisReq, MatchReq
from app.services import interview_service, match_service, optimize_service
from app.services.analysis_service import run_smart_analysis
from app.services.match_explainer_service import MatchExplainer
from app.services.rag_service import get_knowledge_references
from app.services.skill_gap import build_skill_gap, jd_skill_union, resume_skill_names
from app.utils.http_errors import api_error
from app.utils.job_access import get_accessible_job
from app.utils.response import ERR_AI, ERR_COMMON, ERR_DB, ERR_PARAM, fail, ok


def _deep_parse_json(obj):
    """递归解析对象中所有 JSON 字符串（兼容 LLM 双重序列化或 DB 驱动差异）"""
    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            return _deep_parse_json(parsed)
        except Exception:
            return obj
    if isinstance(obj, dict):
        return {k: _deep_parse_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_parse_json(i) for i in obj]
    return obj


def _score_value(value, default=0):
    """Return a numeric score from either a plain number or {'score': number}."""
    if isinstance(value, dict):
        value = value.get("score", default)
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _normalize_dimension_scores(match_report):
    """Normalize dimension_scores so frontend can read a stable {score, matched, missing} shape."""
    if not isinstance(match_report, dict):
        return match_report

    report = dict(match_report)
    raw = report.get("dimension_scores") or {}
    if not isinstance(raw, dict):
        raw = {}

    normalized = {}
    for key in ("skills", "experience", "education", "industry"):
        value = raw.get(key, 0)
        if isinstance(value, dict):
            item = dict(value)
            item["score"] = _score_value(item.get("score", 0))
        else:
            item = {"score": _score_value(value, 0)}
        item.setdefault("matched", [])
        item.setdefault("missing", [])
        normalized[key] = item

    report["dimension_scores"] = normalized
    return report


def _normalize_interview_questions(interview_questions):
    """Normalize old basic/tech/project/scenario output and new *_questions output."""
    if not isinstance(interview_questions, dict):
        return interview_questions

    data = dict(interview_questions)
    mapping = {
        "hr_questions": ("hr_questions", "basic"),
        "tech_questions": ("tech_questions", "tech"),
        "project_questions": ("project_questions", "project"),
        "scenario_questions": ("scenario_questions", "scenario"),
    }

    normalized = {}
    total = 0
    for target, sources in mapping.items():
        items = []
        for source in sources:
            source_items = data.get(source)
            if isinstance(source_items, list):
                items = source_items
                break
        normalized[target] = items
        total += len(items)

    for key, value in data.items():
        if key not in {"basic", "tech", "project", "scenario", *mapping.keys()}:
            normalized[key] = value

    normalized["total_questions"] = _score_value(data.get("total_questions", total), total)
    return normalized


def _load_task_outputs(db: Session, user_id: int, record_id: int):
    """Load orchestrated outputs attached to an analysis record."""
    task = (
        db.query(AgentTask)
        .filter(
            AgentTask.analysis_record_id == record_id,
            AgentTask.user_id == user_id,
        )
        .order_by(AgentTask.id.desc())
        .first()
    )
    if not task:
        return {}, {}, {}

    career_planning = {}
    rag_confidence = {}
    steps = (
        db.query(AgentStepLog).filter(AgentStepLog.task_id == task.id).order_by(AgentStepLog.step_index.desc()).all()
    )
    for step in steps:
        step_norm = normalize_step_name(step.step_name)
        parsed = _deep_parse_json(step.output_data)
        if step_norm == "knowledge_retrieval" and isinstance(parsed, dict) and parsed.get("rag_confidence"):
            rag_confidence = parsed["rag_confidence"]
        if step_norm == "career_planning":
            career_planning = parsed
            break
        # Fallback: some pipelines store career_planning nested in SummaryAgent output
        if isinstance(parsed, dict) and "career_planning" in parsed and parsed["career_planning"]:
            career_planning = parsed["career_planning"]
            break

    final_report = _deep_parse_json(task.final_report)
    return final_report, career_planning, rag_confidence


def _get_owned_resume(db: Session, user: User, resume_id: int | None) -> Resume | None:
    if not resume_id:
        return None
    return db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()


router = APIRouter()


@router.post("/full", summary="一键智能分析：统一编排 Agent 工作流")
async def full_smart_analysis(
    payload: FullAnalysisReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = (
        db.query(Resume)
        .filter(
            Resume.id == payload.resume_id,
            Resume.user_id == current_user.id,
            Resume.is_deleted == 0,
        )
        .first()
    )
    jd = get_accessible_job(db, payload.jd_id, current_user)
    if not resume or not jd:
        raise api_error(404, "简历或 JD 不存在，或无权限访问", ERR_PARAM)

    try:
        task_id = run_smart_analysis(
            resume_id=payload.resume_id,
            jd_id=payload.jd_id,
            user_id=current_user.id,
        )
        return ok(data={"task_id": task_id}, message="智能分析已启动")
    except Exception as exc:
        traceback.print_exc()
        raise api_error(500, f"启动分析失败: {exc}", ERR_COMMON) from exc


@router.post("/match", summary="一键分析：匹配度 + 优化 + 面试题")
async def full_match(
    payload: MatchReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = db.query(Resume).filter(Resume.id == payload.resume_id, Resume.user_id == current_user.id).first()
    jd = get_accessible_job(db, payload.jd_id, current_user)
    if not resume or not jd:
        raise api_error(404, "简历或 JD 不存在，或无权限访问", ERR_PARAM)

    try:
        record = match_service.run_full_analysis(
            db,
            payload.resume_id,
            payload.jd_id,
            remark=payload.remark if hasattr(payload, "remark") else "",
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise api_error(400, str(exc), ERR_PARAM) from exc
    except RuntimeError as exc:
        raise api_error(502, f"AI 服务出错: {exc}", ERR_AI) from exc
    except Exception as exc:
        traceback.print_exc()
        raise api_error(500, f"分析失败: {exc}", ERR_COMMON) from exc

    references = getattr(record, "_references", [])
    return ok(
        {
            "record_id": record.id,
            "match_score": record.match_score,
            "match_report": _normalize_dimension_scores(_deep_parse_json(record.match_report)),
            "optimize_suggestions": _deep_parse_json(record.optimize_suggestions),
            "interview_questions": _normalize_interview_questions(_deep_parse_json(record.interview_questions)),
            "references": references,
        },
        message="分析完成",
    )


@router.post("/{record_id}/optimize/regenerate", summary="重新生成简历优化建议")
async def regen_optimize(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rec = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.id == record_id, AnalysisRecord.user_id == current_user.id)
        .first()
    )
    if not rec:
        raise api_error(404, "记录不存在，或无权限访问", ERR_PARAM)

    try:
        record = optimize_service.regenerate_optimize(db, record_id, user_id=current_user.id)
    except ValueError as exc:
        raise api_error(400, str(exc), ERR_PARAM) from exc
    except Exception as exc:
        traceback.print_exc()
        raise api_error(502, f"重新生成失败: {exc}", ERR_AI) from exc

    return ok(
        {
            "record_id": record.id,
            "optimize_suggestions": _deep_parse_json(record.optimize_suggestions),
        },
        message="简历优化建议已重新生成",
    )


@router.post("/{record_id}/interview/regenerate", summary="重新生成面试题")
async def regen_interview(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rec = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.id == record_id, AnalysisRecord.user_id == current_user.id)
        .first()
    )
    if not rec:
        raise api_error(404, "记录不存在，或无权限访问", ERR_PARAM)

    try:
        record = interview_service.regenerate_interview(db, record_id, user_id=current_user.id)
    except ValueError as exc:
        raise api_error(400, str(exc), ERR_PARAM) from exc
    except Exception as exc:
        traceback.print_exc()
        raise api_error(502, f"重新生成失败: {exc}", ERR_AI) from exc

    return ok(
        {
            "record_id": record.id,
            "interview_questions": _normalize_interview_questions(_deep_parse_json(record.interview_questions)),
        },
        message="面试题已重新生成",
    )


@router.get("/{record_id}", summary="获取单条分析结果详情")
async def get_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        rec = (
            db.query(AnalysisRecord)
            .filter(AnalysisRecord.id == record_id, AnalysisRecord.user_id == current_user.id)
            .first()
        )
    except Exception as exc:
        raise api_error(500, f"查询失败: {exc}", ERR_DB) from exc

    if not rec:
        raise api_error(404, "记录不存在，或无权限访问", ERR_PARAM)

    resume = _get_owned_resume(db, current_user, rec.resume_id)
    jd = get_accessible_job(db, rec.jd_id, current_user) if rec.jd_id else None

    resume_parsed = resume.parsed_json or {} if resume else {}
    jd_parsed = jd.parsed_json or {} if jd else {}
    fallback_required = list(jd.skill_tags or []) if jd else []
    resume_skills = resume_skill_names(resume_parsed)
    jd_skills = jd_skill_union(jd_parsed, fallback_required)
    report_gap = build_skill_gap(
        resume_parsed,
        jd_parsed,
        jd_id=rec.jd_id,
        fallback_required=fallback_required,
    )
    matched = report_gap.matched_required + report_gap.matched_nice_to_have
    missing = report_gap.missing_required + report_gap.missing_nice_to_have

    parsed_match = _normalize_dimension_scores(_deep_parse_json(rec.match_report))
    parsed_interview = _normalize_interview_questions(_deep_parse_json(rec.interview_questions))
    final_report, career_planning, rag_confidence = _load_task_outputs(db, current_user.id, rec.id)

    return ok(
        {
            "id": rec.id,
            "record_id": rec.id,
            "resume_id": rec.resume_id,
            "jd_id": rec.jd_id,
            "match_score": rec.match_score,
            "match_report": parsed_match,
            "optimize_suggestions": _deep_parse_json(rec.optimize_suggestions),
            "interview_questions": parsed_interview,
            "remark": rec.remark,
            "resume_title": resume.file_name if resume else "",
            "jd_title": jd.title if jd else "",
            "resume_skills": resume_skills,
            "jd_skills": jd_skills,
            "matched_skills": matched,
            "missing_skills": missing,
            "final_report": final_report,
            "career_planning": career_planning,
            "rag_confidence": rag_confidence,
            "create_time": rec.create_time.isoformat() if rec.create_time else None,
        }
    )


@router.get("/{record_id}/references", summary="获取分析引用的知识库来源")
async def get_record_references(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rec = (
        db.query(AnalysisRecord)
        .filter(
            AnalysisRecord.id == record_id,
            AnalysisRecord.user_id == current_user.id,
        )
        .first()
    )
    if not rec:
        raise api_error(404, "记录不存在，或无权限访问", ERR_PARAM)

    resume = _get_owned_resume(db, current_user, rec.resume_id)
    jd = get_accessible_job(db, rec.jd_id, current_user) if rec.jd_id else None
    if not resume or not jd:
        return ok(data={"references": []})

    jd_data = jd.parsed_json or {}
    title = jd_data.get("title", "") or jd.title or ""
    skills = jd_data.get("required_skills", []) or []
    keywords = jd_data.get("keywords", []) or []
    query_parts = [title]
    if isinstance(skills, list):
        query_parts.extend(skills[:5])
    if isinstance(keywords, list):
        query_parts.extend(keywords[:5])
    query = " ".join(query_parts)

    references = get_knowledge_references(query, db, user_id=current_user.id)
    _, _, rag_confidence = _load_task_outputs(db, current_user.id, rec.id)
    return ok(data={"references": references, "query": query, "rag_confidence": rag_confidence})


@router.post("/explain-match", summary="匹配度解释器")
async def explain_match(
    payload: ExplainMatchReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """基于规则+LLM的匹配度深度解释

    流程:
      1. 规则引擎计算 6 维基础分
      2. 加权汇总
      3. LLM 生成自然语言解释
      4. 返回完整解释结果
    """
    resume = (
        db.query(Resume)
        .filter(
            Resume.id == payload.resume_id,
            Resume.user_id == current_user.id,
            Resume.is_deleted == 0,
        )
        .first()
    )
    jd = get_accessible_job(db, payload.jd_id, current_user)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)
    if not jd:
        return fail(message="JD不存在或无权限", code=ERR_PARAM)
    if not resume.parsed_json:
        return fail(message="简历尚未解析", code=ERR_PARAM)

    try:
        explainer = MatchExplainer()
        result = explainer.explain(resume, jd)
        return ok(data=result.to_dict(), message="匹配度解释完成")
    except Exception as e:
        traceback.print_exc()
        return fail(message=f"匹配度解释失败: {str(e)[:80]}", code=ERR_COMMON)
