# -*- coding: utf-8 -*-
"""多智能体协作 Pydantic 模型"""
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field


class MultiAgentStartReq(BaseModel):
    resume_id: int = Field(..., description="简历 ID")
    jd_id: int = Field(..., description="岗位 JD ID")


class AutoStartReq(BaseModel):
    """智能调度入口：自然语言需求驱动，简历/JD 可不填（自动取最近一次）"""
    user_request: str = Field("", description="用户自然语言需求")
    resume_id: Optional[int] = Field(None, description="简历 ID，可选；缺省取最近一次")
    jd_id: Optional[int] = Field(None, description="岗位 JD ID，可选；缺省取最近一次")


class AgentMessageResp(BaseModel):
    id: int
    run_id: int
    agent_name: str
    status: str
    depends_on: List[str] = []
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_msg: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    tokens_used: int = 0
    cost_cents: float = 0.0


class AgentRunResp(BaseModel):
    id: int
    resume_id: int
    jd_id: int
    status: str
    summary_report: Dict[str, Any] = {}
    error_msg: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    create_time: Optional[str] = None


class MultiAgentDetailResp(BaseModel):
    run: AgentRunResp
    messages: List[AgentMessageResp]
    results: List[Dict[str, Any]]
