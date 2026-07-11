# -*- coding: utf-8 -*-
"""投递流程 Pydantic 模型"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.job_pipeline import PIPELINE_STAGES, VALID_TRANSITIONS


class StageHistoryItem(BaseModel):
    stage: str = Field(..., description="流程阶段")
    at: str = Field(..., description="阶段变更时间 ISO 格式")
    note: str = Field(default="", description="变更备注")

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: str) -> str:
        if value not in PIPELINE_STAGES:
            raise ValueError(f"非法的投递流程阶段，可选值: {', '.join(sorted(PIPELINE_STAGES))}")
        return value


class InterviewInfo(BaseModel):
    """面试信息"""
    interview_at: Optional[str] = Field(default=None, description="面试时间，ISO 格式")
    interview_type: str = Field(default="", description="面试类型: tech/hr/comprehensive/case")
    interview_round: int = Field(default=0, ge=0, description="面试轮次")
    interview_location: str = Field(default="", description="面试地点/视频链接")
    interview_contact: str = Field(default="", description="面试联系人")


class OfferInfo(BaseModel):
    """Offer 信息"""
    offer_salary: str = Field(default="", max_length=100, description="Offer 薪资")
    offer_details: Dict[str, Any] = Field(default_factory=dict, description="Offer 详情")
    offer_deadline: Optional[str] = Field(default=None, description="Offer 回复截止日期，ISO 格式")


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
    # 面试信息
    interview_at: Optional[str] = Field(default=None, description="面试时间")
    interview_type: str = Field(default="", description="面试类型")
    interview_round: int = Field(default=0, ge=0, description="面试轮次")
    interview_location: str = Field(default="", description="面试地点/视频链接")
    interview_contact: str = Field(default="", description="面试联系人")
    # Offer 信息
    offer_salary: str = Field(default="", max_length=100, description="Offer 薪资")
    offer_details: Dict[str, Any] = Field(default_factory=dict, description="Offer 详情")
    offer_deadline: Optional[str] = Field(default=None, description="Offer 回复截止日期")

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: str) -> str:
        if value not in PIPELINE_STAGES:
            raise ValueError(f"非法的投递流程阶段，可选值: {', '.join(sorted(PIPELINE_STAGES))}")
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
    # 面试信息
    interview_at: Optional[str] = None
    interview_type: Optional[str] = None
    interview_round: Optional[int] = Field(default=None, ge=0)
    interview_location: Optional[str] = None
    interview_contact: Optional[str] = None
    # Offer 信息
    offer_salary: Optional[str] = Field(default=None, max_length=100)
    offer_details: Optional[Dict[str, Any]] = None
    offer_deadline: Optional[str] = None

    @field_validator("stage")
    @classmethod
    def validate_stage(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PIPELINE_STAGES:
            raise ValueError(f"非法的投递流程阶段，可选值: {', '.join(sorted(PIPELINE_STAGES))}")
        return value


class StageTransitionReq(BaseModel):
    """阶段流转请求"""
    target_stage: str = Field(..., description="目标阶段")
    note: str = Field(default="", description="流转备注")
    # 面试信息（流转到 interview 时可携带）
    interview_at: Optional[str] = Field(default=None, description="面试时间")
    interview_type: Optional[str] = Field(default=None, description="面试类型")
    interview_round: Optional[int] = Field(default=None, ge=0)
    interview_location: Optional[str] = Field(default=None, description="面试地点/视频链接")
    interview_contact: Optional[str] = Field(default=None, description="面试联系人")
    # Offer 信息（流转到 offer 时可携带）
    offer_salary: Optional[str] = Field(default=None, max_length=100)
    offer_details: Optional[Dict[str, Any]] = None
    offer_deadline: Optional[str] = Field(default=None)

    @field_validator("target_stage")
    @classmethod
    def validate_target_stage(cls, value: str) -> str:
        if value not in PIPELINE_STAGES:
            raise ValueError(f"非法的目标阶段，可选值: {', '.join(sorted(PIPELINE_STAGES))}")
        return value


class PipelineListResp(BaseModel):
    total: int
    items: List[Dict[str, Any]]


class PipelineKanbanResp(BaseModel):
    """看板视图响应"""
    stages: Dict[str, List[Dict[str, Any]]] = Field(
        ..., description="按阶段分组的投递记录"
    )
    stage_counts: Dict[str, int] = Field(
        ..., description="各阶段记录数"
    )
