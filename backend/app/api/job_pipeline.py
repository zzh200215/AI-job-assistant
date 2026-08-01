"""投递流程 API — 看板视图、阶段流转、面试日程、Offer 管理"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.tenant_context import stamp_tenant, tenant_filter
from app.models.history import Resume, ResumeVersion
from app.models.job_pipeline import (
    ACTIVE_STAGES,
    PIPELINE_STAGES,
    TERMINAL_STAGES,
    VALID_TRANSITIONS,
    JobApplicationPipeline,
)
from app.models.user import User
from app.schemas.job_pipeline import (
    PipelineCreateReq,
    PipelineUpdateReq,
    StageTransitionReq,
)
from app.utils.job_access import get_accessible_job
from app.utils.response import ERR_PARAM, fail, ok
from app.utils.time_helper import utc_now, utc_now_iso

router = APIRouter()


def _get_owned_resume_version(
    db: Session, user_id: int, resume_id: int | None, version_id: int
) -> ResumeVersion | None:
    query = (
        db.query(ResumeVersion)
        .join(Resume, ResumeVersion.resume_id == Resume.id)
        .filter(
            ResumeVersion.id == version_id,
            ResumeVersion.format == "md",
            Resume.user_id == user_id,
            Resume.is_deleted == 0,
        )
    )
    if resume_id is not None:
        query = query.filter(ResumeVersion.resume_id == resume_id)
    return query.first()


# ============================================================
# 看板视图
# ============================================================


@router.get("/pipeline/kanban", summary="看板视图（按阶段分组）")
async def kanban_view(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = db.query(JobApplicationPipeline).filter(tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id).all()

    stages: dict[str, list[dict]] = {s: [] for s in ACTIVE_STAGES}
    stages.update({s: [] for s in TERMINAL_STAGES})
    stage_counts: dict[str, int] = dict.fromkeys(PIPELINE_STAGES, 0)

    for item in items:
        d = item.to_dict()
        stage = item.stage
        if stage not in stages:
            stages[stage] = []
        stages[stage].append(d)
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    # 活跃阶段按 follow_up_at / update_time 排序
    for stage_key in stages:
        stages[stage_key].sort(
            key=lambda x: (
                x.get("follow_up_at") or "9999",
                x.get("update_time") or "",
            )
        )

    return ok(
        {
            "stages": stages,
            "stage_counts": stage_counts,
            "active_stages": ACTIVE_STAGES,
            "terminal_stages": TERMINAL_STAGES,
        }
    )


# ============================================================
# 面试日程
# ============================================================


@router.get("/pipeline/interviews", summary="获取即将面试列表")
async def upcoming_interviews(
    days: int = Query(7, ge=1, le=30, description="查询未来 N 天内的面试"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = utc_now()
    entries = (
        db.query(JobApplicationPipeline)
        .filter(
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.stage == "interview",
            JobApplicationPipeline.interview_at.isnot(None),
        )
        .order_by(JobApplicationPipeline.interview_at)
        .all()
    )

    from datetime import timedelta

    cutoff = now + timedelta(days=days)
    result = []
    for e in entries:
        if e.interview_at and e.interview_at <= cutoff:
            result.append(e.to_dict())

    return ok({"total": len(result), "items": result})


# ============================================================
# Offer 对比
# ============================================================


@router.get("/pipeline/offers", summary="获取所有 Offer 列表（用于对比）")
async def list_offers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entries = (
        db.query(JobApplicationPipeline)
        .filter(
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.stage.in_(["offer", "accepted"]),
        )
        .order_by(JobApplicationPipeline.update_time.desc())
        .all()
    )
    return ok(
        {
            "total": len(entries),
            "items": [e.to_dict() for e in entries],
        }
    )


# ============================================================
# 投递记录 CRUD
# ============================================================


@router.get("/pipeline/list", summary="获取投递流程列表")
async def list_pipeline_entries(
    stage: str = Query("", description="流程阶段过滤"),
    keyword: str = Query("", description="岗位/公司/备注关键词"),
    resume_id: int | None = Query(None, description="简历 ID 过滤"),
    is_active: bool | None = Query(None, description="是否活跃阶段"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if stage and stage not in PIPELINE_STAGES:
        return fail(message=f"非法的流程阶段，可选值: {', '.join(sorted(PIPELINE_STAGES))}", code=ERR_PARAM)

    q = db.query(JobApplicationPipeline).filter(tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id)
    if stage:
        q = q.filter(JobApplicationPipeline.stage == stage)
    if resume_id is not None:
        q = q.filter(JobApplicationPipeline.resume_id == resume_id)
    if is_active is True:
        q = q.filter(JobApplicationPipeline.stage.in_(ACTIVE_STAGES))
    elif is_active is False:
        q = q.filter(JobApplicationPipeline.stage.in_(TERMINAL_STAGES))

    items = q.all()
    keyword = keyword.strip().lower()
    if keyword:
        items = [
            item
            for item in items
            if keyword
            in " ".join(
                [
                    item.title or "",
                    item.company or "",
                    item.location or "",
                    item.note or "",
                    item.next_action or "",
                    item.resume_name or "",
                ]
            ).lower()
        ]

    items.sort(key=_sort_key)
    return ok(
        {
            "total": len(items),
            "items": [item.to_dict() for item in items],
        }
    )


@router.get("/pipeline/resume-versions", summary="获取可用于投递追踪的简历版本")
async def list_pipeline_resume_versions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    versions = (
        db.query(ResumeVersion, Resume)
        .join(Resume, ResumeVersion.resume_id == Resume.id)
        .filter(
            Resume.user_id == current_user.id,
            Resume.is_deleted == 0,
            ResumeVersion.format == "md",
        )
        .order_by(ResumeVersion.created_at.desc())
        .all()
    )
    return ok(
        {
            "items": [
                {
                    "id": version.id,
                    "resume_id": version.resume_id,
                    "label": version.label or f"{version.version_type} 版本",
                    "version_type": version.version_type,
                    "target_jd_id": version.target_jd_id,
                    "resume_name": resume.file_name or resume.name or "简历",
                    "created_at": version.created_at.isoformat() if version.created_at else None,
                }
                for version, resume in versions
            ]
        }
    )


@router.get("/pipeline/resume-version-stats", summary="简历版本投递效果汇总")
async def pipeline_resume_version_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entries = (
        db.query(JobApplicationPipeline)
        .filter(
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.resume_version_id.isnot(None),
        )
        .all()
    )
    grouped: dict[int, dict] = {}
    for entry in entries:
        version_id = entry.resume_version_id
        row = grouped.setdefault(
            version_id,
            {
                "resume_version_id": version_id,
                "label": entry.resume_version_label or f"版本 #{version_id}",
                "total": 0,
                "submitted": 0,
                "interviews": 0,
                "offers": 0,
                "accepted": 0,
                "rejected": 0,
                "latest_activity": None,
            },
        )
        row["total"] += 1
        if entry.stage != "todo":
            row["submitted"] += 1
        if entry.stage in {"interview", "offer", "accepted"}:
            row["interviews"] += 1
        if entry.stage in {"offer", "accepted"}:
            row["offers"] += 1
        if entry.stage == "accepted":
            row["accepted"] += 1
        if entry.stage == "rejected":
            row["rejected"] += 1
        timestamp = entry.update_time.isoformat() if entry.update_time else None
        if timestamp and (not row["latest_activity"] or timestamp > row["latest_activity"]):
            row["latest_activity"] = timestamp

    items = []
    for row in grouped.values():
        submitted = row["submitted"]
        row["interview_rate"] = round(row["interviews"] / submitted * 100, 1) if submitted else 0
        row["offer_rate"] = round(row["offers"] / submitted * 100, 1) if submitted else 0
        items.append(row)
    items.sort(key=lambda item: (item["interviews"], item["submitted"], item["latest_activity"] or ""), reverse=True)
    return ok({"total_versions": len(items), "items": items})


@router.get("/pipeline/recommend-resume-version", summary="为目标岗位推荐简历版本")
async def recommend_pipeline_resume_version(
    jd_id: int = Query(..., description="目标岗位 ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jd = get_accessible_job(db, jd_id, current_user)
    if not jd:
        return fail(message="岗位不存在或无权限", code=ERR_PARAM)
    keywords = list((jd.parsed_json or {}).get("required_skills", []) or [])
    keywords = list(dict.fromkeys(str(item).strip() for item in keywords if str(item).strip()))[:20]
    versions = (
        db.query(ResumeVersion)
        .join(Resume, ResumeVersion.resume_id == Resume.id)
        .filter(Resume.user_id == current_user.id, Resume.is_deleted == 0, ResumeVersion.format == "md")
        .all()
    )
    entries = db.query(JobApplicationPipeline).filter(tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id).all()
    items = []
    for version in versions:
        matched = [keyword for keyword in keywords if keyword.lower() in (version.content or "").lower()]
        coverage = len(matched) / len(keywords) if keywords else 0
        samples = [entry for entry in entries if entry.resume_version_id == version.id and entry.stage != "todo"]
        interviews = sum(entry.stage in {"interview", "offer", "accepted"} for entry in samples)
        interview_rate = interviews / len(samples) if samples else 0
        items.append(
            {
                "resume_version_id": version.id,
                "resume_id": version.resume_id,
                "label": version.label or f"{version.version_type} 版本",
                "score": round(coverage * 70 + interview_rate * 30),
                "matched_keywords": matched,
                "keyword_coverage": round(coverage * 100),
                "sample_size": len(samples),
                "historical_interview_rate": round(interview_rate * 100, 1),
            }
        )
    items.sort(key=lambda item: (item["score"], item["sample_size"]), reverse=True)
    return ok({"jd_id": jd.id, "items": items[:5], "recommended": items[0] if items else None})


@router.post("/pipeline", summary="创建投递流程记录")
async def create_pipeline_entry(
    payload: PipelineCreateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = None
    jd = None

    if payload.resume_id is not None:
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

    resume_version = None
    if payload.resume_version_id is not None:
        resume_version = _get_owned_resume_version(db, current_user.id, payload.resume_id, payload.resume_version_id)
        if not resume_version:
            return fail(message="简历版本不存在、与简历不匹配或无权限", code=ERR_PARAM)
        if resume is None:
            resume = db.get(Resume, resume_version.resume_id)

    if payload.jd_id is not None:
        jd = get_accessible_job(db, payload.jd_id, current_user)
        if not jd:
            return fail(message="岗位不存在或无权限", code=ERR_PARAM)

    duplicate = None
    if payload.jd_id is not None:
        duplicate = (
            db.query(JobApplicationPipeline)
            .filter(
                tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
                JobApplicationPipeline.jd_id == payload.jd_id,
                JobApplicationPipeline.resume_id == payload.resume_id,
                JobApplicationPipeline.resume_version_id == payload.resume_version_id,
            )
            .first()
        )
    elif payload.source_url and payload.title:
        duplicate = (
            db.query(JobApplicationPipeline)
            .filter(
                tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
                JobApplicationPipeline.source_url == payload.source_url,
                JobApplicationPipeline.title == payload.title,
                JobApplicationPipeline.company == payload.company,
            )
            .first()
        )

    if duplicate:
        return ok(duplicate.to_dict(), message="该岗位已在投递流程中")

    try:
        follow_up_at = _parse_datetime(payload.follow_up_at)
        interview_at = _parse_datetime(payload.interview_at)
        offer_deadline = _parse_datetime(payload.offer_deadline)
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)

    history = [item.model_dump() for item in payload.stage_history]
    if not history:
        history = [{"stage": payload.stage, "at": utc_now_iso()}]

    entry = stamp_tenant(
        JobApplicationPipeline(
        user_id=current_user.id,
        resume_id=resume.id if resume else payload.resume_id,
        resume_version_id=resume_version.id if resume_version else None,
        resume_version_label=(resume_version.label or resume_version.version_type) if resume_version else "",
        feedback_type=payload.feedback_type,
        feedback_score=payload.feedback_score,
        feedback_tags=_unique_skill_tags(payload.feedback_tags),
        feedback_note=payload.feedback_note,
        feedback_at=utc_now() if payload.feedback_type or payload.feedback_note else None,
        jd_id=jd.id if jd else payload.jd_id,
        title=payload.title or (jd.title if jd else ""),
        company=payload.company or (jd.company if jd else ""),
        location=payload.location or (jd.location if jd else ""),
        salary_range=payload.salary_range or (jd.salary_range if jd else ""),
        source=payload.source or (jd.source if jd else "manual"),
        source_url=payload.source_url or (jd.external_url if jd else ""),
        summary=payload.summary,
        raw_text=payload.raw_text or (jd.raw_text if jd else ""),
        experience_requirement=payload.experience_requirement or (jd.experience_requirement if jd else ""),
        education_requirement=payload.education_requirement or (jd.education_requirement if jd else ""),
        industry=payload.industry or (jd.industry if jd else ""),
        skill_tags=_unique_skill_tags(payload.skill_tags or (jd.skill_tags if jd else [])),
        priority_score=payload.priority_score,
        priority_label=payload.priority_label,
        stage=payload.stage,
        note=payload.note,
        next_action=payload.next_action,
        follow_up_at=follow_up_at,
        resume_name=payload.resume_name or (resume.file_name if resume else ""),
        stage_history=history,
        interview_at=interview_at,
        interview_type=payload.interview_type,
        interview_round=payload.interview_round,
        interview_location=payload.interview_location,
        interview_contact=payload.interview_contact,
        offer_salary=payload.offer_salary,
        offer_details=payload.offer_details,
        offer_deadline=offer_deadline,
        )
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return ok(entry.to_dict(), message="已加入投递流程")


# ============================================================
# 阶段流转（专用接口，校验合法流转）
# ============================================================


@router.post("/pipeline/{entry_id}/transition", summary="阶段流转")
async def transition_stage(
    entry_id: int,
    payload: StageTransitionReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.id == entry_id,
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
        )
        .first()
    )
    if not entry:
        return fail(message="投递记录不存在或无权限", code=ERR_PARAM)

    current_stage = entry.stage
    target_stage = payload.target_stage

    if current_stage == target_stage:
        return fail(message="目标阶段与当前阶段相同", code=ERR_PARAM)

    allowed = VALID_TRANSITIONS.get(current_stage, set())
    if target_stage not in allowed:
        return fail(
            message=f"不允许从 '{current_stage}' 流转到 '{target_stage}'，允许的目标: {', '.join(sorted(allowed)) or '无（终态）'}",
            code=ERR_PARAM,
        )

    # 更新阶段和历史
    history = entry.stage_history or []
    history.append(
        {
            "stage": target_stage,
            "at": utc_now_iso(),
            "note": payload.note,
            "from_stage": current_stage,
        }
    )
    entry.stage = target_stage
    entry.stage_history = history

    # 面试阶段携带面试信息
    if target_stage == "interview":
        if payload.interview_at:
            try:
                entry.interview_at = _parse_datetime(payload.interview_at)
            except ValueError as exc:
                return fail(message=str(exc), code=ERR_PARAM)
        if payload.interview_type is not None:
            entry.interview_type = payload.interview_type
        if payload.interview_round is not None:
            entry.interview_round = payload.interview_round
        if payload.interview_location is not None:
            entry.interview_location = payload.interview_location
        if payload.interview_contact is not None:
            entry.interview_contact = payload.interview_contact

    # Offer 阶段携带 Offer 信息
    if target_stage == "offer":
        if payload.offer_salary is not None:
            entry.offer_salary = payload.offer_salary
        if payload.offer_details is not None:
            entry.offer_details = payload.offer_details
        if payload.offer_deadline:
            try:
                entry.offer_deadline = _parse_datetime(payload.offer_deadline)
            except ValueError as exc:
                return fail(message=str(exc), code=ERR_PARAM)

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return ok(entry.to_dict(), message=f"已从 '{current_stage}' 流转到 '{target_stage}'")


@router.put("/pipeline/{entry_id}", summary="更新投递流程记录")
async def update_pipeline_entry(
    entry_id: int,
    payload: PipelineUpdateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.id == entry_id,
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
        )
        .first()
    )
    if not entry:
        return fail(message="投递记录不存在或无权限", code=ERR_PARAM)

    data = payload.model_dump(exclude_unset=True)

    if "resume_id" in data and data["resume_id"] is not None:
        resume = (
            db.query(Resume)
            .filter(
                Resume.id == data["resume_id"],
                Resume.user_id == current_user.id,
                Resume.is_deleted == 0,
            )
            .first()
        )
        if not resume:
            return fail(message="简历不存在或无权限", code=ERR_PARAM)
        entry.resume_id = resume.id
        if "resume_name" not in data:
            entry.resume_name = resume.file_name or resume.name or ""

    if "resume_version_id" in data:
        version_id = data["resume_version_id"]
        if version_id is None:
            entry.resume_version_id = None
            entry.resume_version_label = ""
        else:
            bound_resume_id = data.get("resume_id", entry.resume_id)
            version = _get_owned_resume_version(db, current_user.id, bound_resume_id, version_id)
            if not version:
                return fail(message="简历版本不存在、与简历不匹配或无权限", code=ERR_PARAM)
            entry.resume_id = version.resume_id
            entry.resume_version_id = version.id
            entry.resume_version_label = version.label or version.version_type

    if "jd_id" in data and data["jd_id"] is not None:
        jd = get_accessible_job(db, data["jd_id"], current_user)
        if not jd:
            return fail(message="岗位不存在或无权限", code=ERR_PARAM)
        entry.jd_id = jd.id

    # 通用字段
    _simple_fields = (
        "title",
        "company",
        "location",
        "salary_range",
        "source",
        "source_url",
        "summary",
        "raw_text",
        "experience_requirement",
        "education_requirement",
        "industry",
        "priority_score",
        "priority_label",
        "stage",
        "note",
        "next_action",
        "resume_name",
        "interview_type",
        "interview_round",
        "interview_location",
        "interview_contact",
            "offer_salary",
            "feedback_type",
            "feedback_score",
            "feedback_note",
    )
    for field in _simple_fields:
        if field in data:
            setattr(entry, field, data[field])

    # 需要特殊处理的字段
    if "skill_tags" in data and data["skill_tags"] is not None:
        entry.skill_tags = _unique_skill_tags(data["skill_tags"])
    if "feedback_tags" in data and data["feedback_tags"] is not None:
        entry.feedback_tags = _unique_skill_tags(data["feedback_tags"])
    if any(field in data for field in ("feedback_type", "feedback_score", "feedback_tags", "feedback_note")):
        entry.feedback_at = utc_now()

    for dt_field in ("follow_up_at", "interview_at", "offer_deadline"):
        if dt_field in data:
            try:
                setattr(entry, dt_field, _parse_datetime(data[dt_field]))
            except ValueError as exc:
                return fail(message=str(exc), code=ERR_PARAM)

    if "stage_history" in data and data["stage_history"] is not None:
        entry.stage_history = [
            item.model_dump() if hasattr(item, "model_dump") else item for item in data["stage_history"]
        ]

    if "offer_details" in data and data["offer_details"] is not None:
        entry.offer_details = data["offer_details"]

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return ok(entry.to_dict(), message="投递记录已更新")


@router.delete("/pipeline/terminal", summary="清理所有终态记录（rejected/withdrawn）")
async def clear_terminal_pipeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = (
        db.query(JobApplicationPipeline)
        .filter(
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.stage.in_(TERMINAL_STAGES),
        )
        .all()
    )
    count = len(items)
    for item in items:
        db.delete(item)
    db.commit()
    return ok({"deleted": count}, message=f"已清理 {count} 条终态记录")


@router.delete("/pipeline/{entry_id}", summary="删除投递流程记录")
async def delete_pipeline_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = (
        db.query(JobApplicationPipeline)
        .filter(
            JobApplicationPipeline.id == entry_id,
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
        )
        .first()
    )
    if not entry:
        return fail(message="投递记录不存在或无权限", code=ERR_PARAM)

    db.delete(entry)
    db.commit()
    return ok(message="投递记录已删除")


# ============================================================
# 投递统计摘要
# ============================================================


@router.get("/pipeline/stats", summary="投递数据统计")
async def pipeline_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(
            JobApplicationPipeline.stage,
            func.count(JobApplicationPipeline.id),
        )
        .filter(tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id)
        .group_by(JobApplicationPipeline.stage)
        .all()
    )
    stage_counts = dict(rows)

    # 本周新增投递数
    from datetime import timedelta

    week_ago = utc_now() - timedelta(days=7)
    weekly_new = (
        db.query(func.count(JobApplicationPipeline.id))
        .filter(
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.create_time >= week_ago,
        )
        .scalar()
    )

    # 即将面试数
    upcoming_interviews_count = (
        db.query(func.count(JobApplicationPipeline.id))
        .filter(
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.stage == "interview",
            JobApplicationPipeline.interview_at.isnot(None),
            JobApplicationPipeline.interview_at >= utc_now(),
        )
        .scalar()
    )

    # 待回复 Offer
    pending_offers = (
        db.query(func.count(JobApplicationPipeline.id))
        .filter(
            tenant_filter(JobApplicationPipeline), JobApplicationPipeline.user_id == current_user.id,
            JobApplicationPipeline.stage == "offer",
        )
        .scalar()
    )

    total = sum(stage_counts.values())
    active_count = sum(stage_counts.get(s, 0) for s in ACTIVE_STAGES)

    return ok(
        {
            "total": total,
            "active": active_count,
            "stage_counts": stage_counts,
            "weekly_new": weekly_new,
            "upcoming_interviews": upcoming_interviews_count,
            "pending_offers": pending_offers,
            "conversion_rate": round(active_count / total, 2) if total > 0 else 0,
        }
    )


# ============================================================
# 工具函数
# ============================================================


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(normalized, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("时间格式非法，请使用 ISO 格式或 YYYY-MM-DD") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _sort_key(item: JobApplicationPipeline):
    follow_up = item.follow_up_at or datetime.max
    updated = item.update_time or datetime.min
    return (follow_up, -updated.timestamp())


def _unique_skill_tags(items):
    return list(dict.fromkeys([str(item).strip() for item in (items or []) if str(item).strip()]))
