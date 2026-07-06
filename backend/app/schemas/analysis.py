# -*- coding: utf-8 -*-
"""分析相关 Pydantic 模型"""
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field


# ===================== 匹配度解释器 =====================

class ExplainMatchReq(BaseModel):
    resume_id: int = Field(..., description="简历 ID")
    jd_id: int = Field(..., description="岗位 JD ID")


class ExplainMatchResp(BaseModel):
    overall_score: float
    overall_reason: str
    dimensions: List[Dict]
    skill_match: Dict
    risk_points: List[str]
    optimization_suggestions: List[str]
    recommendation: str
    weights_used: Dict


class MatchReq(BaseModel):
    resume_id: int = Field(..., description="简历 ID")
    jd_id: int = Field(..., description="岗位 JD ID")
    remark: Optional[str] = Field("", description="可选备注")


class FullAnalysisReq(BaseModel):
    """一键智能分析请求"""
    resume_id: int = Field(..., description="简历 ID")
    jd_id: int = Field(..., description="岗位 JD ID")


class CandidateScreeningReq(BaseModel):
    jd_id: int = Field(..., description="目标 JD ID")
    resume_ids: List[int] = Field(..., min_length=1, description="待筛选简历 ID 列表")
    top_k: int = Field(10, ge=1, le=100, description="返回前 N 名候选人")


class CandidateScreeningSaveReq(CandidateScreeningReq):
    name: str = Field("", max_length=200, description="筛选记录名称")


# ===================== 编排器响应模型 =====================

class AgentStepResult(BaseModel):
    """单个 Agent 步骤结果"""
    agent_name: str = Field(..., description="Agent 名称")
    status: str = Field(..., description="success / failed / skipped")
    result: Optional[Dict[str, Any]] = Field(None, description="Agent 输出")
    error: str = Field("", description="失败时的错误信息")


class OrchestratorResult(BaseModel):
    """编排器统一返回格式"""
    status: str = Field(..., description="success / partial / failed")
    task_id: int = Field(..., description="AgentTask ID")
    record_id: Optional[int] = Field(None, description="AnalysisRecord ID")
    steps: List[AgentStepResult] = Field([], description="各步骤结果")
    final_report: Optional[Dict[str, Any]] = Field(None, description="最终汇总报告")
    error: str = Field("", description="失败时的错误信息")
