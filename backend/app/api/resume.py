"""Resume APIs."""

from __future__ import annotations

import os
import traceback
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.tenant_context import stamp_tenant, tenant_filter
from app.models.history import Resume, ResumeVersion
from app.models.user import User
from app.schemas.resume import ResumeParseResp, ResumeUploadResp
from app.services import resume_export_service, resume_service
from app.services.resume_analysis_service import analyze_resume, quick_score_resume
from app.services.resume_rewrite_service import apply_rewrite_suggestions, build_rewrite_suggestions
from app.services.resume_tailor_service import tailor_resume_for_jd
from app.services.resume_workspace_service import build_ats_snapshot, build_markdown_diff
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
            tenant_filter(Resume),
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


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, (str, int, float)) and str(item).strip()]


def _number_or_none(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _dimension(dimensions: Any, key: str) -> dict[str, Any]:
    """Read one analysis dimension whatever shape the model emitted.

    The analysis prompt asks for {score, issues, suggestions} per dimension and
    the response is never schema-checked, so a bare number must also work. Reading
    `dimensions.get(key, 0)` directly handed the whole dict to the UI as a "score",
    which rendered as a JSON blob beside a 0-width progress bar.
    """
    value = dimensions.get(key) if isinstance(dimensions, dict) else None
    if isinstance(value, dict):
        return {
            "score": _number_or_none(value.get("score")),
            "issues": _as_text_list(value.get("issues")),
            "suggestions": _as_text_list(value.get("suggestions")),
            "missing_keywords": _as_text_list(value.get("missing_keywords")),
        }
    return {"score": _number_or_none(value), "issues": [], "suggestions": [], "missing_keywords": []}


def _roadmap_items(value: Any) -> list[str]:
    """Flatten quick_wins / medium_effort / major_rework into one list.

    A dict-shaped roadmap used to fail an `isinstance(value, list)` check and be
    discarded, so the roadmap panel read "暂无改进建议" for every report that
    actually followed the schema.
    """
    if isinstance(value, dict):
        items = [item for track in ("quick_wins", "medium_effort", "major_rework") for item in _as_text_list(value.get(track))]
        if items:
            return items
        return [str(v).strip() for v in value.values() if isinstance(v, str) and str(v).strip()]
    return _as_text_list(value)


def _match_summary(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""

    def _join(items: list[str]) -> str:
        # Model-emitted items often already end in a full stop, which reads badly
        # once they are joined with "；".
        return "；".join(item.rstrip("。；; ") for item in items if item.rstrip("。；; "))

    parts = []
    level = value.get("match_level")
    if level:
        parts.append(f"匹配度：{level}")
    gaps = _as_text_list(value.get("gap_analysis"))
    if gaps:
        parts.append("差距：" + _join(gaps))
    bridge = _as_text_list(value.get("bridge_strategies"))
    if bridge:
        parts.append("弥补方式：" + _join(bridge))
    return "。".join(parts)


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

    # 权益校验：简历数量上限
    allowed, msg, _ = check_quota(db, current_user.id, "resume_count", consume=False)
    if not allowed:
        return fail(message=msg, code=ERR_QUOTA)

    try:
        meta = resume_service.save_upload_file(raw, file.filename)
        obj = stamp_tenant(
            Resume(
                user_id=current_user.id,
                file_name=meta["file_name"],
                file_path=meta["file_path"],
                file_type=meta["file_type"],
                file_size=meta["file_size"],
            )
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
        tenant_filter(Resume),
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
        tenant_filter(Resume),
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
                tenant_filter(Resume),
                Resume.user_id == current_user.id,
                Resume.name == cand["name"],
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        import json

        obj = stamp_tenant(
            Resume(
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
async def create_resume_version(
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
async def compare_resume_versions(
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
async def update_resume_version(
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
async def save_suggestion_decision(
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
async def preview_resume_ats(
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
async def export_resume(
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
async def download_resume_export(
    resume_id: int,
    format: str = Query("docx"),
    version: str = Query("optimized"),
    template: str = Query("classic"),
    version_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = _get_owned_resume(db, resume_id, current_user.id)
    error = _validate_export_request(resume, format, version)
    if error:
        return error
    if version_id and not _get_resume_version(db, resume_id, int(version_id)):
        return fail(message="导出版本不存在或无权限", code=ERR_PARAM)

    try:
        if format == "docx":
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
async def tailor_resume(
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


@router.post("/{resume_id}/rewrite-suggestions", summary="生成行级简历改写建议")
async def rewrite_suggestions(
    resume_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """每条建议锚定一个文本块，返回 原文 → 改后；不落库，采纳与否由候选人决定。"""
    jd_id = (payload or {}).get("jd_id")
    try:
        result = build_rewrite_suggestions(db, resume_id, jd_id=int(jd_id) if jd_id else None, user_id=current_user.id)
        return ok(result, message=f"生成 {len(result['suggestions'])} 条改写建议")
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"改写建议生成失败: {exc}", code=ERR_AI)


@router.post("/{resume_id}/apply-rewrites", summary="应用行级改写并重算匹配分")
async def apply_rewrites(
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
        message = (
            f"已应用 {len(result['applied'])} 处改写"
            if result["changed"]
            else "没有改动被应用"
        )
        return ok(result, message=message)
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"应用改写失败: {exc}", code=ERR_COMMON)


# ============================================================
# 简历深度分析
# ============================================================


@router.get("/{resume_id}/quick-score", summary="简历完整度检查（基于规则）")
async def get_resume_quick_score(
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
async def analyze_resume_api(
    resume_id: int,
    payload: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    AI深度分析简历，包含5维度评分、改进路线图、目标岗位匹配差距分析。
    - structure: 结构完整性
    - content_quality: 内容质量
    - keyword_density: 关键词密度
    - differentiation: 差异化竞争力
    - ats_friendly: ATS友好度
    """
    target_position = ""
    if payload:
        target_position = payload.get("target_position", "")

    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    try:
        result = analyze_resume(db, resume_id, target_position=target_position, user_id=current_user.id)
        return ok(result, message="简历深度分析完成")
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"分析失败: {exc}", code=ERR_AI)


@router.post("/{resume_id}/diagnose", summary="简历诊断（快速评分+AI分析聚合）")
async def diagnose_resume(
    resume_id: int,
    payload: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    聚合诊断接口：合并快速评分与 AI 深度分析，返回结构化诊断报告。
    用于简历中心页面的「AI诊断」弹窗。
    返回：
    - total_score: 综合评分
    - structure_score: 结构评分
    - expression_score: 表达评分
    - keyword_score: 关键词覆盖评分
    - highlight_score: 亮点评分
    - structure_issues: 结构问题列表
    - expression_issues: 表达问题列表
    - missing_keywords: 缺失关键词列表
    - highlights: 亮点列表
    - match_analysis: 岗位匹配分析
    - ats_score: ATS 友好度评分
    - ats_issues: ATS 问题列表
    """
    resume = _get_owned_resume(db, resume_id, current_user.id)
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    target_position = ""
    if payload:
        target_position = payload.get("target_position", "")

    try:
        # 1. 快速评分（规则引擎）
        quick_result = quick_score_resume(db, resume_id, user_id=current_user.id)

        # 2. AI 深度分析
        analysis_result = analyze_resume(
            db,
            resume_id,
            target_position=target_position,
            user_id=current_user.id,
        )

        # 3. 聚合诊断报告
        dimensions = analysis_result.get("dimensions", {})
        issues = _as_text_list(analysis_result.get("critical_issues"))
        strengths = _as_text_list(analysis_result.get("strengths"))
        roadmap = _roadmap_items(analysis_result.get("improvement_roadmap"))
        target_match = _match_summary(analysis_result.get("target_position_match", ""))

        structure = _dimension(dimensions, "structure")
        content = _dimension(dimensions, "content_quality")
        keyword = _dimension(dimensions, "keyword_density")
        differentiation = _dimension(dimensions, "differentiation")
        ats = _dimension(dimensions, "ats_friendly")

        # `analyze_resume` returns whatever the model emitted with no schema, so
        # overall_score can legitimately be absent. It must not be backfilled
        # from quick_score_resume: that number counts how many resume sections
        # are populated, which is a completeness measure, not a quality one.
        total_score = _number_or_none(analysis_result.get("overall_score"))

        # The model attributes issues to dimensions itself; keyword-classifying
        # the free-text critical_issues list is only the fallback. An empty bucket
        # means "not identified", never "nothing wrong" — the previous hardcoded
        # defaults presented stock advice as if it came from this resume.
        structure_issues = structure["issues"] or [
            issue
            for issue in issues
            if any(kw in issue.lower() for kw in ["结构", "格式", "布局", "顺序", "section", "缺少", "缺失"])
        ]
        expression_issues = content["issues"] or [
            issue
            for issue in issues
            if any(kw in issue.lower() for kw in ["表达", "描述", "语言", "措辞", "啰嗦", "模糊", "简略"])
        ]
        missing_keywords = keyword["missing_keywords"]
        highlights = strengths[:5]

        # These come from the rule-based completeness check ("缺少工作经历"), so
        # they are not ATS parseability findings and are no longer labelled as
        # such. The ATS score itself is the model's `ats_friendly` dimension.
        completeness_issues = quick_result.get("issues", []) if isinstance(quick_result.get("issues"), list) else []

        result = {
            "total_score": total_score,
            "structure_score": structure["score"],
            "expression_score": content["score"],
            "keyword_score": keyword["score"],
            "highlight_score": differentiation["score"],
            "ats_score": ats["score"],
            "structure_issues": structure_issues,
            "expression_issues": expression_issues,
            "missing_keywords": missing_keywords[:10],
            "highlights": highlights,
            "match_analysis": target_match,
            "completeness_issues": completeness_issues,
            "completeness_score": quick_result.get("completeness_score"),
            "module_check": quick_result.get("module_check", {}),
            "improvement_roadmap": roadmap,
        }
        return ok(result, message="简历诊断完成")
    except ValueError as exc:
        return fail(message=str(exc), code=ERR_PARAM)
    except Exception as exc:
        traceback.print_exc()
        return fail(message=f"诊断失败: {exc}", code=ERR_AI)
