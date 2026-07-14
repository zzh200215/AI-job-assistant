"""Authentication-related Pydantic models."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.password_blacklist import is_blacklisted
from app.core.user_roles import CANDIDATE_ROLE


def _normalize_email(value) -> str:
    return str(value).strip().lower()


def _normalize_account(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("请输入邮箱或用户名")
    return normalized


def _validate_password_strength(
    value: str,
    username: str | None = None,
    email: str | None = None,
) -> str:
    if value != value.strip():
        raise ValueError("密码首尾不能包含空格")
    if len(value) < 8:
        raise ValueError("密码长度至少为 8 位")

    has_lower = bool(re.search(r"[a-z]", value))
    has_upper = bool(re.search(r"[A-Z]", value))
    has_digit = bool(re.search(r"\d", value))
    # Punctuation/special characters commonly accepted by systems
    has_special = bool(re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", value))
    categories = sum([has_lower, has_upper, has_digit, has_special])

    if len(value) >= 12:
        if categories < 2:
            raise ValueError("密码需至少包含字母、数字、特殊字符中的 2 种")
    else:
        if categories < 3:
            raise ValueError("密码需至少包含大写字母、小写字母、数字、特殊字符中的 3 种")

    if is_blacklisted(value):
        raise ValueError("密码过于常见，请更换更复杂的密码")

    if username and value.lower() == username.strip().lower():
        raise ValueError("密码不能与用户名相同")

    if email:
        local = email.split("@")[0].strip().lower()
        if local and value.lower() == local:
            raise ValueError("密码不能与邮箱前缀相同")

    return value


class RegisterReq(BaseModel):
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=8, max_length=100, description="密码")

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

    @model_validator(mode="after")
    def validate_password(self):
        _validate_password_strength(
            self.password,
            username=self.username,
            email=self.email,
        )
        return self


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

    @model_validator(mode="after")
    def validate_password(self):
        _validate_password_strength(
            self.new_password,
            username=self.account,
            email=self.email,
        )
        if self.new_password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self


class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    role: Literal["candidate", "admin"] = CANDIDATE_ROLE
    is_admin: bool = False
    created_at: str | None = None
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

    avatar_url: str | None = Field(default=None, max_length=500)
    nickname: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=20)
    bio: str | None = None
    # 求职意向
    job_seeking_status: str | None = None
    expected_position: str | None = Field(default=None, max_length=200)
    expected_city: str | None = Field(default=None, max_length=200)
    expected_salary_min: int | None = Field(default=None, ge=0)
    expected_salary_max: int | None = Field(default=None, ge=0)
    expected_industry: str | None = Field(default=None, max_length=200)
    work_years: int | None = Field(default=None, ge=0)
    education: str | None = Field(default=None)
    current_employer: str | None = Field(default=None, max_length=200)
    current_position: str | None = Field(default=None, max_length=200)
    skill_tags: list | None = None
    social_links: dict | None = None

    @field_validator("job_seeking_status")
    @classmethod
    def validate_job_seeking_status(cls, value: str | None) -> str | None:
        if value is not None and value not in {"active", "urgent", "observing", "not_looking", ""}:
            raise ValueError("求职状态可选值: active/urgent/observing/not_looking")
        return value

    @field_validator("education")
    @classmethod
    def validate_education(cls, value: str | None) -> str | None:
        if value is not None and value not in {"", "high_school", "associate", "bachelor", "master", "phd"}:
            raise ValueError("学历可选值: high_school/associate/bachelor/master/phd")
        return value


class AuthResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
