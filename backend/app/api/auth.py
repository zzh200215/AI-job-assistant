# -*- coding: utf-8 -*-
"""Authentication endpoints: register, login, reset password, current user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.core.user_roles import CANDIDATE_ROLE, RECRUITER_ROLE, USER_ROLES
from app.models.user import User
from app.schemas.auth import AuthResp, LoginReq, PasswordResetReq, RegisterReq, UserInfo, UserProfileUpdateReq
from app.utils.response import ERR_PARAM, fail, ok

router = APIRouter()


def _resolve_user_role(user: User) -> str:
    return user.role if user.role in USER_ROLES else CANDIDATE_ROLE


def _build_user_info(user: User) -> UserInfo:
    return UserInfo(
        id=user.id,
        username=user.username,
        email=user.email or "",
        role=_resolve_user_role(user),
        is_admin=user.username in settings.admin_usernames_list,
        created_at=user.created_at.isoformat() if user.created_at else None,
        avatar_url=getattr(user, "avatar_url", "") or "",
        nickname=getattr(user, "nickname", "") or "",
        phone=getattr(user, "phone", "") or "",
        bio=getattr(user, "bio", "") or "",
        job_seeking_status=getattr(user, "job_seeking_status", "") or "",
        expected_position=getattr(user, "expected_position", "") or "",
        expected_city=getattr(user, "expected_city", "") or "",
        expected_salary_min=getattr(user, "expected_salary_min", 0) or 0,
        expected_salary_max=getattr(user, "expected_salary_max", 0) or 0,
        expected_industry=getattr(user, "expected_industry", "") or "",
        work_years=getattr(user, "work_years", 0) or 0,
        education=getattr(user, "education", "") or "",
        current_employer=getattr(user, "current_employer", "") or "",
        current_position=getattr(user, "current_position", "") or "",
        skill_tags=getattr(user, "skill_tags", None) or [],
        social_links=getattr(user, "social_links", None) or {},
    )


def _create_auth_response(user: User, message: str) -> dict:
    token = create_access_token(
        {
            "sub": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": _resolve_user_role(user),
        }
    )
    payload = AuthResp(access_token=token, user=_build_user_info(user)).model_dump()
    return ok(payload, message=message)


def _find_user_by_account(db: Session, account: str) -> User | None:
    normalized = account.strip()
    lowered = normalized.lower()
    return (
        db.query(User)
        .filter(
            or_(
                func.lower(User.email) == lowered,
                func.lower(User.username) == lowered,
            )
        )
        .first()
    )


@router.post("/register", summary="用户注册")
async def register(payload: RegisterReq, db: Session = Depends(get_db)):
    if payload.role == RECRUITER_ROLE:
        return fail(message="公开注册仅支持求职者账号", code=ERR_PARAM)

    if payload.username in settings.admin_usernames_list:
        return fail(message="该用户名不可注册", code=ERR_PARAM)

    existing_user = (
        db.query(User)
        .filter(
            or_(
                func.lower(User.email) == payload.email,
                func.lower(User.username) == payload.username.lower(),
            )
        )
        .first()
    )
    if existing_user:
        if existing_user.email and existing_user.email.lower() == payload.email:
            return fail(message="该邮箱已被注册", code=ERR_PARAM)
        return fail(message="该用户名已被占用", code=ERR_PARAM)

    user = User(
        username=payload.username,
        email=payload.email,
        password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _create_auth_response(user, message="注册成功")


@router.post("/login", summary="用户登录")
async def login(payload: LoginReq, db: Session = Depends(get_db)):
    user = _find_user_by_account(db, payload.account)
    if not user or not verify_password(payload.password, user.password):
        return fail(message="邮箱/用户名或密码错误", code=ERR_PARAM)

    return _create_auth_response(user, message="登录成功")


@router.post("/reset-password", summary="重置密码")
async def reset_password(payload: PasswordResetReq, db: Session = Depends(get_db)):
    user = _find_user_by_account(db, payload.account)
    if not user or (user.email or "").strip().lower() != payload.email:
        return fail(message="账户与注册邮箱不匹配", code=ERR_PARAM)

    user.password = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    return ok(message="密码已重置，请使用新密码登录")


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    """Extract current logged-in user or raise 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证 Token")

    token = authorization[7:]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    user_id = int(payload.get("sub", 0))
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


@router.get("/me", summary="获取当前登录用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    return ok(_build_user_info(current_user).model_dump())


@router.put("/me/profile", summary="更新用户个人资料")
async def update_profile(
    payload: UserProfileUpdateReq,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump(exclude_unset=True)

    # 薪资逻辑校验
    if "expected_salary_min" in data and "expected_salary_max" in data:
        if data["expected_salary_min"] and data["expected_salary_max"]:
            if data["expected_salary_min"] > data["expected_salary_max"]:
                return fail(message="期望最低薪资不能高于最高薪资", code=ERR_PARAM)

    for field, value in data.items():
        if hasattr(current_user, field):
            setattr(current_user, field, value)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return ok(_build_user_info(current_user).model_dump(), message="个人资料已更新")
