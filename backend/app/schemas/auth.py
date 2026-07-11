# -*- coding: utf-8 -*-
"""Authentication-related Pydantic models."""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.user_roles import CANDIDATE_ROLE


def _normalize_email(value) -> str:
    return str(value).strip().lower()


def _normalize_account(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("请输入邮箱或用户名")
    return normalized


def _validate_password_strength(value: str) -> str:
    if value != value.strip():
        raise ValueError("密码首尾不能包含空格")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("密码需至少包含 1 个字母和 1 个数字")
    return value


class RegisterReq(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=8, max_length=100, description="密码")
    role: Literal["candidate", "recruiter"] = Field(default=CANDIDATE_ROLE, description="用户身份")

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("用户名至少 2 个字符")
        if not re.fullmatch(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", normalized):
            raise ValueError("用户名仅支持中文、字母、数字、下划线和短横线")
        return normalized

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class LoginReq(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="邮箱或用户名",
        validation_alias=AliasChoices("account", "email"),
    )
    password: str = Field(..., min_length=1, max_length=100, description="密码")

    @field_validator("account")
    @classmethod
    def normalize_account(cls, value: str) -> str:
        return _normalize_account(value)

    @field_validator("password")
    @classmethod
    def normalize_password(cls, value: str) -> str:
        if not value:
            raise ValueError("请输入密码")
        return value


class PasswordResetReq(BaseModel):
    account: str = Field(..., min_length=2, max_length=100, description="邮箱或用户名")
    email: EmailStr = Field(..., description="注册邮箱")
    new_password: str = Field(..., min_length=8, max_length=100, description="新密码")
    confirm_password: str = Field(..., min_length=8, max_length=100, description="确认密码")

    @field_validator("account")
    @classmethod
    def normalize_account(cls, value: str) -> str:
        return _normalize_account(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value) -> str:
        return _normalize_email(value)

    @field_validator("new_password", "confirm_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)

    @model_validator(mode="after")
    def validate_password_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self


class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    role: Literal["candidate", "recruiter"] = CANDIDATE_ROLE
    is_admin: bool = False
    created_at: Optional[str] = None
    # 求职者资料
    avatar_url: str = ""
    nickname: str = ""
    phone: str = ""
    bio: str = ""
    # 求职意向
    job_seeking_status: str = ""
    expected_position: str = ""
    expected_city: str = ""
    expected_salary_min: int = 0
    expected_salary_max: int = 0
    expected_industry: str = ""
    work_years: int = 0
    education: str = ""
    current_employer: str = ""
    current_position: str = ""
    skill_tags: list = []
    social_links: dict = {}


class UserProfileUpdateReq(BaseModel):
    """用户个人资料更新请求"""
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    nickname: Optional[str] = Field(default=None, max_length=50)
    phone: Optional[str] = Field(default=None, max_length=20)
    bio: Optional[str] = None
    # 求职意向
    job_seeking_status: Optional[str] = None
    expected_position: Optional[str] = Field(default=None, max_length=200)
    expected_city: Optional[str] = Field(default=None, max_length=200)
    expected_salary_min: Optional[int] = Field(default=None, ge=0)
    expected_salary_max: Optional[int] = Field(default=None, ge=0)
    expected_industry: Optional[str] = Field(default=None, max_length=200)
    work_years: Optional[int] = Field(default=None, ge=0)
    education: Optional[str] = Field(default=None)
    current_employer: Optional[str] = Field(default=None, max_length=200)
    current_position: Optional[str] = Field(default=None, max_length=200)
    skill_tags: Optional[list] = None
    social_links: Optional[dict] = None

    @field_validator("job_seeking_status")
    @classmethod
    def validate_job_seeking_status(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in {"active", "urgent", "observing", "not_looking", ""}:
            raise ValueError("求职状态可选值: active/urgent/observing/not_looking")
        return value

    @field_validator("education")
    @classmethod
    def validate_education(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in {"", "high_school", "associate", "bachelor", "master", "phd"}:
            raise ValueError("学历可选值: high_school/associate/bachelor/master/phd")
        return value


class AuthResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
