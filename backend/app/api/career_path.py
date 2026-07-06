# -*- coding: utf-8 -*-
"""
职业方向推荐 API

- POST /api/career-path/recommend   — 根据简历推荐岗位方向
"""
import traceback

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.history import Resume
from app.agents.career_path_agent import CareerPathAgent
from app.utils.response import ok, fail, ERR_PARAM, ERR_COMMON

router = APIRouter()


@router.post("/recommend", summary="职业方向推荐")
async def recommend_career_paths(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """根据简历技能和经验，推荐适合投递的岗位方向"""
    resume = db.query(Resume).filter(
        Resume.id == resume_id,
        Resume.user_id == current_user.id,
        Resume.is_deleted == 0,
    ).first()
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    resume_data = resume.parsed_json or {}
    if not resume_data:
        return fail(message="简历尚未解析，请先解析", code=ERR_PARAM)

    try:
        agent = CareerPathAgent()
        result = agent.recommend(resume_data)
        paths = result.get("career_paths", [])
        summary = result.get("summary", "")
        return ok(data={
            "resume_id": resume_id,
            "resume_name": resume.name or resume.file_name,
            "career_paths": paths,
            "summary": summary,
        }, message=f"推荐 {len(paths)} 个岗位方向")
    except Exception as e:
        traceback.print_exc()
        return fail(message=f"职业方向推荐失败: {str(e)[:80]}", code=ERR_COMMON)
