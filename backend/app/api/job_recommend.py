"""Job recommendation APIs."""

import csv
import io
import json
import traceback
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.tenant_context import current_tenant_id, stamp_tenant, tenant_filter
from app.models.history import JobDescription, Resume
from app.models.job_recommend import JobBookmark, JobRecommendationFeedback
from app.models.user import User
from app.services.job_recommend_engine import JobRecommendationEngine, load_suppressed_reasons
from app.services.recommendation_tuning import (
    build_feedback_tuning_recommendation,
    get_recommendation_tuning_config,
    reset_recommendation_tuning_config,
    save_recommendation_tuning_config,
)
from app.utils.response import ERR_COMMON, ERR_PARAM, fail, ok

router = APIRouter()


def _is_admin(user: User) -> bool:
    return user.username in settings.admin_usernames_list


def _job_visibility_filter(user_id: int):
    return and_(
        or_(JobDescription.user_id == user_id, JobDescription.user_id.is_(None)),
        or_(JobDescription.tenant_id == current_tenant_id(), JobDescription.tenant_id.is_(None)),
    )


def _can_access_job(jd: JobDescription, user: User) -> bool:
    if _is_admin(user):
        return True
    owner_ok = jd.user_id in (None, user.id)
    tenant_ok = jd.tenant_id in (None, current_tenant_id())
    return owner_ok and tenant_ok


def _get_owned_resume(db: Session, resume_id: int, user_id: int) -> Resume | None:
    return (
        db.query(Resume)
        .filter(
            Resume.id == resume_id,
            Resume.user_id == user_id,
            Resume.is_deleted == 0,
        )
        .first()
    )


def _safe_resume_label(resume: Resume | None) -> str:
    if not resume:
        return ""
    if isinstance(resume, dict):
        return resume.get("name") or resume.get("file_name") or f"Resume {resume.get('id')}"
    return resume.name or resume.file_name or f"Resume {resume.id}"


def _mean_or_none(values: list[float | int | None], digits: int = 2) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return round(sum(filtered) / len(filtered), digits)


def _score_bucket_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score < 60:
        return "0-59"
    if score < 80:
        return "60-79"
    return "80-100"


def _build_feedback_action_items(
    *,
    total: int,
    like_count: int,
    dislike_count: int,
    high_score_dislikes: list[dict],
    low_score_likes: list[dict],
    weak_industries: list[dict],
) -> list[dict]:
    items: list[dict] = []
    if total == 0:
        return items

    dislike_rate = round(dislike_count / total, 2) if total else 0
    if dislike_rate >= 0.45:
        items.append(
            {
                "type": "ranking_quality",
                "severity": "high",
                "title": "整体点踩偏高，建议回看推荐排序权重",
                "detail": f"当前点踩占比 {dislike_rate:.0%}，需要优先检查技能匹配、地点和薪资权重。",
            }
        )

    if high_score_dislikes:
        items.append(
            {
                "type": "score_calibration",
                "severity": "high",
                "title": "存在高分点踩，建议校准匹配分阈值",
                "detail": f"发现 {len(high_score_dislikes)} 条 80 分及以上仍被点踩的反馈，说明评分与用户偏好存在偏差。",
            }
        )

    if low_score_likes:
        items.append(
            {
                "type": "recall_gap",
                "severity": "medium",
                "title": "存在低分点赞，建议补充召回特征",
                "detail": f"发现 {len(low_score_likes)} 条 60 分以下仍被点赞的反馈，说明部分岗位被低估。",
            }
        )

    if weak_industries:
        worst = weak_industries[0]
        items.append(
            {
                "type": "industry_bias",
                "severity": "medium",
                "title": "行业偏好出现明显分化",
                "detail": f"{worst['industry']} 的点踩率较高，可检查行业词权重、工作年限和岗位标签映射。",
            }
        )

    if not items and like_count:
        items.append(
            {
                "type": "stable",
                "severity": "low",
                "title": "当前反馈较稳定",
                "detail": "暂无明显异常，可继续积累反馈样本后再调整推荐规则。",
            }
        )

    return items[:4]


def _build_feedback_analysis(db: Session, *, user_id: int) -> dict:
    rows = (
        db.query(JobRecommendationFeedback)
        .filter(tenant_filter(JobRecommendationFeedback), JobRecommendationFeedback.user_id == user_id)
        .order_by(JobRecommendationFeedback.created_at.desc())
        .all()
    )

    total = len(rows)
    like_count = sum(1 for row in rows if row.feedback_type == "like")
    dislike_count = sum(1 for row in rows if row.feedback_type == "dislike")
    like_rate = round(like_count / total, 4) if total else 0
    dislike_rate = round(dislike_count / total, 4) if total else 0
    avg_match_score = _mean_or_none([row.match_score for row in rows if row.match_score is not None], digits=2)

    resume_ids = sorted({row.resume_id for row in rows})
    jd_ids = sorted({row.jd_id for row in rows})
    resume_map = (
        {
            item.id: {
                "id": item.id,
                "name": item.name,
                "file_name": item.file_name,
                "parsed_json": item.parsed_json or {},
            }
            for item in db.query(Resume).filter(Resume.id.in_(resume_ids)).all()
        }
        if resume_ids
        else {}
    )
    jd_map = (
        {
            item.id: {
                "id": item.id,
                "title": item.title,
                "company": item.company,
                "location": item.location,
                "salary_range": item.salary_range,
                "industry": item.industry,
                "raw_text": item.raw_text,
                "parsed_json": item.parsed_json or {},
                "source": item.source,
                "experience_requirement": item.experience_requirement,
            }
            for item in db.query(JobDescription).filter(JobDescription.id.in_(jd_ids)).all()
        }
        if jd_ids
        else {}
    )

    recent = []
    for row in rows[:12]:
        resume = resume_map.get(row.resume_id)
        jd = jd_map.get(row.jd_id)
        recent.append(
            {
                **row.to_dict(),
                "resume_title": _safe_resume_label(resume),
                "jd_title": jd["title"] if jd else "",
                "jd_company": jd["company"] if jd else "",
                "industry": jd["industry"] if jd and jd.get("industry") else "未分类",
            }
        )

    by_job = {}
    for row in rows:
        item = by_job.setdefault(
            row.jd_id,
            {
                "jd_id": row.jd_id,
                "jd_title": "",
                "jd_company": "",
                "industry": "未分类",
                "like": 0,
                "dislike": 0,
                "total": 0,
                "_scores": [],
            },
        )
        jd = jd_map.get(row.jd_id)
        if jd:
            item["jd_title"] = jd["title"]
            item["jd_company"] = jd["company"] or ""
            item["industry"] = jd["industry"] or "未分类"
        item[row.feedback_type] += 1
        item["total"] += 1
        if row.match_score is not None:
            item["_scores"].append(row.match_score)

    top_jobs = []
    mismatch_jobs = []
    for item in by_job.values():
        scores_for_job = item.pop("_scores", [])
        item["avg_match_score"] = _mean_or_none(scores_for_job, digits=2)
        item["like_rate"] = round(item["like"] / item["total"], 4) if item["total"] else 0
        item["dislike_rate"] = round(item["dislike"] / item["total"], 4) if item["total"] else 0
        top_jobs.append(item)
        if item["total"] >= 2 and item["dislike"] >= item["like"]:
            mismatch_jobs.append(item)
    top_jobs.sort(key=lambda x: (x["total"], x["like"]), reverse=True)
    mismatch_jobs.sort(key=lambda x: (x["dislike_rate"], x["total"]), reverse=True)

    trend_days = 7
    latest_day = max((row.created_at.date() for row in rows if row.created_at), default=None)
    trend_map: dict[str, dict] = {}
    if latest_day:
        for offset in range(trend_days - 1, -1, -1):
            day = latest_day - timedelta(days=offset)
            trend_map[day.isoformat()] = {
                "date": day.isoformat(),
                "like": 0,
                "dislike": 0,
                "total": 0,
                "avg_match_score": None,
                "_scores": [],
            }
        for row in rows:
            if not row.created_at:
                continue
            day_key = row.created_at.date().isoformat()
            if day_key not in trend_map:
                continue
            point = trend_map[day_key]
            point[row.feedback_type] += 1
            point["total"] += 1
            if row.match_score is not None:
                point["_scores"].append(row.match_score)
    trend = []
    for point in trend_map.values():
        scores_for_day = point.pop("_scores", [])
        if scores_for_day:
            point["avg_match_score"] = _mean_or_none(scores_for_day, digits=2)
        trend.append(point)

    resume_stats: dict[int, dict] = {}
    industry_stats: dict[str, dict] = {}
    weak_industry_candidates: list[dict] = []
    high_score_dislikes: list[dict] = []
    low_score_likes: list[dict] = []
    calibration_buckets: dict[str, dict] = {}
    active_dates = set()

    for row in rows:
        resume = resume_map.get(row.resume_id)
        jd = jd_map.get(row.jd_id)
        if row.created_at:
            active_dates.add(row.created_at.date().isoformat())

        resume_item = resume_stats.setdefault(
            row.resume_id,
            {
                "resume_id": row.resume_id,
                "resume_title": _safe_resume_label(resume),
                "like": 0,
                "dislike": 0,
                "total": 0,
                "_scores": [],
            },
        )
        resume_item[row.feedback_type] += 1
        resume_item["total"] += 1
        if row.match_score is not None:
            resume_item["_scores"].append(row.match_score)

        industry = jd["industry"] if jd and jd.get("industry") else "未分类"
        industry_item = industry_stats.setdefault(
            industry,
            {
                "industry": industry,
                "like": 0,
                "dislike": 0,
                "total": 0,
                "_scores": [],
            },
        )
        industry_item[row.feedback_type] += 1
        industry_item["total"] += 1
        if row.match_score is not None:
            industry_item["_scores"].append(row.match_score)

        bucket = calibration_buckets.setdefault(
            _score_bucket_label(row.match_score),
            {
                "bucket": _score_bucket_label(row.match_score),
                "like": 0,
                "dislike": 0,
                "total": 0,
                "like_rate": 0,
                "avg_match_score": None,
                "_scores": [],
            },
        )
        bucket[row.feedback_type] += 1
        bucket["total"] += 1
        if row.match_score is not None:
            bucket["_scores"].append(row.match_score)

        if row.feedback_type == "dislike" and row.match_score is not None and row.match_score >= 80:
            high_score_dislikes.append(
                {
                    "resume_id": row.resume_id,
                    "resume_title": _safe_resume_label(resume),
                    "jd_id": row.jd_id,
                    "jd_title": jd["title"] if jd else "",
                    "jd_company": jd["company"] if jd else "",
                    "industry": industry,
                    "match_score": row.match_score,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
        if row.feedback_type == "like" and row.match_score is not None and row.match_score < 60:
            low_score_likes.append(
                {
                    "resume_id": row.resume_id,
                    "resume_title": _safe_resume_label(resume),
                    "jd_id": row.jd_id,
                    "jd_title": jd["title"] if jd else "",
                    "jd_company": jd["company"] if jd else "",
                    "industry": industry,
                    "match_score": row.match_score,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )

    by_resume = []
    mismatch_resumes = []
    for item in resume_stats.values():
        scores_for_resume = item.pop("_scores", [])
        item["avg_match_score"] = _mean_or_none(scores_for_resume, digits=2)
        item["like_rate"] = round(item["like"] / item["total"], 4) if item["total"] else 0
        item["dislike_rate"] = round(item["dislike"] / item["total"], 4) if item["total"] else 0
        by_resume.append(item)
        if item["total"] >= 2 and item["dislike"] >= item["like"]:
            mismatch_resumes.append(item)
    by_resume.sort(key=lambda x: (x["total"], x["like"]), reverse=True)
    mismatch_resumes.sort(key=lambda x: (x["dislike_rate"], x["total"]), reverse=True)

    by_industry = []
    for item in industry_stats.values():
        scores_for_industry = item.pop("_scores", [])
        item["avg_match_score"] = _mean_or_none(scores_for_industry, digits=2)
        item["like_rate"] = round(item["like"] / item["total"], 4) if item["total"] else 0
        item["dislike_rate"] = round(item["dislike"] / item["total"], 4) if item["total"] else 0
        by_industry.append(item)
        if item["total"] >= 2 and item["dislike"] >= item["like"]:
            weak_industry_candidates.append(item)
    by_industry.sort(key=lambda x: (x["total"], x["like"]), reverse=True)
    weak_industries = sorted(
        weak_industry_candidates,
        key=lambda x: (x["dislike_rate"], x["total"]),
        reverse=True,
    )[:3]

    calibration_bucket_items = []
    for item in calibration_buckets.values():
        scores_for_bucket = item.pop("_scores", [])
        item["avg_match_score"] = _mean_or_none(scores_for_bucket, digits=2)
        item["like_rate"] = round(item["like"] / item["total"], 4) if item["total"] else 0
        calibration_bucket_items.append(item)
    calibration_bucket_items.sort(key=lambda x: x["bucket"])

    high_score_dislikes = high_score_dislikes[:5]
    low_score_likes = low_score_likes[:5]
    action_items = _build_feedback_action_items(
        total=total,
        like_count=like_count,
        dislike_count=dislike_count,
        high_score_dislikes=high_score_dislikes,
        low_score_likes=low_score_likes,
        weak_industries=weak_industries,
    )

    anomaly_count = len(high_score_dislikes) + len(low_score_likes)
    alignment_score = (
        max(
            min(
                round((like_rate * 100) - (anomaly_count * 6) - (len(weak_industries) * 4) + 35),
                100,
            ),
            0,
        )
        if total
        else 0
    )

    return {
        "total": total,
        "like_count": like_count,
        "dislike_count": dislike_count,
        "like_rate": like_rate,
        "dislike_rate": dislike_rate,
        "avg_match_score": avg_match_score,
        "recent_feedback": recent,
        "top_jobs": top_jobs[:5],
        "trend": trend,
        "by_resume": by_resume[:5],
        "by_industry": by_industry[:5],
        "tuning_signals": {
            "high_score_dislikes": high_score_dislikes,
            "low_score_likes": low_score_likes,
            "weak_industries": weak_industries,
            "action_items": action_items,
        },
        "evaluation": {
            "alignment_score": alignment_score,
            "coverage": {
                "unique_resume_count": len(resume_ids),
                "unique_job_count": len(jd_ids),
                "unique_industry_count": len(industry_stats),
                "active_days": len(active_dates),
            },
            "calibration": {
                "buckets": calibration_bucket_items,
                "high_score_dislike_count": len(high_score_dislikes),
                "low_score_like_count": len(low_score_likes),
            },
            "mismatch_focus": {
                "jobs": mismatch_jobs[:5],
                "resumes": mismatch_resumes[:5],
                "industries": weak_industries,
            },
            "sample_health": {
                "enough_for_tuning": total >= 10,
                "enough_for_industry_view": len(industry_stats) >= 2,
                "enough_for_resume_view": len(resume_stats) >= 2,
            },
        },
    }


def _build_feedback_tuning_recommendation(db: Session, *, user_id: int) -> dict:
    analysis = _build_feedback_analysis(db, user_id=user_id)
    samples = _build_tuning_samples(db, user_id=user_id, anomaly_only=True)
    current_config = get_recommendation_tuning_config(user_id)
    return build_feedback_tuning_recommendation(analysis, samples, current_config=current_config)


@router.get("/recommend-config", summary="Get recommendation tuning config")
async def get_recommend_config(
    current_user: User = Depends(get_current_user),
):
    return ok(get_recommendation_tuning_config(current_user.id))


@router.put("/recommend-config", summary="Update recommendation tuning config")
async def update_recommend_config(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
):
    try:
        config = save_recommendation_tuning_config(current_user.id, payload)
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    JobRecommendationEngine.clear_cache()
    return ok(config, message="recommendation config updated")


@router.post("/recommend-config/reset", summary="Reset recommendation tuning config")
async def reset_recommend_config(
    current_user: User = Depends(get_current_user),
):
    config = reset_recommendation_tuning_config(current_user.id)
    JobRecommendationEngine.clear_cache()
    return ok(config, message="recommendation config reset")


@router.post("/recommend-config/compare", summary="Compare two recommendation configs")
async def compare_recommend_config(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        config_a = payload.get("config_a") or get_recommendation_tuning_config(current_user.id)
        config_b = payload.get("config_b") or get_recommendation_tuning_config(current_user.id)
        label_a = str(payload.get("label_a") or "配置 A")
        label_b = str(payload.get("label_b") or "配置 B")
        from app.services.recommendation_tuning import validate_recommendation_tuning_config

        config_a = validate_recommendation_tuning_config(config_a)
        config_b = validate_recommendation_tuning_config(config_b)
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)

    rows, resume_map, jd_map, embedding_by_key = _build_compare_sample_context(db, user_id=current_user.id)
    scored_a = _score_feedback_rows(
        db,
        rows=rows,
        resume_map=resume_map,
        jd_map=jd_map,
        embedding_by_key=embedding_by_key,
        tuning_config=config_a,
        label=label_a,
    )
    scored_b = _score_feedback_rows(
        db,
        rows=rows,
        resume_map=resume_map,
        jd_map=jd_map,
        embedding_by_key=embedding_by_key,
        tuning_config=config_b,
        label=label_b,
    )
    return ok(
        {
            "sample_total": len(scored_a["items"]),
            "variant_a": {
                "label": label_a,
                "config": config_a,
                "summary": scored_a["summary"],
            },
            "variant_b": {
                "label": label_b,
                "config": config_b,
                "summary": scored_b["summary"],
            },
            "delta": _compare_scored_variants(scored_a, scored_b),
        }
    )


def _build_tuning_tags(
    *,
    row: dict,
    sample: dict,
    weak_industries: set[str],
) -> list[str]:
    tags: list[str] = []
    if row["feedback_type"] == "dislike" and row["match_score"] is not None and row["match_score"] >= 80:
        tags.append("high_score_dislike")
    if row["feedback_type"] == "like" and row["match_score"] is not None and row["match_score"] < 60:
        tags.append("low_score_like")
    if sample["industry"] in weak_industries:
        tags.append("weak_industry")
    if not sample["salary_match"]:
        tags.append("salary_gap")
    if not sample["location_match"]:
        tags.append("location_gap")
    if not sample["experience_match"]:
        tags.append("experience_gap")
    if len(sample["skill_gap"]) >= 3:
        tags.append("skill_gap_heavy")
    if sample["vector_score"] - sample["rule_score"] >= 20:
        tags.append("vector_rule_diverge")
    return tags


def _build_tuning_samples(db: Session, *, user_id: int, anomaly_only: bool = True) -> list[dict]:
    rows = [
        {
            "id": row.id,
            "user_id": row.user_id,
            "resume_id": row.resume_id,
            "jd_id": row.jd_id,
            "feedback_type": row.feedback_type,
            "match_score": row.match_score,
            "created_at": row.created_at,
        }
        for row in (
            db.query(JobRecommendationFeedback)
            .filter(tenant_filter(JobRecommendationFeedback), JobRecommendationFeedback.user_id == user_id)
            .order_by(JobRecommendationFeedback.created_at.desc(), JobRecommendationFeedback.id.desc())
            .all()
        )
    ]
    if not rows:
        return []

    analysis = _build_feedback_analysis(db, user_id=user_id)
    weak_industries = {
        item["industry"]
        for item in analysis.get("evaluation", {}).get("mismatch_focus", {}).get("industries", [])
        if item.get("industry")
    }

    resume_ids = sorted({row["resume_id"] for row in rows})
    jd_ids = sorted({row["jd_id"] for row in rows})
    resume_map = (
        {
            item.id: {
                "id": item.id,
                "name": item.name,
                "file_name": item.file_name,
                "parsed_json": item.parsed_json or {},
            }
            for item in db.query(Resume).filter(Resume.id.in_(resume_ids)).all()
        }
        if resume_ids
        else {}
    )
    jd_map = (
        {
            item.id: {
                "id": item.id,
                "title": item.title,
                "company": item.company,
                "location": item.location,
                "salary_range": item.salary_range,
                "industry": item.industry,
                "raw_text": item.raw_text,
                "parsed_json": item.parsed_json or {},
                "source": item.source,
                "experience_requirement": item.experience_requirement,
            }
            for item in db.query(JobDescription).filter(JobDescription.id.in_(jd_ids)).all()
        }
        if jd_ids
        else {}
    )

    tuning_config = get_recommendation_tuning_config(user_id)
    engine = JobRecommendationEngine(db, tuning_config=tuning_config)
    resume_text_by_id: dict[int, str] = {}
    jd_text_by_id: dict[int, str] = {}
    text_keys: list[str] = []
    text_map: dict[str, str] = {}
    for resume in resume_map.values():
        text = engine._build_vector_text(resume["parsed_json"] or {})
        key = f"resume:{resume['id']}"
        text_keys.append(key)
        text_map[key] = text
        resume_text_by_id[resume["id"]] = text
    for jd in jd_map.values():
        text = jd["raw_text"] or engine._build_vector_text(jd["parsed_json"] or {})
        key = f"jd:{jd['id']}"
        text_keys.append(key)
        text_map[key] = text
        jd_text_by_id[jd["id"]] = text

    embedding_by_key: dict[str, list[float] | None] = dict.fromkeys(text_keys)
    try:
        from app.services.embedding_service import embed_texts

        emb_values = embed_texts([text_map[key] for key in text_keys])
        for key, emb in zip(text_keys, emb_values, strict=False):
            embedding_by_key[key] = emb
    except Exception:
        pass

    samples = []
    for row in rows:
        resume = resume_map.get(row["resume_id"])
        jd = jd_map.get(row["jd_id"])
        if not resume or not jd:
            continue

        resume_json = resume["parsed_json"] or {}
        jd_json = jd["parsed_json"] or {}
        resume_skills = engine._extract_skills(resume_json)
        jd_skills = engine._extract_skills(jd_json)
        overlap = sorted(set(resume_skills) & set(jd_skills))
        gap = sorted(set(jd_skills) - set(resume_skills))

        resume_salary = engine._parse_salary(resume_json.get("expected_salary", "") or "")
        jd_salary = engine._parse_salary(jd["salary_range"] or "")
        salary_match = engine._salary_match(resume_salary, jd_salary) if resume_salary[0] is not None else True

        resume_location = resume_json.get("location", resume_json.get("city", ""))
        location_match = engine._location_match(resume_location, jd["location"] or "") if resume_location else True
        experience_match = engine._experience_match(resume_json.get("years_exp", 0), jd_json)
        jd_stub = SimpleNamespace(
            salary_range=jd["salary_range"] or "",
            location=jd["location"] or "",
            experience_requirement=jd.get("experience_requirement") or "",
        )

        vector_score = engine._vector_score(
            embedding_by_key.get(f"resume:{resume['id']}"),
            embedding_by_key.get(f"jd:{jd['id']}"),
        )
        rule_score = engine._rule_score(resume_json, jd_stub, jd_json)
        recommendation_type = engine._recommend_type(
            row["match_score"] or (vector_score * engine.WEIGHT_VECTOR + rule_score * engine.WEIGHT_RULE)
        )
        sample = {
            "feedback_id": row["id"],
            "feedback_type": row["feedback_type"],
            "match_score": row["match_score"],
            "score_bucket": _score_bucket_label(row["match_score"]),
            "resume_id": row["resume_id"],
            "resume_title": resume["name"] or resume["file_name"] or f"Resume {resume['id']}",
            "jd_id": row["jd_id"],
            "jd_title": jd["title"],
            "jd_company": jd["company"] or "",
            "industry": jd["industry"] or "未分类",
            "vector_score": round(vector_score, 2),
            "rule_score": round(rule_score, 2),
            "recommendation_type": recommendation_type,
            "skill_overlap": overlap[:8],
            "skill_gap": gap[:8],
            "salary_match": salary_match,
            "location_match": location_match,
            "experience_match": experience_match,
            "match_reason": engine._generate_reason(
                row["match_score"] or (vector_score * engine.WEIGHT_VECTOR + rule_score * engine.WEIGHT_RULE),
                overlap,
                gap,
                salary_match,
                location_match,
            ),
            "feedback_created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        sample["tuning_tags"] = _build_tuning_tags(row=row, sample=sample, weak_industries=weak_industries)

        if anomaly_only and not sample["tuning_tags"]:
            continue
        samples.append(sample)

    samples.sort(key=lambda item: (len(item["tuning_tags"]), item["feedback_created_at"] or ""), reverse=True)
    return samples


def _build_compare_sample_context(
    db: Session, *, user_id: int
) -> tuple[list[dict], dict[int, dict], dict[int, dict], dict[str, list[float] | None]]:
    rows = [
        {
            "id": row.id,
            "resume_id": row.resume_id,
            "jd_id": row.jd_id,
            "feedback_type": row.feedback_type,
            "match_score": row.match_score,
            "created_at": row.created_at,
        }
        for row in (
            db.query(JobRecommendationFeedback)
            .filter(tenant_filter(JobRecommendationFeedback), JobRecommendationFeedback.user_id == user_id)
            .order_by(JobRecommendationFeedback.created_at.desc(), JobRecommendationFeedback.id.desc())
            .all()
        )
    ]
    resume_ids = sorted({row["resume_id"] for row in rows})
    jd_ids = sorted({row["jd_id"] for row in rows})
    resume_map = (
        {
            item.id: {
                "id": item.id,
                "name": item.name,
                "file_name": item.file_name,
                "parsed_json": item.parsed_json or {},
            }
            for item in db.query(Resume).filter(Resume.id.in_(resume_ids)).all()
        }
        if resume_ids
        else {}
    )
    jd_map = (
        {
            item.id: {
                "id": item.id,
                "title": item.title,
                "company": item.company,
                "location": item.location,
                "salary_range": item.salary_range,
                "industry": item.industry,
                "raw_text": item.raw_text,
                "parsed_json": item.parsed_json or {},
                "experience_requirement": item.experience_requirement,
            }
            for item in db.query(JobDescription).filter(JobDescription.id.in_(jd_ids)).all()
        }
        if jd_ids
        else {}
    )

    base_engine = JobRecommendationEngine(db)
    text_keys: list[str] = []
    text_map: dict[str, str] = {}
    for resume in resume_map.values():
        key = f"resume:{resume['id']}"
        text_keys.append(key)
        text_map[key] = base_engine._build_vector_text(resume["parsed_json"] or {})
    for jd in jd_map.values():
        key = f"jd:{jd['id']}"
        text_keys.append(key)
        text_map[key] = jd["raw_text"] or base_engine._build_vector_text(jd["parsed_json"] or {})

    embedding_by_key: dict[str, list[float] | None] = dict.fromkeys(text_keys)
    try:
        from app.services.embedding_service import embed_texts

        emb_values = embed_texts([text_map[key] for key in text_keys])
        for key, emb in zip(text_keys, emb_values, strict=False):
            embedding_by_key[key] = emb
    except Exception:
        pass

    return rows, resume_map, jd_map, embedding_by_key


def _score_feedback_rows(
    db: Session,
    *,
    rows: list[dict],
    resume_map: dict[int, dict],
    jd_map: dict[int, dict],
    embedding_by_key: dict[str, list[float] | None],
    tuning_config: dict,
    label: str,
) -> dict:
    engine = JobRecommendationEngine(db, tuning_config=tuning_config)
    items = []
    agreement_count = 0
    high_score_dislike_count = 0
    low_score_like_count = 0

    for row in rows:
        resume = resume_map.get(row["resume_id"])
        jd = jd_map.get(row["jd_id"])
        if not resume or not jd:
            continue

        resume_json = resume["parsed_json"] or {}
        jd_json = jd["parsed_json"] or {}
        jd_stub = SimpleNamespace(
            salary_range=jd["salary_range"] or "",
            location=jd["location"] or "",
            experience_requirement=jd.get("experience_requirement") or "",
        )
        vector_score = engine._vector_score(
            embedding_by_key.get(f"resume:{resume['id']}"),
            embedding_by_key.get(f"jd:{jd['id']}"),
        )
        rule_score = engine._rule_score(resume_json, jd_stub, jd_json)
        combined_score = round(vector_score * engine._vector_weight + rule_score * engine._rule_weight, 2)
        recommendation_type = engine._recommend_type(combined_score)
        predicted_positive = combined_score >= engine.THRESHOLD_MEDIUM
        agreed = (row["feedback_type"] == "like" and predicted_positive) or (
            row["feedback_type"] == "dislike" and not predicted_positive
        )
        if agreed:
            agreement_count += 1
        if row["feedback_type"] == "dislike" and combined_score >= 80:
            high_score_dislike_count += 1
        if row["feedback_type"] == "like" and combined_score < 60:
            low_score_like_count += 1

        items.append(
            {
                "feedback_id": row["id"],
                "resume_id": row["resume_id"],
                "resume_title": _safe_resume_label(resume),
                "jd_id": row["jd_id"],
                "jd_title": jd["title"],
                "feedback_type": row["feedback_type"],
                "vector_score": round(vector_score, 2),
                "rule_score": round(rule_score, 2),
                "combined_score": combined_score,
                "recommendation_type": recommendation_type,
                "predicted_positive": predicted_positive,
                "agreed": agreed,
            }
        )

    total = len(items)
    return {
        "label": label,
        "config": deepcopy(tuning_config),
        "summary": {
            "total": total,
            "agreement_count": agreement_count,
            "agreement_rate": round(agreement_count / total, 4) if total else 0,
            "avg_combined_score": _mean_or_none([item["combined_score"] for item in items], digits=2),
            "high_score_dislike_count": high_score_dislike_count,
            "low_score_like_count": low_score_like_count,
        },
        "items": items,
    }


def _compare_scored_variants(left: dict, right: dict) -> dict:
    right_by_id = {item["feedback_id"]: item for item in right["items"]}
    movers = []
    for left_item in left["items"]:
        right_item = right_by_id.get(left_item["feedback_id"])
        if not right_item:
            continue
        score_delta = round(right_item["combined_score"] - left_item["combined_score"], 2)
        if score_delta == 0 and right_item["agreed"] == left_item["agreed"]:
            continue
        movers.append(
            {
                "feedback_id": left_item["feedback_id"],
                "resume_title": left_item["resume_title"],
                "jd_title": left_item["jd_title"],
                "feedback_type": left_item["feedback_type"],
                "score_a": left_item["combined_score"],
                "score_b": right_item["combined_score"],
                "score_delta": score_delta,
                "agreed_a": left_item["agreed"],
                "agreed_b": right_item["agreed"],
                "type_a": left_item["recommendation_type"],
                "type_b": right_item["recommendation_type"],
            }
        )
    movers.sort(key=lambda item: (abs(item["score_delta"]), item["agreed_b"] != item["agreed_a"]), reverse=True)
    return {
        "agreement_rate": round(
            float(right["summary"]["agreement_rate"]) - float(left["summary"]["agreement_rate"]),
            4,
        ),
        "avg_combined_score": round(
            float(right["summary"]["avg_combined_score"] or 0) - float(left["summary"]["avg_combined_score"] or 0),
            2,
        ),
        "high_score_dislike_count": right["summary"]["high_score_dislike_count"]
        - left["summary"]["high_score_dislike_count"],
        "low_score_like_count": right["summary"]["low_score_like_count"] - left["summary"]["low_score_like_count"],
        "top_movers": movers[:12],
    }


@router.get("/recommend", summary="Recommend jobs")
async def recommend_jobs(
    resume_id: int = Query(..., description="Resume ID"),
    limit: int = Query(5, ge=1, le=20, description="Result size"),
    location: str | None = Query(None, description="Location filter"),
    salary_min: int | None = Query(None, description="Minimum salary"),
    industry: str | None = Query(None, description="Industry filter"),
    exp_level: str | None = Query(None, description="Experience level filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="resume not found", code=ERR_PARAM)

    filters = {}
    if location:
        filters["location"] = location
    if salary_min is not None:
        filters["salary_min"] = salary_min
    if industry:
        filters["industry"] = industry
    if exp_level:
        filters["exp_level"] = exp_level

    try:
        tuning_config = get_recommendation_tuning_config(current_user.id)
        results = JobRecommendationEngine(db, tuning_config=tuning_config).recommend(
            resume_id=resume.id,
            limit=limit,
            filters=filters,
        )
        return ok(
            data={
                "resume_id": resume_id,
                "total": len(results),
                "recommendations": results,
            },
            message=f"recommended {len(results)} jobs",
        )
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"recommendation failed: {str(exc)[:100]}", code=ERR_COMMON)


@router.post("/batch-import", summary="Batch import jobs")
async def batch_import(
    file: UploadFile = File(...),
    source: str = Form("imported"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    file_name = (file.filename or "").lower()
    count = 0

    try:
        if file_name.endswith(".csv"):
            text = content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                title = (row.get("title") or row.get("职位名称") or "").strip()
                company = (row.get("company") or row.get("公司") or "").strip()
                raw_text = (
                    row.get("raw_text") or row.get("rawText") or row.get("JD文本") or row.get("jd_text") or ""
                ).strip()
                if not title or not raw_text:
                    continue
                db.add(
                    stamp_tenant(
                        JobDescription(
                            user_id=current_user.id,
                            title=title,
                            company=company,
                            location=(row.get("location") or row.get("地点") or "").strip(),
                            salary_range=(row.get("salary_range") or row.get("薪资") or "").strip(),
                            industry=(row.get("industry") or row.get("行业") or "").strip(),
                            raw_text=raw_text,
                            source=source,
                        )
                    )
                )
                count += 1
        elif file_name.endswith(".json"):
            text = content.decode("utf-8")
            data = json.loads(text)
            items = data if isinstance(data, list) else data.get("jobs", data.get("items", []))
            for item in items:
                title = (item.get("title") or item.get("职位名称") or "").strip()
                raw_text = (
                    item.get("raw_text") or item.get("rawText") or item.get("jd_text") or item.get("description") or ""
                ).strip()
                if not title or not raw_text:
                    continue
                db.add(
                    stamp_tenant(
                        JobDescription(
                            user_id=current_user.id,
                            title=title,
                            company=(item.get("company") or "").strip(),
                            location=(item.get("location") or "").strip(),
                            salary_range=(item.get("salary_range") or "").strip(),
                            industry=(item.get("industry") or "").strip(),
                            raw_text=raw_text,
                            source=source,
                        )
                    )
                )
                count += 1
        else:
            return fail(message="only CSV and JSON are supported", code=ERR_PARAM)

        db.commit()
        JobRecommendationEngine.clear_cache()
        return ok(data={"imported_count": count}, message=f"imported {count} jobs")
    except Exception as exc:
        db.rollback()
        traceback.print_exc()
        return fail(message=f"import failed: {str(exc)[:100]}", code=ERR_COMMON)


@router.post("/seed", summary="Seed demo jobs")
async def seed_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mock_jobs = [
        {
            "title": "Python Backend Engineer",
            "company": "ByteDance",
            "location": "Beijing",
            "salary_range": "25k-45k",
            "industry": "Internet",
            "raw_text": "Build backend services with Python, FastAPI, MySQL, and Redis.",
        },
        {
            "title": "Senior Frontend Engineer",
            "company": "Alibaba",
            "location": "Hangzhou",
            "salary_range": "30k-50k",
            "industry": "Internet",
            "raw_text": "Develop large-scale Vue and React applications with TypeScript.",
        },
        {
            "title": "AI Algorithm Engineer",
            "company": "Tencent",
            "location": "Shenzhen",
            "salary_range": "35k-60k",
            "industry": "AI",
            "raw_text": "Work on LLM, NLP, and model inference optimization.",
        },
        {
            "title": "Java Backend Engineer",
            "company": "Meituan",
            "location": "Beijing",
            "salary_range": "20k-35k",
            "industry": "Internet",
            "raw_text": "Build microservices with Java, Spring Cloud, MySQL, and MQ.",
        },
        {
            "title": "Full Stack Engineer",
            "company": "Xiaohongshu",
            "location": "Shanghai",
            "salary_range": "28k-45k",
            "industry": "Internet",
            "raw_text": "Deliver product features across Python/Node and Vue/React.",
        },
        {
            "title": "Data Analyst",
            "company": "JD.com",
            "location": "Beijing",
            "salary_range": "20k-35k",
            "industry": "E-commerce",
            "raw_text": "Analyze user growth and business data with SQL and Python.",
        },
        {
            "title": "DevOps Engineer",
            "company": "Huawei",
            "location": "Shenzhen",
            "salary_range": "25k-40k",
            "industry": "Cloud",
            "raw_text": "Maintain CI/CD pipelines and container infrastructure with Docker and Kubernetes.",
        },
        {
            "title": "AI Product Manager",
            "company": "Baidu",
            "location": "Beijing",
            "salary_range": "25k-45k",
            "industry": "AI",
            "raw_text": "Plan AI products from requirement analysis to launch.",
        },
        {
            "title": "Test Development Engineer",
            "company": "NetEase",
            "location": "Guangzhou",
            "salary_range": "20k-35k",
            "industry": "Internet",
            "raw_text": "Improve testing efficiency with automation and performance tooling.",
        },
        {
            "title": "Data Engineer",
            "company": "Kuaishou",
            "location": "Beijing",
            "salary_range": "25k-45k",
            "industry": "Data",
            "raw_text": "Build ETL pipelines and maintain data warehouse quality.",
        },
    ]

    count = 0
    for job in mock_jobs:
        existing = (
            db.query(JobDescription)
            .filter(
                JobDescription.user_id == current_user.id,
                JobDescription.title == job["title"],
                JobDescription.company == job["company"],
            )
            .first()
        )
        if existing:
            continue

        db.add(
            stamp_tenant(
                JobDescription(
                    user_id=current_user.id,
                    title=job["title"],
                    company=job["company"],
                    location=job["location"],
                    salary_range=job["salary_range"],
                    industry=job["industry"],
                    raw_text=job["raw_text"],
                    source="api",
                )
            )
        )
        count += 1

    db.commit()
    JobRecommendationEngine.clear_cache()
    return ok(data={"seeded_count": count}, message=f"seeded {count} jobs")


@router.post("/feedback", summary="Submit recommendation feedback")
async def submit_feedback(
    resume_id: int = Query(...),
    jd_id: int = Query(...),
    feedback_type: str = Query(..., pattern="^(like|dislike)$"),
    match_score: float | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="resume not found", code=ERR_PARAM)

    jd = db.get(JobDescription, jd_id)
    if not jd or not _can_access_job(jd, current_user):
        return fail(message="job not found", code=ERR_PARAM)

    db.add(
        stamp_tenant(
            JobRecommendationFeedback(
                user_id=current_user.id,
                resume_id=resume_id,
                jd_id=jd_id,
                feedback_type=feedback_type,
                match_score=match_score,
            )
        )
    )
    db.commit()
    return ok(message="feedback recorded")


@router.get("/feedback/stats", summary="Recommendation feedback summary")
async def feedback_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = _build_feedback_analysis(db, user_id=current_user.id)
    return ok(data)


@router.get("/feedback/evaluation", summary="Recommendation feedback evaluation dashboard")
async def feedback_evaluation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analysis = _build_feedback_analysis(db, user_id=current_user.id)
    tuning_recommendation = _build_feedback_tuning_recommendation(db, user_id=current_user.id)
    return ok(
        {
            **analysis,
            "tuning_recommendation": tuning_recommendation,
        }
    )


@router.get("/feedback/tuning-samples", summary="Recommendation tuning samples")
async def feedback_tuning_samples(
    anomaly_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    samples = _build_tuning_samples(db, user_id=current_user.id, anomaly_only=anomaly_only)
    return ok(
        {
            "total": len(samples),
            "anomaly_only": anomaly_only,
            "items": samples[:100],
        }
    )


@router.get("/feedback/tuning-export", summary="Export recommendation tuning samples")
async def export_feedback_tuning_samples(
    format: str = Query("csv", pattern="^(csv|json)$"),
    anomaly_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    samples = _build_tuning_samples(db, user_id=current_user.id, anomaly_only=anomaly_only)
    if format == "json":
        payload = json.dumps(
            {"total": len(samples), "anomaly_only": anomaly_only, "items": samples},
            ensure_ascii=False,
            indent=2,
        )
        return StreamingResponse(
            iter([payload.encode("utf-8")]),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="recommend_tuning_samples.json"'},
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "feedback_id",
            "feedback_type",
            "match_score",
            "score_bucket",
            "resume_id",
            "resume_title",
            "jd_id",
            "jd_title",
            "jd_company",
            "industry",
            "vector_score",
            "rule_score",
            "recommendation_type",
            "salary_match",
            "location_match",
            "experience_match",
            "skill_overlap",
            "skill_gap",
            "tuning_tags",
            "match_reason",
            "feedback_created_at",
        ]
    )
    for item in samples:
        writer.writerow(
            [
                item["feedback_id"],
                item["feedback_type"],
                item["match_score"],
                item["score_bucket"],
                item["resume_id"],
                item["resume_title"],
                item["jd_id"],
                item["jd_title"],
                item["jd_company"],
                item["industry"],
                item["vector_score"],
                item["rule_score"],
                item["recommendation_type"],
                item["salary_match"],
                item["location_match"],
                item["experience_match"],
                " | ".join(item["skill_overlap"]),
                " | ".join(item["skill_gap"]),
                " | ".join(item["tuning_tags"]),
                item["match_reason"],
                item["feedback_created_at"],
            ]
        )
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="recommend_tuning_samples.csv"'},
    )


@router.post("/feedback/apply-tuning", summary="Apply feedback-driven tuning suggestion")
async def apply_feedback_tuning(
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = int(current_user.id)
    analysis = _build_feedback_analysis(db, user_id=user_id)
    samples = _build_tuning_samples(db, user_id=user_id, anomaly_only=True)
    current_config = get_recommendation_tuning_config(user_id)
    recommendation = build_feedback_tuning_recommendation(
        analysis,
        samples,
        current_config=current_config,
    )

    if payload.get("dry_run", True):
        return ok(recommendation)

    if not recommendation.get("sample_total"):
        return fail(message="not enough feedback samples", code=ERR_PARAM)

    try:
        saved = save_recommendation_tuning_config(user_id, recommendation["suggested_config"])
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)

    JobRecommendationEngine.clear_cache()
    return ok(
        {
            **recommendation,
            "saved_config": saved,
        },
        message="feedback-driven tuning applied",
    )


@router.get("/list", summary="List jobs")
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str | None = Query(None, description="manual/imported/api"),
    industry: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(JobDescription).filter(JobDescription.is_active == 1)
    if not _is_admin(current_user):
        query = query.filter(_job_visibility_filter(current_user.id))
    if source:
        query = query.filter(JobDescription.source == source)
    if industry:
        query = query.filter(JobDescription.industry == industry)

    query = query.order_by(JobDescription.create_time.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return ok(
        {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": item.id,
                    "title": item.title,
                    "company": item.company,
                    "location": item.location,
                    "salary_range": item.salary_range,
                    "industry": item.industry,
                    "source": item.source,
                    "create_time": item.create_time.isoformat() if item.create_time else None,
                }
                for item in items
            ],
        }
    )


@router.get("/{jd_id}", summary="Get job detail")
async def get_jd_detail(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jd = db.get(JobDescription, jd_id)
    if not jd or not _can_access_job(jd, current_user):
        return fail(message="job not found", code=ERR_PARAM)

    # 附带收藏状态
    bookmark = (
        db.query(JobBookmark)
        .filter(
            tenant_filter(JobBookmark),
            JobBookmark.user_id == current_user.id,
            JobBookmark.jd_id == jd_id,
        )
        .first()
    )

    return ok(
        {
            "id": jd.id,
            "title": jd.title,
            "company": jd.company,
            "location": jd.location,
            "salary_range": jd.salary_range,
            "industry": jd.industry,
            "raw_text": jd.raw_text,
            "parsed": jd.parsed_json or {},
            "source": jd.source,
            "bookmark_action": bookmark.action if bookmark else None,
            "create_time": jd.create_time.isoformat() if jd.create_time else None,
        }
    )


# ============================================================
# 职位收藏 / 不感兴趣
# ============================================================

# Upper bound on the recovery list a single request may carry.
_SUPPRESSED_LIST_MAX = 200


@router.post("/bookmarks", summary="收藏/不感兴趣职位")
async def bookmark_job(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jd_id = payload.get("jd_id")
    action = payload.get("action")  # bookmark / dismiss
    note = payload.get("note", "")

    if not jd_id or not action:
        return fail(message="jd_id 和 action 必填", code=ERR_PARAM)
    if action not in ("bookmark", "dismiss"):
        return fail(message="action 仅支持 bookmark 或 dismiss", code=ERR_PARAM)

    jd = db.get(JobDescription, jd_id)
    if not jd or not _can_access_job(jd, current_user):
        return fail(message="职位不存在或无权限", code=ERR_PARAM)

    existing = (
        db.query(JobBookmark)
        .filter(
            tenant_filter(JobBookmark),
            JobBookmark.user_id == current_user.id,
            JobBookmark.jd_id == jd_id,
        )
        .first()
    )

    if existing:
        if action == "dismiss" and existing.action == "bookmark":
            # 取消收藏 → 删除
            db.delete(existing)
            db.commit()
            return ok(message="已取消收藏")
        existing.action = action
        existing.note = note or existing.note
        db.add(existing)
        db.commit()
        return ok(existing.to_dict(), message="已更新")

    bookmark = stamp_tenant(
        JobBookmark(
            user_id=current_user.id,
            jd_id=jd_id,
            action=action,
            note=note,
        )
    )
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    return ok(bookmark.to_dict(), message="收藏成功" if action == "bookmark" else "已标记不感兴趣")


@router.delete("/bookmarks/{jd_id}", summary="取消收藏/移除不感兴趣")
async def remove_bookmark(
    jd_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bookmark = (
        db.query(JobBookmark)
        .filter(
            tenant_filter(JobBookmark),
            JobBookmark.user_id == current_user.id,
            JobBookmark.jd_id == jd_id,
        )
        .first()
    )
    if not bookmark:
        return fail(message="未找到收藏记录", code=ERR_PARAM)
    db.delete(bookmark)
    db.commit()
    return ok(message="已移除")


@router.post("/bookmarks/restore", summary="恢复被隐藏的职位")
async def restore_job(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear every signal that hides a job, in one call.

    The candidate-facing alternative — "取消收藏" plus a separate feedback
    delete — would leave a job still hidden by a thumbs-down while the UI claimed
    it was restored. Idempotent by design: clicking 恢复 twice is not an error.
    """
    jd_id = payload.get("jd_id")
    if not jd_id:
        return fail(message="jd_id 必填", code=ERR_PARAM)

    cleared = {
        "dismiss": (
            db.query(JobBookmark)
            .filter(
                tenant_filter(JobBookmark),
                JobBookmark.user_id == current_user.id,
                JobBookmark.jd_id == jd_id,
                JobBookmark.action == "dismiss",
            )
            .delete(synchronize_session=False)
        ),
        "dislike": (
            db.query(JobRecommendationFeedback)
            .filter(
                tenant_filter(JobRecommendationFeedback),
                JobRecommendationFeedback.user_id == current_user.id,
                JobRecommendationFeedback.jd_id == jd_id,
                JobRecommendationFeedback.feedback_type == "dislike",
            )
            .delete(synchronize_session=False)
        ),
    }
    db.commit()
    return ok(
        {"jd_id": jd_id, **cleared},
        message="已恢复推荐" if any(cleared.values()) else "该职位当前未被隐藏",
    )


@router.get("/bookmarks/list", summary="获取收藏的职位列表")
async def list_bookmarks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        db.query(JobBookmark)
        .filter(
            tenant_filter(JobBookmark),
            JobBookmark.user_id == current_user.id,
            JobBookmark.action == "bookmark",
        )
        .order_by(JobBookmark.created_at.desc())
    )
    total = q.count()
    bookmarks = q.offset((page - 1) * page_size).limit(page_size).all()

    # 附带 JD 信息
    items = []
    for bm in bookmarks:
        jd = db.get(JobDescription, bm.jd_id)
        items.append(
            {
                **bm.to_dict(),
                "job": {
                    "id": jd.id,
                    "title": jd.title,
                    "company": jd.company,
                    "location": jd.location,
                    "salary_range": jd.salary_range,
                    "industry": jd.industry,
                }
                if jd
                else None,
            }
        )

    return ok({"total": total, "items": items})


@router.get("/bookmarks/dismissed", summary="获取被隐藏职位及原因")
async def list_dismissed(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reasons = load_suppressed_reasons(db, current_user.id)
    jobs = (
        db.query(JobDescription)
        .filter(JobDescription.id.in_(sorted(reasons)))
        .order_by(JobDescription.id.desc())
        .all()
        if reasons
        else []
    )
    visible = jobs[:_SUPPRESSED_LIST_MAX]
    items = [
        {
            "jd_id": jd.id,
            "job_title": jd.title,
            "company": jd.company,
            "location": jd.location,
            "reasons": reasons.get(jd.id, []),
        }
        for jd in visible
    ]
    # `total` counts suppression rows, which can outlive the job they point at, so
    # the two gaps are reported separately rather than folded into one number.
    return ok(
        {
            "total": len(reasons),
            "items": items,
            "orphaned": max(len(reasons) - len(jobs), 0),
            "truncated": max(len(jobs) - len(visible), 0),
        }
    )
