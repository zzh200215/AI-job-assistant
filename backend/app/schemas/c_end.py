# -*- coding: utf-8 -*-
"""C端求职助手 Pydantic Schemas"""
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ============================================================
# 求职目标
# ============================================================

class TargetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="目标名称")
    position: str = Field("", max_length=100, description="目标岗位关键词")
    industry: str = Field("", max_length=50, description="目标行业")
    cities: list[str] = Field(default_factory=list, description="目标城市列表")
    salary_min: Optional[int] = Field(None, ge=1, description="最低薪资(K/月)")
    salary_max: Optional[int] = Field(None, ge=1, description="最高薪资(K/月)")
    skills: list[str] = Field(default_factory=list, description="核心技能列表")
    priority: str = Field("medium", pattern="^(high|medium|low)$", description="优先级")
    is_primary: int = Field(0, ge=0, le=1, description="是否主目标")
    notes: str = Field("", max_length=2000, description="备注")
    config: dict = Field(default_factory=dict, description="扩展配置")

    @field_validator("salary_max")
    @classmethod
    def salary_max_ge_min(cls, v, info):
        if v is not None and info.data.get("salary_min") and v < info.data["salary_min"]:
            raise ValueError("salary_max 必须 >= salary_min")
        return v


class TargetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    position: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=50)
    cities: Optional[list[str]] = None
    salary_min: Optional[int] = Field(None, ge=1)
    salary_max: Optional[int] = Field(None, ge=1)
    skills: Optional[list[str]] = None
    priority: Optional[str] = Field(None, pattern="^(high|medium|low)$")
    status: Optional[str] = Field(None, pattern="^(active|paused|achieved|archived)$")
    is_primary: Optional[int] = Field(None, ge=0, le=1)
    notes: Optional[str] = Field(None, max_length=2000)
    config: Optional[dict] = None


# ============================================================
# 求职日记
# ============================================================

class JournalCreate(BaseModel):
    entry_type: str = Field("note", pattern="^(note|interview_log|offer_review|reflection)$")
    title: str = Field(..., min_length=1, max_length=200, description="标题")
    content: str = Field("", max_length=10000, description="内容")
    pipeline_id: Optional[int] = Field(None, description="关联投递记录ID")
    jd_id: Optional[int] = Field(None, description="关联JD ID")
    tags: list[str] = Field(default_factory=list, description="标签")
    mood: str = Field("", pattern="^(|great|good|neutral|bad|terrible)$", description="心情")
    rating: int = Field(0, ge=0, le=5, description="自评分 0-5")
    interview_role: str = Field("", max_length=50, description="面试官角色")
    interview_round: int = Field(0, ge=0, description="面试轮次")
    interview_format: str = Field("", max_length=30, description="面试形式")
    attachments: list[str] = Field(default_factory=list, description="附件URL列表")
    is_private: int = Field(1, ge=0, le=1, description="是否私密")


class JournalUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, max_length=10000)
    entry_type: Optional[str] = Field(None, pattern="^(note|interview_log|offer_review|reflection)$")
    tags: Optional[list[str]] = None
    mood: Optional[str] = Field(None, pattern="^(|great|good|neutral|bad|terrible)$")
    rating: Optional[int] = Field(None, ge=0, le=5)
    interview_role: Optional[str] = Field(None, max_length=50)
    interview_round: Optional[int] = Field(None, ge=0)
    interview_format: Optional[str] = Field(None, max_length=30)
    attachments: Optional[list[str]] = None
    is_private: Optional[int] = Field(None, ge=0, le=1)


# ============================================================
# 用户偏好
# ============================================================

class NotificationPrefsUpdate(BaseModel):
    interview_reminder: Optional[bool] = None
    offer_reminder: Optional[bool] = None
    follow_up: Optional[bool] = None
    jd_push: Optional[bool] = None
    quiet_hours_start: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="HH:MM")
    quiet_hours_end: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="HH:MM")
    jd_push_frequency: Optional[str] = Field(None, pattern="^(daily|weekly|never)$")


class PrivacyUpdate(BaseModel):
    profile_visible: Optional[bool] = None
    share_anonymized_stats: Optional[bool] = None


class DefaultsUpdate(BaseModel):
    default_resume_id: Optional[int] = None
    default_target_id: Optional[int] = None
    language: Optional[str] = Field(None, pattern="^(zh-CN|en-US)$")
    theme: Optional[str] = Field(None, pattern="^(light|dark)$")


# ============================================================
# 提醒
# ============================================================

class MatchJdsRequest(BaseModel):
    target_id: Optional[int] = Field(None, description="指定求职目标ID，为空则匹配所有目标")
