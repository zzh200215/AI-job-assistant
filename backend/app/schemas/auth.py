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


class AuthResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
