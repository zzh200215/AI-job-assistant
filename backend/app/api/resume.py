"""Resume APIs."""

from __future__ import annotations

import os
import traceback
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import JobDescription, Resume, ResumeVersion
from app.models.project_report_job import STAGE_REPORT, ProjectReportJob
from app.models.report_job import ResumeReportJob
from app.models.rewrite_job import RewriteSuggestionJob
from app.models.user import User
from app.schemas.resume import ResumeParseResp, ResumeUploadResp
from app.services import resume_export_service, resume_service
from app.services.project_report_html import render_project_report_html
from app.services.project_report_job_service import (
    assemble_document as _assemble_project_document,
)
from app.services.project_report_job_service import (
    create_project_report_job as _create_project_report_job,
)
from app.services.project_report_job_service import (
    create_questions_job as _create_questions_job,
)
from app.services.project_report_job_service import (
    serialize_job as _serialize_project_job,
)
from app.services.project_report_job_service import (
    submit_project_report_job as _submit_project_report_job,
)
from app.services.project_report_job_service import (
    touch_job_for_read as _touch_project_job_for_read,
)
from app.services.project_report_schema import (
    EXCLUDED_NO_QUESTIONS_MESSAGE,
)
from app.services.project_report_schema import (
    report_from_dict as project_report_from_dict,
)
from app.services.project_report_service import project_entries as _project_entries
from app.services.report_job_service import (
    create_report_job as _create_report_job,
)
from app.services.report_job_service import (
    report_from_dict,
)
from app.services.report_job_service import (
    serialize_job as _serialize_report_job,
)
from app.services.report_job_service import (
    submit_report_job as _submit_report_job,
)
from app.services.report_job_service import (
    touch_job_for_read as _touch_report_job_for_read,
)
from app.services.resume_analysis_service import analyze_resume, quick_score_resume
from app.services.resume_report_html import render_report_html
from app.services.resume_rewrite_service import apply_rewrite_suggestions, revert_rewrite_suggestions
from app.services.resume_tailor_service import tailor_resume_for_jd
from app.services.resume_workspace_service import build_ats_snapshot, build_markdown_diff
from app.services.rewrite_job_service import (
    create_rewrite_job,
    serialize_job,
    submit_rewrite_job,
    touch_job_for_read,
)
from app.services.subscription_service import check_quota
from app.utils.file_access import resolve_upload_path
from app.utils.job_access import get_accessible_job
from app.utils.response import ERR_AI, ERR_COMMON, ERR_FILE, ERR_PARAM, ERR_QUOTA, fail, ok
from app.utils.time_helper import utc_now

router = APIRouter()

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "png", "jpg", "jpeg"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "image/png",
    "image/jpeg",
    "application/octet-stream",
}
MAX_FILE_SIZE = 10 * 1024 * 1024

MIME_FALLBACK = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


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


def _validate_export_request(resume: Resume | None, fmt: str, version: str):
    if fmt not in ("pdf", "docx"):
        return fail(message="不支持的导出格式，仅支持 pdf / docx", code=ERR_PARAM)
    if version not in ("original", "optimized", "tailored", "manual"):
        return fail(message="不支持的版本类型", code=ERR_PARAM)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)
    if version == "optimized" and not resume.optimized_content:
        return fail(message="暂无优化版简历，请先生成", code=ERR_PARAM)
    return None


def _get_resume_version(db: Session, resume_id: int, version_id: int) -> ResumeVersion | None:
    return (
        db.query(ResumeVersion)
        .filter(
            ResumeVersion.id == version_id,
            ResumeVersion.resume_id == resume_id,
            ResumeVersion.format == "md",
        )
        .first()
    )


# 报告里那个"模型自报的总分"只作对照，绝不上候选人的屏（七维之和才是出分口径）。
# 任何把 `analyze_resume` 的结果原样返回的路由都必须先过这一道。
_INTERNAL_ANALYSIS_KEYS = ("model_reported_total",)


def _to_candidate_view(analysis: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in analysis.items() if key not in _INTERNAL_ANALYSIS_KEYS}


@router.post("/upload", summary="Upload resume")
def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file or not file.filename:
        return fail(message="上传文件为空", code=ERR_FILE)

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        return fail(
            message=f"不支持的文件格式 .{ext}，仅支持 PDF / DOCX / 图片简历（PNG/JPG/JPEG）",
            code=ERR_FILE,
        )

    mime = (file.content_type or "").lower()
    if mime and mime not in ALLOWED_MIME_TYPES:
        expected = MIME_FALLBACK.get(ext)
        if mime != expected:
            return fail(
                message=f"Invalid content type: {mime}. Please upload a PDF or DOCX file.",
                code=ERR_FILE,
            )

    # D219：这条路由在事件循环线程上做了三件同步事——读整份上传文件（上限 10MB）、把文件写到磁盘、
    # 再加一次数据库往返。改成 `def` 之后全部落在 anyio 线程里；文件读要跟着换成同步形态，
    # 这里没有别的 await 需要协程陪着了。
    raw = file.file.read()
    if len(raw) > MAX_FILE_SIZE:
        return fail(
            message=f"File is too large: {len(raw) / 1024 / 1024:.1f}MB (max 10MB).",
            code=ERR_FILE,
        )

    # 权益校验：简历数量上限
    allowed, msg, _ = check_quota(db, current_user.id, "resume_count", consume=False)
    if not allowed:
        return fail(message=msg, code=ERR_QUOTA)

    try:
        meta = resume_service.save_upload_file(raw, file.filename)
        obj = Resume(
            user_id=current_user.id,
            file_name=meta["file_name"],
            file_path=meta["file_path"],
            file_type=meta["file_type"],
            file_size=meta["file_size"],
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    except Exception as exc:
        db.rollback()
        return fail(message=f"文件保存失败: {exc}", code=ERR_FILE)

    data = ResumeUploadResp(
        id=obj.id,
        file_name=obj.file_name,
        file_path=obj.file_path,
        file_type=obj.file_type or "",
        file_size=obj.file_size or 0,
    ).model_dump()
    return ok(data, message="上传成功")


@router.post("/parse", summary="Parse resume")
def parse_resume(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume_id = payload.get("resume_id")
    if not resume_id:
        return fail(message="resume_id 必填", code=ERR_PARAM)

    resume = _get_owned_resume(db, int(resume_id), current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    try:
        obj = resume_service.parse_and_save(db, int(resume_id))
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"AI 解析失败: {exc}", code=ERR_AI)

    data = ResumeParseResp(
        id=obj.id,
        raw_text=obj.raw_text or "",
        parsed=obj.parsed_json or {},
        name=obj.name,
        phone=obj.phone,
        email=obj.email,
        years_exp=obj.years_exp,
        create_time=obj.create_time,
    ).model_dump()
    return ok(data, message="解析成功")


@router.get("/list", summary="List resumes")
def list_resume(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Resume).filter(
        Resume.is_deleted == 0,
        Resume.user_id == current_user.id,
    )
    query = query.order_by(Resume.create_time.desc())
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
                    "file_name": item.file_name,
                    "file_type": item.file_type,
                    "file_size": item.file_size,
                    "name": item.name,
                    "phone": item.phone,
                    "email": item.email,
                    "years_exp": item.years_exp,
                    "parsed": item.parsed_json or {},
                    "create_time": item.create_time.isoformat() if item.create_time else None,
                }
                for item in items
            ],
        }
    )


# ---------- 企业筛选用：获取所有可见简历 ----------
# 注：此路由必须在 /{resume_id} 之前注册，否则 "accessible-list" 会被动态路由捕获


@router.get("/accessible-list", summary="获取所有可筛选的简历（企业端使用）")
def accessible_resume_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回当前用户自己可安全用于筛选的简历列表。"""
    query = db.query(Resume).filter(
        Resume.is_deleted == 0,
        Resume.user_id == current_user.id,
    )

    query = query.order_by(Resume.create_time.desc())
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
                    "file_name": item.file_name,
                    "file_type": item.file_type,
                    "file_size": item.file_size,
                    "name": item.name,
                    "phone": item.phone,
                    "email": item.email,
                    "years_exp": item.years_exp,
                    "parsed": item.parsed_json or {},
                    "create_time": item.create_time.isoformat() if item.create_time else None,
                }
                for item in items
            ],
        }
    )


# ---------- 演示用：一键生成候选人简历 ----------

SEED_CANDIDATES = [
    {
        "name": "张明",
        "phone": "13800138001",
        "email": "zhangming@example.com",
        "years_exp": 3,
        "parsed_json": {
            "name": "张明",
            "phone": "13800138001",
            "email": "zhangming@example.com",
            "years_exp": 3,
            "education": "本科",
            "major": "计算机科学与技术",
            "school": "华中科技大学",
            "current_title": "Java后端开发工程师",
            "skills": ["Java", "Spring Boot", "MySQL", "Redis", "RabbitMQ", "MyBatis", "Docker"],
            "work_experience": [
                {
                    "company": "某互联网公司",
                    "title": "Java后端开发",
                    "desc": "负责订单系统的设计与开发，使用Spring Cloud微服务架构处理日均百万级请求。",
                },
                {
                    "company": "某科技公司",
                    "title": "Java开发实习生",
                    "desc": "参与内部管理系统的后端开发，独立完成权限管理模块。",
                },
            ],
            "project_experience": [
                {
                    "name": "电商订单系统",
                    "desc": "基于Spring Cloud实现订单创建、支付回调、库存扣减等核心流程。",
                    "tech": ["Spring Cloud", "MySQL", "Redis"],
                }
            ],
        },
    },
    {
        "name": "李婷",
        "phone": "13900139002",
        "email": "liting@example.com",
        "years_exp": 2,
        "parsed_json": {
            "name": "李婷",
            "phone": "13900139002",
            "email": "liting@example.com",
            "years_exp": 2,
            "education": "硕士",
            "major": "软件工程",
            "school": "武汉大学",
            "current_title": "前端开发工程师",
            "skills": ["Vue.js", "React", "TypeScript", "JavaScript", "CSS", "Element Plus", "Webpack", "Node.js"],
            "work_experience": [
                {
                    "company": "某科技公司",
                    "title": "前端开发",
                    "desc": "负责管理后台前端架构设计与开发，基于Vue3 + Element Plus实现20+业务页面。",
                }
            ],
            "project_experience": [
                {
                    "name": "智能数据分析平台",
                    "desc": "基于React + TypeScript开发数据可视化看板，集成ECharts实现多维度图表展示。",
                    "tech": ["React", "TypeScript", "ECharts"],
                }
            ],
        },
    },
    {
        "name": "王强",
        "phone": "13700137003",
        "email": "wangqiang@example.com",
        "years_exp": 5,
        "parsed_json": {
            "name": "王强",
            "phone": "13700137003",
            "email": "wangqiang@example.com",
            "years_exp": 5,
            "education": "本科",
            "major": "计算机科学",
            "school": "西安电子科技大学",
            "current_title": "全栈开发工程师",
            "skills": ["Python", "FastAPI", "Django", "Vue.js", "PostgreSQL", "Redis", "Docker", "Linux", "Nginx"],
            "work_experience": [
                {
                    "company": "某大数据公司",
                    "title": "全栈开发",
                    "desc": "负责数据采集平台的架构设计与开发，使用FastAPI + Vue3实现完整前后端分离。",
                },
                {
                    "company": "某软件公司",
                    "title": "后端开发",
                    "desc": "使用Django开发SaaS平台API，负责用户认证、权限管理模块。",
                },
            ],
            "project_experience": [
                {
                    "name": "实时数据采集平台",
                    "desc": "基于FastAPI + WebSocket实现数据实时采集与推送，日处理百万级数据点。",
                    "tech": ["FastAPI", "WebSocket", "PostgreSQL"],
                }
            ],
        },
    },
    {
        "name": "陈雪",
        "phone": "13600136004",
        "email": "chenxue@example.com",
        "years_exp": 1,
        "parsed_json": {
            "name": "陈雪",
            "phone": "13600136004",
            "email": "chenxue@example.com",
            "years_exp": 1,
            "education": "本科",
            "major": "信息管理与信息系统",
            "school": "南京大学",
            "current_title": "数据分析师",
            "skills": ["Python", "SQL", "Excel", "Tableau", "Pandas", "NumPy", "统计学"],
            "work_experience": [
                {
                    "company": "某咨询公司",
                    "title": "数据分析助理",
                    "desc": "负责客户业务数据的清洗、分析和可视化，使用Python完成自动化报表。",
                }
            ],
            "project_experience": [
                {
                    "name": "用户增长分析项目",
                    "desc": "基于Pandas和Tableau分析用户留存与转化数据，输出增长策略建议。",
                    "tech": ["Pandas", "Tableau"],
                }
            ],
        },
    },
    {
        "name": "赵磊",
        "phone": "13500135005",
        "email": "zhaolei@example.com",
        "years_exp": 4,
        "parsed_json": {
            "name": "赵磊",
            "phone": "13500135005",
            "email": "zhaolei@example.com",
            "years_exp": 4,
            "education": "硕士",
            "major": "计算机科学与技术",
            "school": "浙江大学",
            "current_title": "算法工程师",
            "skills": ["Python", "PyTorch", "TensorFlow", "NLP", "LLM", "C++", "Linux", "分布式训练"],
            "work_experience": [
                {
                    "company": "某AI公司",
                    "title": "算法工程师",
                    "desc": "负责NLP模型训练与部署，参与基于LLM的智能客服系统开发。",
                },
                {"company": "某科技公司", "title": "算法实习生", "desc": "参与文本分类和实体识别模型的研发与优化。"},
            ],
            "project_experience": [
                {
                    "name": "智能客服意图识别系统",
                    "desc": "基于BERT微调实现多分类意图识别，准确率达96%，上线QPS 200+。",
                    "tech": ["PyTorch", "BERT", "FastAPI"],
                }
            ],
        },
    },
    {
        "name": "刘洋",
        "phone": "13400134006",
        "email": "liuyang@example.com",
        "years_exp": 6,
        "parsed_json": {
            "name": "刘洋",
            "phone": "13400134006",
            "email": "liuyang@example.com",
            "years_exp": 6,
            "education": "本科",
            "major": "软件工程",
            "school": "电子科技大学",
            "current_title": "DevOps工程师",
            "skills": ["Docker", "Kubernetes", "Jenkins", "GitLab CI", "Ansible", "Terraform", "Linux", "Shell"],
            "work_experience": [
                {
                    "company": "某云计算公司",
                    "title": "DevOps工程师",
                    "desc": "负责K8s集群管理与CI/CD流水线建设，管理200+微服务的自动化部署。",
                },
                {
                    "company": "某互联网公司",
                    "title": "运维开发",
                    "desc": "基于Ansible和Shell实现服务器自动化配置与监控。",
                },
            ],
            "project_experience": [
                {
                    "name": "微服务CI/CD平台",
                    "desc": "基于GitLab CI + ArgoCD构建自动化部署流水线，支撑每日50+次发布。",
                    "tech": ["Kubernetes", "GitLab CI", "ArgoCD"],
                }
            ],
        },
    },
]


@router.post("/seed-demo", summary="一键生成演示候选人简历")
def seed_demo_resumes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """为当前用户生成 6 份演示简历，用于企业筛选功能体验。"""
    inserted = 0
    skipped = 0

    for cand in SEED_CANDIDATES:
        existing = (
            db.query(Resume)
            .filter(
                Resume.user_id == current_user.id,
                Resume.name == cand["name"],
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        import json

        obj = Resume(
            user_id=current_user.id,
            file_name=f"{cand['name']}_简历.pdf",
            file_path="",
            file_type="pdf",
            file_size=0,
            name=cand["name"],
            phone=cand["phone"],
            email=cand["email"],
            years_exp=cand["years_exp"],
            parsed_json=cand["parsed_json"],
            raw_text=json.dumps(cand["parsed_json"], ensure_ascii=False),
        )
        db.add(obj)
        inserted += 1

    db.commit()
    return ok(
        data={"inserted": inserted, "skipped": skipped, "total": len(SEED_CANDIDATES)},
        message=f"已生成 {inserted} 份演示简历（跳过 {skipped} 条已存在记录）",
    )


# ========== 以下为动态路由 /{resume_id} 及其子路由 ==========


@router.get("/{resume_id}", summary="Get resume detail")
def get_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    return ok(
        {
            "id": resume.id,
            "file_name": resume.file_name,
            "file_type": resume.file_type,
            "file_size": resume.file_size,
            "raw_text": resume.raw_text,
            "parsed": resume.parsed_json or {},
            "name": resume.name,
            "phone": resume.phone,
            "email": resume.email,
            "years_exp": resume.years_exp,
            "create_time": resume.create_time.isoformat() if resume.create_time else None,
        }
    )


@router.delete("/{resume_id}", summary="Soft delete resume")
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    resume.is_deleted = 1
    resume.deleted_at = utc_now()
    db.add(resume)
    db.commit()
    return ok(message="删除成功")


@router.post("/{resume_id}/generate-optimized", summary="Generate optimized resume")
def generate_optimized_resume(
    resume_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    jd_id = (payload or {}).get("target_jd_id")

    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    if jd_id:
        jd = get_accessible_job(db, jd_id, current_user)
        if not jd:
            return fail(message="目标岗位不存在或无权限", code=ERR_PARAM)

    try:
        result = resume_export_service.generate_optimized(db, resume_id, jd_id, user_id=current_user.id)
        return ok(data=result, message="优化版简历生成成功")
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"生成失败: {exc}", code=ERR_COMMON)


@router.get("/{resume_id}/versions", summary="Get resume versions")
def get_resume_versions(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    versions = (
        db.query(ResumeVersion)
        .filter(ResumeVersion.resume_id == resume_id)
        .order_by(ResumeVersion.created_at.desc())
        .all()
    )
    original_md = (
        resume_export_service._build_original_md(resume) if hasattr(resume_export_service, "_build_original_md") else ""
    )

    return ok(
        data={
            "original": {
                "content": original_md,
                "created_at": resume.create_time.isoformat() if resume.create_time else None,
            },
            "versions": [version.to_dict() for version in versions],
        }
    )


@router.post("/{resume_id}/versions", summary="Create editable resume version")
def create_resume_version(
    resume_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    content = str((payload or {}).get("content") or "").strip()
    if not content:
        return fail(message="版本内容不能为空", code=ERR_PARAM)
    version_type = str((payload or {}).get("version_type") or "manual")
    if version_type not in {"manual", "optimized", "tailored"}:
        return fail(message="不支持的版本类型", code=ERR_PARAM)

    target_jd_id = (payload or {}).get("target_jd_id")
    if target_jd_id:
        jd = get_accessible_job(db, int(target_jd_id), current_user)
        if not jd:
            return fail(message="目标岗位不存在或无权限", code=ERR_PARAM)
    parent_version_id = (payload or {}).get("parent_version_id")
    if parent_version_id and not _get_resume_version(db, resume_id, int(parent_version_id)):
        return fail(message="来源版本不存在或无权限", code=ERR_PARAM)

    version = ResumeVersion(
        resume_id=resume_id,
        version_type=version_type,
        content=content,
        format="md",
        label=str((payload or {}).get("label") or "").strip()[:120] or "手动编辑版",
        target_jd_id=int(target_jd_id) if target_jd_id else None,
        parent_version_id=int(parent_version_id) if parent_version_id else None,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return ok(data=version.to_dict(), message="版本已保存")


@router.get("/{resume_id}/versions/diff", summary="Compare editable resume versions")
def compare_resume_versions(
    resume_id: int,
    compare_version_id: int = Query(...),
    base_version_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)
    compare_version = _get_resume_version(db, resume_id, compare_version_id)
    if not compare_version:
        return fail(message="对比版本不存在或无权限", code=ERR_PARAM)

    if base_version_id:
        base_version = _get_resume_version(db, resume_id, base_version_id)
        if not base_version:
            return fail(message="基准版本不存在或无权限", code=ERR_PARAM)
        base_content = base_version.content
        base = base_version.to_dict()
    else:
        base_content = resume_export_service._build_original_md(resume)
        base = {"id": None, "label": "原始简历", "version_type": "original"}

    return ok(
        data={
            "base": base,
            "compare": compare_version.to_dict(),
            **build_markdown_diff(base_content, compare_version.content),
        }
    )


@router.patch("/{resume_id}/versions/{version_id}", summary="Update editable resume version")
def update_resume_version(
    resume_id: int,
    version_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _get_owned_resume(db, resume_id, current_user.id):
        return fail(message="简历不存在或无权限", code=ERR_PARAM)
    version = _get_resume_version(db, resume_id, version_id)
    if not version:
        return fail(message="版本不存在或无权限", code=ERR_PARAM)

    if "content" in (payload or {}):
        content = str(payload.get("content") or "").strip()
        if not content:
            return fail(message="版本内容不能为空", code=ERR_PARAM)
        version.content = content
        version.ats_snapshot = None
    if "label" in (payload or {}):
        version.label = str(payload.get("label") or "").strip()[:120] or version.label
    if "target_jd_id" in (payload or {}):
        target_jd_id = payload.get("target_jd_id")
        if target_jd_id:
            jd = get_accessible_job(db, int(target_jd_id), current_user)
            if not jd:
                return fail(message="目标岗位不存在或无权限", code=ERR_PARAM)
            version.target_jd_id = int(target_jd_id)
        else:
            version.target_jd_id = None
        version.ats_snapshot = None
    db.add(version)
    db.commit()
    db.refresh(version)
    return ok(data=version.to_dict(), message="版本已更新")


@router.post("/{resume_id}/versions/{version_id}/suggestions", summary="Persist resume suggestion decision")
def save_suggestion_decision(
    resume_id: int,
    version_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _get_owned_resume(db, resume_id, current_user.id):
        return fail(message="简历不存在或无权限", code=ERR_PARAM)
    version = _get_resume_version(db, resume_id, version_id)
    if not version:
        return fail(message="版本不存在或无权限", code=ERR_PARAM)

    suggestion_id = str((payload or {}).get("suggestion_id") or "").strip()
    decision = str((payload or {}).get("decision") or "").strip()
    if not suggestion_id or decision not in {"accepted", "ignored", "pending"}:
        return fail(message="建议状态参数无效", code=ERR_PARAM)
    decisions = dict(version.suggestion_decisions or {})
    decisions[suggestion_id] = decision
    version.suggestion_decisions = decisions
    db.add(version)
    db.commit()
    db.refresh(version)
    return ok(data=version.to_dict(), message="建议状态已保存")


@router.post("/{resume_id}/ats-preview", summary="Preview ATS quality for current resume content")
def preview_resume_ats(
    resume_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)
    version_id = (payload or {}).get("version_id")
    version = _get_resume_version(db, resume_id, int(version_id)) if version_id else None
    if version_id and not version:
        return fail(message="版本不存在或无权限", code=ERR_PARAM)
    jd_id = (payload or {}).get("jd_id") or (version.target_jd_id if version else None)
    jd = None
    if jd_id:
        jd = get_accessible_job(db, int(jd_id), current_user)
        if not jd:
            return fail(message="目标岗位不存在或无权限", code=ERR_PARAM)

    content = version.content if version else resume_export_service._build_original_md(resume)
    snapshot = build_ats_snapshot(content, jd)
    snapshot["version_id"] = version.id if version else None
    snapshot["jd_id"] = jd.id if jd else None
    if version:
        version.ats_snapshot = snapshot
        db.add(version)
        db.commit()
    return ok(data=snapshot)


@router.post("/{resume_id}/export", summary="Prepare resume export")
def export_resume(
    resume_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fmt = (payload or {}).get("format", "docx")
    version = (payload or {}).get("version", "optimized")
    template = (payload or {}).get("template", "classic")
    version_id = (payload or {}).get("version_id")

    resume = _get_owned_resume(db, resume_id, current_user.id)
    error = _validate_export_request(resume, fmt, version)
    if error:
        return error
    if version_id and not _get_resume_version(db, resume_id, int(version_id)):
        return fail(message="导出版本不存在或无权限", code=ERR_PARAM)

    # 构建下载URL参数
    params = f"format={fmt}&version={version}&template={template}"
    if version_id:
        params += f"&version_id={version_id}"

    return ok(
        data={
            "download_url": f"/api/resume/{resume_id}/download?{params}",
            "format": fmt,
            "version": version,
            "template": template,
            "available_templates": resume_export_service.AVAILABLE_TEMPLATES,
        },
        message=f"{fmt.upper()} 导出成功",
    )


@router.get("/{resume_id}/download", summary="Download exported resume")
def download_resume_export(
    resume_id: int,
    format: str = Query("docx"),
    version: str = Query("optimized"),
    template: str = Query("classic"),
    version_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # D219：E15 只把渲染（DOCX/PDF，秒级）包进了线程池，取简历的那两次数据库查询
    # （`_get_owned_resume` / `_get_resume_version`）一直留在协程体里。整条改 `def` 之后
    # 渲染与查库在同一条线程上，占的线程数不变。
    resume = _get_owned_resume(db, resume_id, current_user.id)
    error = _validate_export_request(resume, format, version)
    if error:
        return error
    if version_id and not _get_resume_version(db, resume_id, int(version_id)):
        return fail(message="导出版本不存在或无权限", code=ERR_PARAM)

    try:
        if format == "docx":
            # 渲染文档是 CPU + 磁盘活（PDF 那支还要跑 WeasyPrint），秒级；整条路由已经是 `def`，
            # FastAPI 把它整个丢进 anyio 线程池，这里直接调就行（D219）。
            rel_path = resume_export_service.export_docx(
                resume_id,
                version,
                db,
                user_id=current_user.id,
                template=template,
                version_id=version_id,
            )
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            rel_path = resume_export_service.export_pdf(
                resume_id,
                version,
                db,
                user_id=current_user.id,
                template=template,
                version_id=version_id,
            )
            media_type = "application/pdf"

        abs_path = resolve_upload_path(rel_path)
        if not abs_path.exists() or not abs_path.is_file():
            return fail(message="导出文件不存在", code=ERR_FILE)

        base_name = os.path.splitext(resume.file_name or f"resume_{resume_id}")[0]
        filename = f"{base_name}_{version}.{format}"
        return FileResponse(path=abs_path, filename=filename, media_type=media_type)
    except RuntimeError as exc:
        return fail(message=str(exc), code=ERR_COMMON)
    except ValueError:
        return fail(message="导出路径无效", code=ERR_COMMON)
    except Exception as exc:
        return fail(message=f"导出失败: {exc}", code=ERR_COMMON)


@router.post("/{resume_id}/tailor", summary="针对目标JD自适应改写简历")
def tailor_resume(
    resume_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    根据目标JD，生成一份专门针对该岗位的定制版简历。
    - 保持事实真实性，不编造经历
    - 调整措辞、重点和结构，突出与JD的匹配度
    - 同时返回匹配分析和改写说明
    """
    jd_id = payload.get("jd_id")
    if not jd_id:
        return fail(message="jd_id 必填", code=ERR_PARAM)

    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    if not resume.parsed_json:
        return fail(message="简历尚未解析，请先解析简历", code=ERR_PARAM)

    jd = get_accessible_job(db, int(jd_id), current_user)
    if not jd:
        return fail(message="目标岗位不存在或无权限", code=ERR_PARAM)

    try:
        result = tailor_resume_for_jd(db, resume_id, int(jd_id), user_id=current_user.id)
        return ok(data=result, message="简历自适应改写完成")
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"改写失败: {exc}", code=ERR_AI)


# ============================================================
# 行级改写建议（锚定到具体文本块）
# ============================================================


@router.post("/{resume_id}/rewrite-suggestion-jobs", summary="提交一次行级改写建议作业（立刻返回，不等模型）")
def create_rewrite_suggestion_job(
    resume_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把"生成改写建议"改成后台作业。

    为什么不再是同步那一发：它是**一次**模型调用，实测 4.58–12.08s（关思考链，D196）到
    91.77s 且返回空 content（开思考链，D189）。同步写法下这一发会占住 anyio 20 根线程中的一根
    （`core/threadpool.py` 把上限钉成连接池的 10+10），候选人还要对着 spinner 等满。
    现在 POST 只做两件事：落一行作业、投进本进程的池子，然后返回 `job_id`。

    "建议不落库"这条对外承诺没有被推翻：这一张表存的是**没被采纳的候选文本**，`tb_resume.parsed_json`
    一个字都不写；采纳仍然只发生在 `apply-rewrites` 那一步。
    """
    jd_id = (payload or {}).get("jd_id")
    # 归属在**这里**判，不留给后台那一跑：作业内部也会判（`build_rewrite_suggestions` 带
    # user_id），但把别人的 resume_id 变成一行 failed 作业同样是写库、同样占一个作业槽位。
    # 用的是本文件那一条既有判据（`_get_owned_resume` / `get_accessible_job`），不另立一套——
    # 同一个事实两处各写一遍是这个仓库反复记过的分叉源。
    if _get_owned_resume(db, resume_id, current_user.id) is None:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)
    jd_id_int = int(jd_id) if jd_id else None
    if jd_id_int is not None and get_accessible_job(db, jd_id_int, current_user) is None:
        return fail(message="目标岗位不存在或无权限", code=ERR_PARAM)
    job = create_rewrite_job(
        db,
        user_id=current_user.id,
        resume_id=resume_id,
        jd_id=jd_id_int,
    )
    submit_rewrite_job(job.id)
    return ok({"job_id": job.id, "status": "pending"}, message="改写建议开始生成")


@router.get("/rewrite-suggestion-jobs/{job_id}", summary="查一次改写建议作业的结果")
def get_rewrite_suggestion_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """轮询这一条。载荷里没有 `error_msg`——那句可能带模型返回的内容，而这是对外端点。"""
    job = (
        db.query(RewriteSuggestionJob)
        .filter(RewriteSuggestionJob.id == job_id, RewriteSuggestionJob.user_id == current_user.id)
        .first()
    )
    if job is None:
        return fail(message="作业不存在或无权限", code=ERR_PARAM)
    # 读路径顺手做恢复：进程死在半路留下的 running/pending 在这里退回并补投，
    # 所以不需要再加一条调度任务（候选人一定会来读，轮询本身就是那条扫描）。
    payload = serialize_job(job)
    payload["status"] = touch_job_for_read(db, job)
    return ok(payload)


@router.post("/{resume_id}/apply-rewrites", summary="应用行级改写并重算匹配分")
def apply_rewrites(
    resume_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """edits: [{block_id, proposed_text, expected_original?}]

    expected_original 用于拒绝过期锚点：建议是按 position 锚定的，简历在生成建议
    之后又被改过时，直接应用会覆盖掉候选人后来写的文字。
    """
    edits = (payload or {}).get("edits")
    if not isinstance(edits, list) or not edits:
        return fail(message="edits 必须是非空数组", code=ERR_PARAM)
    jd_id = (payload or {}).get("jd_id")
    try:
        result = apply_rewrite_suggestions(
            db, resume_id, edits, jd_id=int(jd_id) if jd_id else None, user_id=current_user.id
        )
        message = f"已应用 {len(result['applied'])} 处改写" if result["changed"] else "没有改动被应用"
        return ok(result, message=message)
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"应用改写失败: {exc}", code=ERR_COMMON)


@router.post("/{resume_id}/revert-rewrite", summary="撤销一次行级改写")
def revert_rewrite(
    resume_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """payload: {snapshot_version_id} —— apply-rewrites 返回的那一行 id。

    快照在 B1.3 就在写，但一直没有人能把它读回来：`GET /{id}/versions` 会带上它，
    而界面上唯一列版本的 `ResumeCompare` 按 `format === 'md'` 过滤，json 快照被丢掉。
    撤销与 `expected_original` 共用一条判据——按 position 锚定，所以候选人应用之后
    又自己改过其中任何一块时，整单撤销被拒并回报那几处，而不是吃掉他们后写的文字。
    """
    version_id = (payload or {}).get("snapshot_version_id")
    if isinstance(version_id, bool) or version_id is None:
        return fail(message="snapshot_version_id 必填", code=ERR_PARAM)
    try:
        target = int(version_id)
    except (TypeError, ValueError):
        return fail(message="snapshot_version_id 必须是版本行 id", code=ERR_PARAM)
    try:
        result = revert_rewrite_suggestions(db, resume_id, target, user_id=current_user.id)
        if not result["changed"]:
            stale = "、".join(str(item["block_id"]) for item in result["stale_blocks"])
            return ok(result, message=f"简历里这几处已经又改过，没有撤销：{stale}")
        return ok(result, message=f"已撤销 {len(result['restored_blocks'])} 处改写")
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"撤销改写失败: {exc}", code=ERR_COMMON)


# ============================================================
# 简历深度分析
# ============================================================


@router.get("/{resume_id}/quick-score", summary="简历完整度检查（基于规则）")
def get_resume_quick_score(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    基于规则的完整度检查，不调用LLM。

    返回的是"有多少模块被填了"，不是简历质量或 ATS 兼容性评价；
    质量评价见 POST /resume/{id}/analyze。
    """
    try:
        result = quick_score_resume(db, resume_id, user_id=current_user.id)
        return ok(result)
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)


@router.post("/{resume_id}/analyze", summary="简历深度分析（AI）")
def analyze_resume_api(
    resume_id: int,
    payload: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    按七维口径深度分析简历：首屏结论段 + 七维评分概览 + 竞争分析。
    七个维度与满分见 `docs/resume-report-spec.md` §2；总分由七维之和算，不是模型自报的那一个。
    """
    target_position = ""
    if payload:
        target_position = payload.get("target_position", "")

    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    try:
        result = analyze_resume(db, resume_id, target_position=target_position, user_id=current_user.id)
        return ok(_to_candidate_view(result), message="简历深度分析完成")
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"分析失败: {exc}", code=ERR_AI)


@router.post("/{resume_id}/diagnose", summary="简历诊断（七维评分 + 竞争分析 + 完整度检查）")
def diagnose_resume(
    resume_id: int,
    payload: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    评估报告的模块一/二/三，加上规则侧完整度检查，供简历中心「AI诊断」弹窗取用。

    返回：
    - verdict / total_score / grade / grade_desc / grade_scale / dimensions / to_next_grade：
      首屏结论段与七维评分概览（dimensions 每行含 key/label/full/score/star/note）
    - missing_keywords：词表覆盖缺口（住在 role_fit 那一档，这里汇总）
    - competition：竞争分析（档位徽标、能打的牌、要补的短板、针对性建议、期望薪资口径）
    - completeness_score / completeness_grade / completeness_issues / module_check：
      规则算的"填了多少个模块"，与上面的七维不同尺，所以键名各自带 completeness 前缀
    """
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    target_position = ""
    if payload:
        target_position = payload.get("target_position", "")

    try:
        quick_result = quick_score_resume(db, resume_id, user_id=current_user.id)
        analysis = analyze_resume(
            db,
            resume_id,
            target_position=target_position,
            user_id=current_user.id,
        )

        # 这些句子来自规则侧完整度检查（"缺少工作经历"），说的是模块填没填，
        # 不是这份简历写得好不好，所以一律待在 completeness_* 名下。
        completeness_issues = quick_result.get("issues", []) if isinstance(quick_result.get("issues"), list) else []

        result = {
            **_to_candidate_view(analysis),
            "report_date": utc_now().strftime("%Y-%m-%d"),
            "completeness_issues": completeness_issues,
            "completeness_score": quick_result.get("completeness_score"),
            "completeness_grade": quick_result.get("completeness_grade"),
            "module_check": quick_result.get("module_check", {}),
        }
        return ok(result, message="简历诊断完成")
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"诊断失败: {exc}", code=ERR_AI)


# ------------------------------------------------------------------ 简历评估报告（六模块）
# 一次报告最多三发模型调用，所以它和改写作业同一族形状：投一行、立刻返回、前端轮询。
# 路由都挂在 `/report-jobs` 这一段，与 `/{resume_id}` 那种一段式路径不会互相抢匹配。


@router.post("/{resume_id}/report-jobs", summary="提交一次简历评估报告作业（立刻返回，不等模型）")
def create_report_job_api(
    resume_id: int,
    payload: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)
    if not (resume.parsed_json or resume.raw_text):
        return fail(message="简历内容为空，先生成报告前请先解析", code=ERR_PARAM)

    body = payload or {}
    jd_id = body.get("jd_id")
    target_position = str(body.get("target_position") or "")
    if jd_id is not None and db.get(JobDescription, int(jd_id)) is None:
        return fail(message="目标岗位不存在或无权限", code=ERR_PARAM)

    job = _create_report_job(
        db,
        user_id=current_user.id,
        resume_id=resume_id,
        jd_id=int(jd_id) if jd_id is not None else None,
        target_position=target_position,
    )
    _submit_report_job(job.id)
    return ok({"job_id": job.id, "status": job.status}, message="报告生成已开始")


@router.get("/report-jobs/{job_id}", summary="查一次报告作业的状态与结果")
def get_report_job_api(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.get(ResumeReportJob, job_id)
    if job is None or job.user_id != current_user.id:
        return fail(message="作业不存在或无权限", code=ERR_PARAM)
    _touch_report_job_for_read(db, job)
    return ok(_serialize_report_job(job), message="ok")


@router.post("/report-jobs/{job_id}/apply-redline", summary="采纳批改稿里的若干处改动（写回简历并重算匹配分）")
def apply_redline_api(
    job_id: int,
    payload: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """把选中的编号折成整块改写，走 `apply-rewrites` 那条既有写路径。

    句级记号只是另一种寻址方式，不是第二条写入路径：快照、撤销、`expected_original`
    防过期锚点、重算匹配分全都复用，避免"改简历"这件事出现两个权威。
    """
    job = db.get(ResumeReportJob, job_id)
    if job is None or job.user_id != current_user.id:
        return fail(message="作业不存在或无权限", code=ERR_PARAM)
    if job.status != "completed" or not job.report_json:
        return fail(message="这一份报告还没有可用结果", code=ERR_PARAM)

    marks = (payload or {}).get("marks")
    if not isinstance(marks, list) or not marks:
        return fail(message="marks 必须是非空编号列表", code=ERR_PARAM)

    report = report_from_dict(job.report_json)
    if report.redline is None:
        return fail(message="这一份报告里没有批改稿", code=ERR_PARAM)
    try:
        wanted = [int(mark) for mark in marks]
    except (TypeError, ValueError):
        return fail(message="marks 里只能放编号", code=ERR_PARAM)

    known_marks = {edit.mark for edit in report.redline.edits}
    unknown = [mark for mark in wanted if mark not in known_marks]
    if unknown:
        # 先判编号存不存在，再判可不可写回：候选人点了个不存在的号，
        # 那句"属于需要自己改的栏目"会把人引到错的方向上。
        return fail(message=f"编号不存在：{unknown}", code=ERR_PARAM)

    edits = report.redline.edits_for_apply(wanted)
    if not edits:
        return fail(
            message="这些编号都落在需要自己在简历文件里改的那几栏（基本信息、经历抬头、技术栈、教育背景）",
            code=ERR_PARAM,
        )

    try:
        result = apply_rewrite_suggestions(
            db,
            job.resume_id,
            edits,
            jd_id=job.jd_id,
            user_id=current_user.id,
        )
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    result["requested_marks"] = wanted
    return ok(result, message="批改已写回简历")


@router.get("/report-jobs/{job_id}/report.html", summary="下载自包含的简历评估报告 HTML")
def download_report_html(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """现渲一份自包含 HTML：文本→HTML 是纯函数，不存盘就没有会过期的一致性副本。"""
    job = db.get(ResumeReportJob, job_id)
    if job is None or job.user_id != current_user.id:
        return fail(message="作业不存在或无权限", code=ERR_PARAM)
    if job.status != "completed" or not job.report_json:
        return fail(message="这一份报告还没有可用结果", code=ERR_PARAM)

    try:
        document = render_report_html(report_from_dict(job.report_json))
    except RuntimeError as exc:
        traceback.print_exc()
        return fail(message=str(exc), code=ERR_AI)

    resume = _get_owned_resume(db, job.resume_id, current_user.id)
    name = report_from_dict(job.report_json).verdict.get("candidate_name") or (resume.name if resume else "") or "简历"
    quoted = quote(f"简历评估报告_{name}.html")
    return Response(
        content=document,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


# ------------------------------------------------------------------ 单项目分析（四大节）
# 一次作业跑前三节（两发模型调用），第四节是挂在同一份文档上的第二次调用：
# 他点的口径是"20 题按按钮再跑"，所以它是**另一行作业**，不是同一行的第二次状态。
# 路由挂在 `/project-report-jobs`，与上面 `/report-jobs` 那一族不互相抢匹配。


@router.post("/{resume_id}/project-report-jobs", summary="提交一次单项目分析（前三节，立刻返回不等模型）")
def create_project_report_job_api(
    resume_id: int,
    payload: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    body = payload or {}
    try:
        project_index = int(body.get("project_index"))
    except (TypeError, ValueError):
        return fail(message="project_index 要从 0 开始数的那一个项目", code=ERR_PARAM)

    entries = _project_entries(resume.parsed_json)
    if not entries:
        return fail(message="这份简历里没有项目经历，做不了单项目分析", code=ERR_PARAM)
    if not (0 <= project_index < len(entries)):
        return fail(message=f"没有第 {project_index + 1} 个项目（这份简历里共 {len(entries)} 个）", code=ERR_PARAM)

    jd_id = body.get("jd_id")
    target_position = str(body.get("target_position") or "")
    if jd_id is not None and db.get(JobDescription, int(jd_id)) is None:
        return fail(message="目标岗位不存在或无权限", code=ERR_PARAM)

    name = str(entries[project_index].get("name") or "").strip()
    job = _create_project_report_job(
        db,
        user_id=current_user.id,
        resume_id=resume_id,
        project_index=project_index,
        project_name=name,
        jd_id=int(jd_id) if jd_id is not None else None,
        target_position=target_position,
    )
    _submit_project_report_job(job.id)
    return ok({"job_id": job.id, "status": job.status, "project_index": project_index}, message="项目分析已开始")


@router.get("/project-report-jobs/{job_id}", summary="查一次单项目分析作业的状态与结果")
def get_project_report_job_api(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.get(ProjectReportJob, job_id)
    if job is None or job.user_id != current_user.id:
        return fail(message="作业不存在或无权限", code=ERR_PARAM)
    status = _touch_project_job_for_read(db, job)
    document = _assemble_project_document(db, job) if status == "completed" else None
    return ok(_serialize_project_job(job, document=document), message="ok")


@router.post("/project-report-jobs/{job_id}/questions", summary="给这一份项目分析续跑第四节（20 题）")
def create_project_questions_job_api(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.get(ProjectReportJob, job_id)
    if job is None or job.user_id != current_user.id:
        return fail(message="作业不存在或无权限", code=ERR_PARAM)
    if job.stage != STAGE_REPORT:
        return fail(message="只有前三节那一份作业能续跑第四节", code=ERR_PARAM)
    if job.status != "completed" or not job.report_json:
        return fail(message="这一份项目分析还没有可用结果", code=ERR_PARAM)
    if job.excluded:
        # 命中一票否决的那一份按口径不出题，这一句是对人的说明，不是机制报错。
        return fail(message=EXCLUDED_NO_QUESTIONS_MESSAGE, code=ERR_COMMON)

    child = _create_questions_job(db, parent=job)
    _submit_project_report_job(child.id)
    return ok({"job_id": child.id, "status": child.status, "parent_job_id": job.id}, message="面试准备开始生成")


@router.get("/project-report-jobs/{job_id}/report.html", summary="下载自包含的单项目分析 HTML")
def download_project_report_html(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """现渲一份自包含 HTML：文本→HTML 是纯函数，不存盘就没有会过期的一致性副本。"""
    job = db.get(ProjectReportJob, job_id)
    if job is None or job.user_id != current_user.id:
        return fail(message="作业不存在或无权限", code=ERR_PARAM)
    if job.status != "completed":
        return fail(message="这一份项目分析还没有可用结果", code=ERR_PARAM)

    document = _assemble_project_document(db, job)
    if not document:
        return fail(message="这一份项目分析还没有可用结果", code=ERR_PARAM)
    try:
        rendered = render_project_report_html(project_report_from_dict(document))
    except RuntimeError as exc:
        traceback.print_exc()
        return fail(message=str(exc), code=ERR_AI)

    name = document.get("excerpt", {}).get("name") or f"项目{int(job.project_index) + 1}"
    quoted = quote(f"项目分析_{name}.html")
    return Response(
        content=rendered,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
