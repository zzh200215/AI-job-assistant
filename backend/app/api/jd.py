# -*- coding: utf-8 -*-
"""JD 相关路由"""
import traceback
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.history import JobDescription
from app.models.user import User
from app.api.auth import get_current_user
from app.schemas.jd import JDCreateReq, JDCreateResp, JDParseResp
from app.services import jd_service
from app.utils.job_access import get_accessible_job
from app.utils.response import ok, fail, ERR_PARAM, ERR_AI


router = APIRouter()


@router.post("", summary="创建岗位 JD（同时可选解析）")
async def create_jd(payload: JDCreateReq, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # ---- JD 文本非空校验 ----
    if not payload.raw_text or not payload.raw_text.strip():
        return fail(message="JD 内容不能为空", code=ERR_PARAM)

    try:
        jd = jd_service.create_jd(db, payload.title, payload.company, payload.raw_text, user_id=current_user.id)
    except Exception as e:
        return fail(message=f"JD 保存失败: {str(e)}", code=ERR_PARAM)

    return ok(JDCreateResp(
        id=jd.id,
        title=jd.title,
        company=jd.company,
        raw_text=jd.raw_text,
        parsed=jd.parsed_json or {},
    ).model_dump(), message="JD 创建成功")


@router.post("/parse", summary="解析 JD（调用 LLM）")
async def parse_jd(payload: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    jd_id = payload.get("jd_id")
    if not jd_id:
        return fail(message="jd_id 必填", code=ERR_PARAM)

    # 权限校验
    jd = db.query(JobDescription).filter(JobDescription.id == int(jd_id), JobDescription.user_id == current_user.id).first()
    if not jd:
        return fail(message="JD 不存在或无权限", code=ERR_PARAM)

    try:
        jd = jd_service.parse_and_save(db, int(jd_id))
    except ValueError as e:
        return fail(message=str(e), code=ERR_PARAM)
    except Exception as e:
        traceback.print_exc()
        return fail(message=f"AI 解析失败: {str(e)}", code=ERR_AI)

    return ok(JDParseResp(
        id=jd.id,
        title=jd.title,
        parsed=jd.parsed_json or {},
        salary_range=jd.salary_range,
        location=jd.location,
    ).model_dump(), message="JD 解析成功")


@router.get("/list", summary="JD 列表")
async def list_jd(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(JobDescription).filter(
        JobDescription.user_id == current_user.id,
    )
    q = q.order_by(JobDescription.create_time.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "salary_range": j.salary_range,
                "create_time": j.create_time.isoformat() if j.create_time else None,
            }
            for j in items
        ],
    })


@router.get("/{jd_id}", summary="获取 JD 详情")
async def get_jd(jd_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    jd = get_accessible_job(db, jd_id, current_user)
    if not jd:
        return fail(message="JD 不存在或无权限", code=ERR_PARAM)
    return ok({
        "id": jd.id,
        "title": jd.title,
        "company": jd.company,
        "location": jd.location,
        "salary_range": jd.salary_range,
        "raw_text": jd.raw_text,
        "parsed": jd.parsed_json or {},
        "create_time": jd.create_time.isoformat() if jd.create_time else None,
    })
