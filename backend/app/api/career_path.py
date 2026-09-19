"""
职业方向推荐 API

- POST /api/career-path/recommend — 从岗位库里统计出的方向 + 覆盖率 + 薪资证据

数值（覆盖度、缺失技能频次、薪资分位、样本数）全部由 `career_evidence` 计算；
模型只在这些方向里排序和写理由，理由不是真实推理时回落到规则句。
"""

import traceback

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.agents.career_path_agent import CareerPathAgent, rule_category, rule_reason
from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.history import Resume
from app.models.user import User
from app.services.career_evidence import derive_directions
from app.utils.response import ERR_COMMON, ERR_PARAM, fail, ok

router = APIRouter()


@router.post("/recommend", summary="职业方向推荐")
async def recommend_career_paths(
    resume_id: int,
    limit: int = Query(8, ge=1, le=20, description="最多返回几个方向"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按候选人技能对岗位库里的方向排序，并给出每个方向的支撑样本。"""
    resume = (
        db.query(Resume)
        .filter(
            Resume.id == resume_id,
            Resume.user_id == current_user.id,
            Resume.is_deleted == 0,
        )
        .first()
    )
    if not resume:
        return fail(message="简历不存在或无权限", code=ERR_PARAM)

    resume_data = resume.parsed_json or {}
    if not resume_data:
        return fail(message="简历尚未解析，请先解析", code=ERR_PARAM)

    try:
        directions, corpus = derive_directions(db, resume_data, current_user, limit=limit)
        result = CareerPathAgent().recommend(resume_data, directions)
        by_key = {direction.key: direction for direction in directions}

        paths = [{**by_key[path["direction_key"]].to_dict(), **path} for path in result["career_paths"]]
        if not paths:
            # The evidence exists whether or not the model cooperated, so the page
            # degrades to a ranked, rule-explained list rather than to nothing.
            paths = [
                {
                    **direction.to_dict(),
                    "category": rule_category(direction),
                    "reason": rule_reason(direction),
                    "reason_source": "rules",
                }
                for direction in directions
            ]

        return ok(
            data={
                "resume_id": resume_id,
                "resume_name": resume.name or resume.file_name,
                "career_paths": paths,
                "summary": result.get("summary", ""),
                "reason_source": result.get("reason_source", "rules") if paths else "rules",
                "rejected": result.get("rejected", []),
                "corpus": corpus,
            },
            message=f"推荐 {len(paths)} 个岗位方向"
            if paths
            else "岗位库里没有可统计的岗位，先导入或搜索岗位再试",
        )
    except Exception as e:
        traceback.print_exc()
        return fail(message=f"职业方向推荐失败: {str(e)[:80]}", code=ERR_COMMON)
