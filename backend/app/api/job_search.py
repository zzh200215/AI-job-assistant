"""Job search APIs: external crawl, local fallback, and demo seeds."""

from __future__ import annotations

import traceback

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import JobDescription
from app.models.user import User
from app.services.job_spider import JobItem, JobSpider
from app.utils.job_access import visible_job_filter
from app.utils.response import ERR_COMMON, fail, ok

router = APIRouter()
spider = JobSpider()


SUPPORTED_CITIES = [
    {"name": "北京", "code": "101010100"},
    {"name": "上海", "code": "101020100"},
    {"name": "广州", "code": "101280100"},
    {"name": "深圳", "code": "101280600"},
    {"name": "杭州", "code": "101210100"},
    {"name": "成都", "code": "101270100"},
    {"name": "南京", "code": "101190100"},
    {"name": "武汉", "code": "101200100"},
    {"name": "西安", "code": "101110100"},
    {"name": "长沙", "code": "101250100"},
    {"name": "苏州", "code": "101190400"},
    {"name": "重庆", "code": "101040100"},
    {"name": "全国", "code": ""},
]


SEED_JDS = [
    {
        "title": "Python 后端开发工程师",
        "company": "字节跳动",
        "location": "杭州",
        "salary_range": "25-40K·16薪",
        "experience": "3-5年",
        "education": "本科",
        "skill_tags": ["Python", "Django", "MySQL", "Redis", "Docker", "Kafka"],
        "industry": "互联网科技",
        "raw_text": "负责电商后端服务开发，使用 Python/Django 构建高并发订单系统。",
    },
    {
        "title": "AI 大模型算法工程师",
        "company": "阿里巴巴",
        "location": "杭州",
        "salary_range": "35-60K·16薪",
        "experience": "3-5年",
        "education": "硕士",
        "skill_tags": ["Python", "PyTorch", "LLM", "RAG", "LangChain", "Transformer"],
        "industry": "人工智能",
        "raw_text": "负责大模型训练、微调与 RAG 应用落地，参与 Agent 框架设计。",
    },
    {
        "title": "前端开发工程师",
        "company": "腾讯",
        "location": "深圳",
        "salary_range": "20-35K·15薪",
        "experience": "2-4年",
        "education": "本科",
        "skill_tags": ["Vue3", "React", "TypeScript", "Vite", "Node.js"],
        "industry": "互联网科技",
        "raw_text": "负责管理后台和业务中台前端开发，推进组件化和工程化建设。",
    },
    {
        "title": "数据分析师",
        "company": "美团",
        "location": "北京",
        "salary_range": "18-30K·15薪",
        "experience": "2-4年",
        "education": "本科",
        "skill_tags": ["SQL", "Python", "Tableau", "Hive", "Spark"],
        "industry": "互联网科技",
        "raw_text": "负责业务数据分析、指标体系建设与实验效果评估。",
    },
    {
        "title": "DevOps 工程师",
        "company": "京东",
        "location": "北京",
        "salary_range": "22-38K·14薪",
        "experience": "3-5年",
        "education": "本科",
        "skill_tags": ["Docker", "Kubernetes", "Jenkins", "Linux", "Prometheus"],
        "industry": "电商",
        "raw_text": "负责 CI/CD 流水线与容器集群运维，保障核心系统稳定交付。",
    },
]


def _to_result_item(jd: JobDescription) -> dict:
    parsed = jd.parsed_json or {}
    return {
        "id": jd.id,
        "title": jd.title,
        "company": jd.company or "",
        "salary": jd.salary_range or "",
        "location": jd.location or "",
        "experience": parsed.get("experience_requirement") or jd.experience_requirement or "",
        "education": parsed.get("education_requirement") or jd.education_requirement or "",
        "skill_tags": jd.skill_tags or parsed.get("required_skills", []),
        "industry": jd.industry or "",
        "jd_summary": parsed.get("jd_summary") or (jd.raw_text[:200] if jd.raw_text else ""),
        "raw_text": jd.raw_text or "",
        "source": jd.source or "local",
        "source_url": jd.external_url or "",
        "external_id": jd.external_id or "",
        "_local_db": True,
    }


def _is_demo_source(source_value: str | None) -> bool:
    return str(source_value or "").strip().lower() == "_mock"


def _search_local_jobs(db: Session, keyword: str, city: str, current_user: User, limit: int = 10) -> list[dict]:
    like_pattern = f"%{keyword.strip()}%"
    query = db.query(JobDescription).filter(JobDescription.is_active == 1)

    visibility = visible_job_filter(current_user)
    if visibility is not None:
        query = query.filter(visibility)

    query = query.filter(
        or_(
            JobDescription.title.like(like_pattern),
            JobDescription.company.like(like_pattern),
            JobDescription.raw_text.like(like_pattern),
            cast(JobDescription.skill_tags, String).like(like_pattern),
        )
    )
    if city:
        query = query.filter(JobDescription.location.like(f"%{city}%"))

    jobs = query.order_by(JobDescription.create_time.desc()).limit(limit).all()
    return [_to_result_item(job) for job in jobs]


def _save_external_jobs(db: Session, jobs: list[JobItem], current_user: User, save: bool) -> tuple[list[dict], int]:
    saved_count = 0
    results: list[dict] = []

    for job in jobs[:10]:
        if _is_demo_source(job.source):
            results.append(
                {
                    "id": None,
                    "title": job.title,
                    "company": job.company,
                    "salary": job.salary_range,
                    "location": job.location,
                    "experience": job.experience,
                    "education": job.education,
                    "skill_tags": job.skill_tags,
                    "industry": job.industry,
                    "jd_summary": job.jd_summary or (job.raw_text[:200] if job.raw_text else ""),
                    "raw_text": job.raw_text,
                    "source": job.source,
                    "source_url": job.source_url,
                    "external_id": job.external_id,
                    "_local_db": False,
                }
            )
            continue

        jd_id = None
        persisted = False
        if save and job.company and job.title:
            duplicate = (
                db.query(JobDescription)
                .filter(
                    JobDescription.user_id == current_user.id,
                    JobDescription.title == job.title,
                    JobDescription.company == job.company,
                    JobDescription.location == job.location,
                    JobDescription.source.in_(["boss", "zhaopin", "lagou", "crawled", "imported", "api", "manual"]),
                )
                .first()
            )
            if duplicate:
                jd_id = duplicate.id
                persisted = True
            else:
                jd = JobDescription(
                    user_id=current_user.id,
                    title=job.title,
                    company=job.company,
                    location=job.location,
                    salary_range=job.salary_range,
                    raw_text=job.raw_text or job.jd_summary or f"{job.title} - {job.company}",
                    source=job.source or "crawled",
                    industry=job.industry,
                    external_url=job.source_url,
                    external_id=job.external_id,
                    skill_tags=job.skill_tags,
                    education_requirement=job.education,
                    experience_requirement=job.experience,
                )
                db.add(jd)
                db.flush()
                jd_id = jd.id
                persisted = True
                saved_count += 1

        results.append(
            {
                "id": jd_id,
                "title": job.title,
                "company": job.company,
                "salary": job.salary_range,
                "location": job.location,
                "experience": job.experience,
                "education": job.education,
                "skill_tags": job.skill_tags,
                "industry": job.industry,
                "jd_summary": job.jd_summary or (job.raw_text[:200] if job.raw_text else ""),
                "raw_text": job.raw_text,
                "source": job.source,
                "source_url": job.source_url,
                "external_id": job.external_id,
                "_local_db": persisted,
            }
        )

    return results, saved_count


def _dedupe_jobs(items: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for item in items:
        key = (
            str(item.get("title") or "").strip().lower(),
            str(item.get("company") or "").strip().lower(),
            str(item.get("location") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


@router.post("/search-external", summary="搜索外部招聘岗位")
async def search_external_jobs(
    keyword: str = Query(..., min_length=1, description="搜索关键词"),
    city: str = Query("", description="城市"),
    source: str = Query("boss", description="来源: boss/all"),
    page: int = Query(1, ge=1, le=10),
    save: bool = Query(True, description="是否保存到本地"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        external_jobs, external_error = spider.search(keyword, city, source, page)
    except Exception as exc:
        traceback.print_exc()
        external_jobs, external_error = [], f"外部抓取异常: {str(exc)[:80]}"

    has_real_external = any(not _is_demo_source(job.source) for job in external_jobs)
    external_results, saved_count = (
        _save_external_jobs(db, external_jobs, current_user, save) if external_jobs else ([], 0)
    )

    local_results: list[dict] = []
    result_mode = "external"
    info_message = external_error or ""
    is_demo = False

    if not has_real_external:
        local_results = _search_local_jobs(db, keyword, city, current_user)
        if local_results:
            result_mode = "local_fallback"
            info_message = external_error or "外部抓取受限，已切换为本地职位库结果"
        else:
            demo_jobs = [job for job in external_jobs if _is_demo_source(job.source)]
            if not demo_jobs:
                demo_jobs, _ = spider.demo(keyword, city)
            external_results, _ = _save_external_jobs(db, demo_jobs, current_user, save=False)
            result_mode = "demo_fallback"
            info_message = "当前未获取到真实岗位，已展示演示数据"
            is_demo = True

    if save and saved_count > 0:
        db.commit()

    results = _dedupe_jobs(external_results + local_results)[:10]
    if not results and external_results:
        results = external_results[:10]

    return ok(
        data={
            "total": len(results),
            "page": page,
            "keyword": keyword,
            "city": city,
            "source": source,
            "saved_count": saved_count,
            "jobs": results,
            "is_demo": is_demo,
            "result_mode": result_mode,
            "error": None if is_demo else (info_message or None),
        },
        message=info_message or f"搜索到 {len(results)} 个岗位",
    )


@router.post("/fetch-detail", summary="抓取岗位详情")
async def fetch_job_detail(
    source: str = Query(..., description="来源: boss"),
    url: str = Query(..., description="岗位 URL"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        job = spider.fetch_detail(source, url)
        if not job or not job.raw_text:
            return fail(message="抓取详情失败", code=ERR_COMMON)

        existing = (
            db.query(JobDescription)
            .filter(
                JobDescription.user_id == current_user.id,
                JobDescription.external_url == url,
            )
            .first()
        )
        if existing:
            existing.raw_text = job.raw_text
            existing.parsed_json = {"jd_summary": job.raw_text[:300]}
            existing.skill_tags = job.skill_tags or existing.skill_tags
            existing.source = job.source or existing.source
            db.add(existing)
        else:
            existing = JobDescription(
                user_id=current_user.id,
                title=job.title or "未知岗位",
                company=job.company or "",
                location=job.location or "",
                salary_range=job.salary_range or "",
                raw_text=job.raw_text,
                source=job.source or source,
                external_url=url,
                external_id=job.external_id or "",
                skill_tags=job.skill_tags or [],
                industry=job.industry or "",
                education_requirement=job.education or "",
                experience_requirement=job.experience or "",
            )
            db.add(existing)
        db.commit()
        db.refresh(existing)

        return ok(
            data={
                "id": existing.id,
                "raw_text": existing.raw_text[:500],
                "source": existing.source,
            },
            message="详情抓取成功",
        )
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"抓取失败: {str(exc)[:80]}", code=ERR_COMMON)


@router.get("/cities", summary="支持的城市列表")
async def get_cities():
    return ok(data={"cities": SUPPORTED_CITIES})


@router.post("/seed-demo", summary="一键导入演示岗位数据")
async def seed_demo_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inserted = 0
    skipped = 0

    for item in SEED_JDS:
        existing = (
            db.query(JobDescription)
            .filter(
                JobDescription.user_id == current_user.id,
                JobDescription.title == item["title"],
                JobDescription.company == item["company"],
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        db.add(
            JobDescription(
                user_id=current_user.id,
                source="imported",
                is_active=1,
                title=item["title"],
                company=item["company"],
                location=item["location"],
                salary_range=item["salary_range"],
                raw_text=item["raw_text"],
                education_requirement=item["education"],
                experience_requirement=item["experience"],
                industry=item["industry"],
                skill_tags=item["skill_tags"],
                parsed_json={
                    "experience_requirement": item["experience"],
                    "education_requirement": item["education"],
                    "industry": item["industry"],
                    "required_skills": item["skill_tags"],
                    "jd_summary": item["raw_text"][:200],
                },
            )
        )
        inserted += 1

    db.commit()
    return ok(
        data={"inserted": inserted, "skipped": skipped, "total": len(SEED_JDS)},
        message=f"已导入 {inserted} 条演示岗位（跳过 {skipped} 条已存在记录）",
    )
