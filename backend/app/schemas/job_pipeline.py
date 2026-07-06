# -*- coding: utf-8 -*-
"""投递流程 Pydantic 模型"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


PIPELINE_STAGES = {"todo", "applied", "interview", "rejected"}


class StageHistoryItem(BaseModel):
    stage: str = Field(..., description="流程阶段")
    at: str = Field(..., description="阶段变更时间 ISO 格式")

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: str) -> str:
        if value not in PIPELINE_STAGES:
            raise ValueError("非法的投递流程阶段")
        return value


class PipelineBase(BaseModel):
    resume_id: Optional[int] = Field(default=None, description="关联简历 ID")
    jd_id: Optional[int] = Field(default=None, description="关联 JD ID")
    title: str = Field(..., min_length=1, max_length=200, description="岗位名称")
    company: str = Field(default="", max_length=200, description="公司名称")
    location: str = Field(default="", max_length=100, description="地点")
    salary_range: str = Field(default="", max_length=100, description="薪资范围")
    source: str = Field(default="manual", max_length=20, description="岗位来源")
    source_url: str = Field(default="", max_length=500, description="岗位来源链接")
    summary: str = Field(default="", description="岗位摘要")
    raw_text: str = Field(default="", description="完整 JD 文本")
    experience_requirement: str = Field(default="", max_length=50, description="经验要求")
    education_requirement: str = Field(default="", max_length=50, description="学历要求")
    industry: str = Field(default="", max_length=100, description="行业")
    skill_tags: List[str] = Field(default_factory=list, description="技能标签")
    priority_score: int = Field(default=0, ge=0, le=100, description="投递优先级得分")
    priority_label: str = Field(default="", max_length=50, description="投递优先级标签")
    stage: str = Field(default="todo", description="流程阶段")
    note: str = Field(default="", description="备注")
    next_action: str = Field(default="", max_length=255, description="下一步动作")
    follow_up_at: Optional[str] = Field(default=None, description="下次跟进时间，ISO 日期/时间字符串")
    resume_name: str = Field(default="", max_length=255, description="简历名称快照")
    stage_history: List[StageHistoryItem] = Field(default_factory=list, description="阶段流转历史")

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: str) -> str:
        if value not in PIPELINE_STAGES:
            raise ValueError("非法的投递流程阶段")
        return value


class PipelineCreateReq(PipelineBase):
    pass


class PipelineUpdateReq(BaseModel):
    resume_id: Optional[int] = Field(default=None, description="关联简历 ID")
    jd_id: Optional[int] = Field(default=None, description="关联 JD ID")
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    company: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=100)
    salary_range: Optional[str] = Field(default=None, max_length=100)
    source: Optional[str] = Field(default=None, max_length=20)
    source_url: Optional[str] = Field(default=None, max_length=500)
    summary: Optional[str] = None
    raw_text: Optional[str] = None
    experience_requirement: Optional[str] = Field(default=None, max_length=50)
    education_requirement: Optional[str] = Field(default=None, max_length=50)
    industry: Optional[str] = Field(default=None, max_length=100)
    skill_tags: Optional[List[str]] = None
    priority_score: Optional[int] = Field(default=None, ge=0, le=100)
    priority_label: Optional[str] = Field(default=None, max_length=50)
    stage: Optional[str] = None
    note: Optional[str] = None
    next_action: Optional[str] = Field(default=None, max_length=255)
    follow_up_at: Optional[str] = None
    resume_name: Optional[str] = Field(default=None, max_length=255)
    stage_history: Optional[List[StageHistoryItem]] = None

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PIPELINE_STAGES:
            raise ValueError("非法的投递流程阶段")
        return value


class PipelineListResp(BaseModel):
    total: int
    items: List[Dict[str, Any]]
