# -*- coding: utf-8 -*-
"""Resume APIs."""
from __future__ import annotations

import os
import traceback

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import JobDescription, Resume, ResumeVersion
from app.models.user import User
from app.schemas.resume import ResumeParseResp, ResumeUploadResp
from app.services import resume_export_service, resume_service
from app.utils.file_access import resolve_upload_path
from app.utils.job_access import get_accessible_job
from app.utils.response import ERR_AI, ERR_COMMON, ERR_FILE, ERR_PARAM, fail, ok
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
    if version not in ("original", "optimized"):
        return fail(message="不支持的版本类型，仅支持 original / optimized", code=ERR_PARAM)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)
    if version == "optimized" and not resume.optimized_content:
        return fail(message="暂无优化版简历，请先生成", code=ERR_PARAM)
    return None


@router.post("/upload", summary="Upload resume")
async def upload_resume(
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

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        return fail(
            message=f"File is too large: {len(raw) / 1024 / 1024:.1f}MB (max 10MB).",
            code=ERR_FILE,
        )

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
async def parse_resume(
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
async def list_resume(
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
async def accessible_resume_list(
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
                {"company": "某互联网公司", "title": "Java后端开发", "desc": "负责订单系统的设计与开发，使用Spring Cloud微服务架构处理日均百万级请求。"},
                {"company": "某科技公司", "title": "Java开发实习生", "desc": "参与内部管理系统的后端开发，独立完成权限管理模块。"}
            ],
            "project_experience": [
                {"name": "电商订单系统", "desc": "基于Spring Cloud实现订单创建、支付回调、库存扣减等核心流程。", "tech": ["Spring Cloud", "MySQL", "Redis"]}
            ]
        }
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
                {"company": "某科技公司", "title": "前端开发", "desc": "负责管理后台前端架构设计与开发，基于Vue3 + Element Plus实现20+业务页面。"}
            ],
            "project_experience": [
                {"name": "智能数据分析平台", "desc": "基于React + TypeScript开发数据可视化看板，集成ECharts实现多维度图表展示。", "tech": ["React", "TypeScript", "ECharts"]}
            ]
        }
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
                {"company": "某大数据公司", "title": "全栈开发", "desc": "负责数据采集平台的架构设计与开发，使用FastAPI + Vue3实现完整前后端分离。"},
                {"company": "某软件公司", "title": "后端开发", "desc": "使用Django开发SaaS平台API，负责用户认证、权限管理模块。"}
            ],
            "project_experience": [
                {"name": "实时数据采集平台", "desc": "基于FastAPI + WebSocket实现数据实时采集与推送，日处理百万级数据点。", "tech": ["FastAPI", "WebSocket", "PostgreSQL"]}
            ]
        }
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
                {"company": "某咨询公司", "title": "数据分析助理", "desc": "负责客户业务数据的清洗、分析和可视化，使用Python完成自动化报表。"}
            ],
            "project_experience": [
                {"name": "用户增长分析项目", "desc": "基于Pandas和Tableau分析用户留存与转化数据，输出增长策略建议。", "tech": ["Pandas", "Tableau"]}
            ]
        }
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
                {"company": "某AI公司", "title": "算法工程师", "desc": "负责NLP模型训练与部署，参与基于LLM的智能客服系统开发。"},
                {"company": "某科技公司", "title": "算法实习生", "desc": "参与文本分类和实体识别模型的研发与优化。"}
            ],
            "project_experience": [
                {"name": "智能客服意图识别系统", "desc": "基于BERT微调实现多分类意图识别，准确率达96%，上线QPS 200+。", "tech": ["PyTorch", "BERT", "FastAPI"]}
            ]
        }
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
                {"company": "某云计算公司", "title": "DevOps工程师", "desc": "负责K8s集群管理与CI/CD流水线建设，管理200+微服务的自动化部署。"},
                {"company": "某互联网公司", "title": "运维开发", "desc": "基于Ansible和Shell实现服务器自动化配置与监控。"}
            ],
            "project_experience": [
                {"name": "微服务CI/CD平台", "desc": "基于GitLab CI + ArgoCD构建自动化部署流水线，支撑每日50+次发布。", "tech": ["Kubernetes", "GitLab CI", "ArgoCD"]}
            ]
        }
    },
]


@router.post("/seed-demo", summary="一键生成演示候选人简历")
async def seed_demo_resumes(
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
async def get_resume(
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
async def delete_resume(
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
async def generate_optimized_resume(
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
async def get_resume_versions(
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
        resume_export_service._build_original_md(resume)
        if hasattr(resume_export_service, "_build_original_md")
        else ""
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


@router.post("/{resume_id}/export", summary="Prepare resume export")
async def export_resume(
    resume_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fmt = (payload or {}).get("format", "docx")
    version = (payload or {}).get("version", "optimized")

    resume = _get_owned_resume(db, resume_id, current_user.id)
    error = _validate_export_request(resume, fmt, version)
    if error:
        return error

    return ok(
        data={
            "download_url": f"/api/resume/{resume_id}/download?format={fmt}&version={version}",
            "format": fmt,
            "version": version,
        },
        message=f"{fmt.upper()} 导出成功",
    )


@router.get("/{resume_id}/download", summary="Download exported resume")
async def download_resume_export(
    resume_id: int,
    format: str = Query("docx"),
    version: str = Query("optimized"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    error = _validate_export_request(resume, format, version)
    if error:
        return error

    try:
        if format == "docx":
            rel_path = resume_export_service.export_docx(resume_id, version, db, user_id=current_user.id)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            rel_path = resume_export_service.export_pdf(resume_id, version, db, user_id=current_user.id)
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
