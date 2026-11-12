"""演示数据的入口：一颗按钮把新库变成"能走完主链"的样子。

为什么是个独立模块而不是塞进 `/resume` 或 `/jobs`：它一次动三张表（简历、岗位、投递记录），
挂在任何一域下面都会让那个域的语义变糊——"生成演示数据"不是简历能力，也不是岗位能力，
它是**首次体验**的入口，所以它有自己的前缀。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.demo_seed_service import seed_demo_dataset
from app.utils.response import ok

router = APIRouter()


@router.post("/seed", summary="一键写入演示数据（简历 + 岗位 + 投递记录）")
def seed_demo(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """三步各自幂等：重复点只会跳过已存在的行，不会灌重复。"""
    data = seed_demo_dataset(db, current_user.id)
    parts = []
    if data["resume_created"]:
        parts.append("1 份简历")
    if data["jobs_inserted"]:
        parts.append(f"{data['jobs_inserted']} 个岗位")
    if data["applications_inserted"]:
        parts.append(f"{data['applications_inserted']} 条投递记录")

    if parts:
        message = f"已生成 {'、'.join(parts)}——现在可以从简历中心开始走一遍。"
    else:
        message = "演示数据已经在了，没有再灌一遍。"
    return ok(data=data, message=message)
