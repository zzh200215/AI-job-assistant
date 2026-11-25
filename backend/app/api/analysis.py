"""Analysis APIs for smart matching, optimization, and references."""

import json
import traceback

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.agent import AgentStepLog, AgentTask, RetrievalLog
from app.models.history import AnalysisRecord, Resume
from app.models.prompt_trace import PromptTrace
from app.models.user import User
from app.orchestration.protocol import normalize_step_name
from app.schemas.analysis import ExplainMatchReq, FullAnalysisReq
from app.services import interview_service, optimize_service
from app.services.analysis_service import run_smart_analysis
from app.services.match_explainer_service import MatchExplainer
from app.services.orchestration_backend import OrchestrationUnavailable
from app.services.rag_confidence_service import confidence_from_flat_results
from app.services.rag_service import get_knowledge_references
from app.services.skill_gap import build_skill_gap, canonicalize_skill_rows, jd_skill_union, resume_skill_names
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


def _complete_match_report(match_report, score, matched, missing):
    """展示层兜底：模型没给摘要/证据时，用权威分与技能覆盖把话说完整。"""
    if not isinstance(match_report, dict):
        return match_report
    report = dict(match_report)
    summary = report.get("summary")
    if not summary or "没有匹配摘要" in str(summary):
        covered = f"已覆盖 {len(matched)} 项岗位技能" if matched else "暂无已覆盖的岗位技能"
        missing_text = f"缺少 {', '.join(missing[:4])}" if missing else "没有明显技能缺口"
        report["summary"] = f"按六维规则当前匹配度 {score}；{covered}，{missing_text}。"
    if not report.get("strengths") and matched:
        report["strengths"] = [f"已覆盖岗位技能：{', '.join(matched[:5])}"]
    if not report.get("gaps") and missing:
        report["gaps"] = [f"缺少岗位技能：{', '.join(missing[:5])}"]
    if not report.get("risk_points") and missing:
        report["risk_points"] = ["关键技能缺口可能影响简历初筛。"]
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
    steps = (
        db.query(AgentStepLog).filter(AgentStepLog.task_id == task.id).order_by(AgentStepLog.step_index.desc()).all()
    )
    for step in steps:
        step_norm = normalize_step_name(step.step_name)
        parsed = _deep_parse_json(step.output_data)
        if step_norm == "career_planning":
            career_planning = parsed
            break
        # Fallback: some pipelines store career_planning nested in SummaryAgent output
        if isinstance(parsed, dict) and "career_planning" in parsed and parsed["career_planning"]:
            career_planning = parsed["career_planning"]
            break

    rag_confidence = _rag_confidence_from_retrievals(db, task.id)
    final_report = _deep_parse_json(task.final_report)
    # 历史记录落库时还没有 canonical（D281 之前）；读出来补上，前端才能按同一把尺
    # 把面试证据贴到别名缺口上。只改这份响应对象，库里的 json 不动。
    if isinstance(career_planning, dict):
        canonicalize_skill_rows(career_planning.get("skill_gaps"))
    return final_report, career_planning, rag_confidence


def _rag_confidence_from_retrievals(db: Session, task_id: int) -> dict:
    """从 `retrieval_log` 反推这次分析的知识取证置信度。

    这里原先读的是 `knowledge_retrieval` 步骤日志——只有 `step_by_step` 那条已删除
    的流水线会写它，所以主线任务上这个字段永远是空的。现在改为按真实发生过的检索
    计算，并且复用同一个实现（`confidence_from_flat_results`），不另造一套口径；
    没有任何检索记录时返回空字典——那是"没查过"，不是"查了没信心"。
    """
    rows = db.query(RetrievalLog).filter(RetrievalLog.task_id == task_id).order_by(RetrievalLog.id).all()
    if not rows:
        return {}

    hits: list[dict] = []
    for row in rows:
        for item in row.results or []:
            hits.append({**item, "doc_type": item.get("doc_type") or row.doc_type_filter or "general"})

    representative_query = next((r.query_text for r in rows if r.query_text), "")
    return confidence_from_flat_results(representative_query, hits)


def _get_owned_resume(db: Session, user: User, resume_id: int | None) -> Resume | None:
    if not resume_id:
        return None
    return db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == user.id).first()


router = APIRouter()


@router.post("/full", summary="一键智能分析：统一编排 Agent 工作流")
def full_smart_analysis(
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
    except OrchestrationUnavailable as exc:
        # 503 而不是 500：这不是"分析失败"，是**现在没人能跑**——换个时间/起一个 worker 就好。
        # 也刻意不回 task_id：发一个没人会跑的任务号，前端就只能一直转圈。
        raise api_error(503, str(exc), ERR_AI) from exc
    except Exception as exc:
        traceback.print_exc()
        # 这句会**原样上屏**（`request.js` 把 `message` 当 toast）：异常原文里常带着 provider 的
        # "HTTP 429 / fallback 链路均未成功"。证据留在上面那次 traceback，屏幕只说下一步。
        raise api_error(500, "启动分析失败，请稍后重试", ERR_COMMON) from exc


@router.post("/{record_id}/optimize/regenerate", summary="重新生成简历优化建议")
def regen_optimize(
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
        # 不带 `str(exc)`：这一支几乎到不了（上面已经查过一次 404），但 message 会原样上屏，
        # 而且 `ValueError` 不是我们自己的异常类型——文案固定成一句更稳。
        raise api_error(400, "找不到这条分析记录，或你没有访问权限", ERR_PARAM) from exc
    except Exception as exc:
        traceback.print_exc()
        raise api_error(502, "重新生成失败，请稍后重试", ERR_AI) from exc

    return ok(
        {
            "record_id": record.id,
            "optimize_suggestions": _deep_parse_json(record.optimize_suggestions),
        },
        message="简历优化建议已重新生成",
    )


@router.post("/{record_id}/interview/regenerate", summary="重新生成面试题")
def regen_interview(
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
        # 不带 `str(exc)`：这一支几乎到不了（上面已经查过一次 404），但 message 会原样上屏，
        # 而且 `ValueError` 不是我们自己的异常类型——文案固定成一句更稳。
        raise api_error(400, "找不到这条分析记录，或你没有访问权限", ERR_PARAM) from exc
    except Exception as exc:
        traceback.print_exc()
        raise api_error(502, "重新生成失败，请稍后重试", ERR_AI) from exc

    return ok(
        {
            "record_id": record.id,
            "interview_questions": _normalize_interview_questions(_deep_parse_json(record.interview_questions)),
        },
        message="面试题已重新生成",
    )


def _load_provenance(db, record_id: int, user_id: int) -> dict | None:
    """这条结果的"底账"：几发模型调用、谁答的、几发没成功。

    数据本来就在库里——`AgentTask.analysis_record_id` 指回记录、`PromptTrace.task_id` 指回任务——
    只是没人把它们接起来。于是 2026-11-14 那次 7 发调用里 4 发 429、分数只来自规则臂，
    而结果页上只写着"分析完成，匹配度 57"。这一屏从此自己会说这件事。

    没有任务（老记录、或非编排路径写进来的记录）就返回 None：**不造一个全零的底账**，
    那会让"查不到"和"跑了但全失败"长得一样。
    """
    task = (
        db.query(AgentTask)
        .filter(AgentTask.analysis_record_id == record_id, AgentTask.user_id == user_id)
        .order_by(AgentTask.id.desc())
        .first()
    )
    if not task:
        return None

    rows = (
        db.query(PromptTrace.response_source, PromptTrace.status, PromptTrace.degraded)
        .filter(PromptTrace.task_id == task.id)
        .all()
    )
    if not rows:
        return None

    by_source: dict[str, int] = {}
    for source, _status, _degraded in rows:
        key = source or "unknown"
        by_source[key] = by_source.get(key, 0) + 1

    return {
        "task_id": task.id,
        "task_status": task.status,
        "calls": len(rows),
        "by_source": by_source,
        "failed": sum(1 for _s, status, _d in rows if status != "success"),
        "degraded": sum(1 for _s, _st, flagged in rows if flagged),
    }


@router.get("/{record_id}", summary="获取单条分析结果详情")
def get_record(
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
        raise api_error(500, "查询失败，请稍后重试", ERR_DB) from exc

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

    parsed_match = _complete_match_report(
        _normalize_dimension_scores(_deep_parse_json(rec.match_report)),
        rec.match_score,
        matched,
        missing,
    )
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
            # 这份结果是"谁答的"：几发调用、几发失败、几发降级。没有就是 None（老记录）。
            "provenance": _load_provenance(db, rec.id, current_user.id),
            "create_time": rec.create_time.isoformat() if rec.create_time else None,
        }
    )


@router.get("/{record_id}/references", summary="获取分析引用的知识库来源")
def get_record_references(
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
def explain_match(
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
