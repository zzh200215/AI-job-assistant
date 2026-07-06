# -*- coding: utf-8 -*-
"""Agentic RAG Pydantic 请求/响应模型"""
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field


class AgentStartReq(BaseModel):
    """启动 Agent 分析请求"""
    resume_id: int = Field(..., description="简历 ID")
    jd_id: int = Field(..., description="岗位 JD ID")


class AgentStepResp(BaseModel):
    """单个步骤响应"""
    id: int
    task_id: int
    step_name: str
    step_index: int
    status: str  # pending / running / completed / failed
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    error_msg: Optional[str] = None
    retry_count: int = 0


class AgentTaskResp(BaseModel):
    """任务详情响应"""
    id: int
    user_id: int
    resume_id: int
    jd_id: int
    analysis_record_id: Optional[int] = None
    intent: Optional[str] = None
    intent_detail: Optional[Dict[str, Any]] = None
    plan: Optional[List[Dict[str, Any]]] = None
    final_report: Optional[Dict[str, Any]] = None
    status: str
    error_msg: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    create_time: Optional[str] = None


class AgentTaskDetailResp(BaseModel):
    """任务完整详情（含步骤和检索）"""
    task: AgentTaskResp
    steps: List[AgentStepResp]
    retrievals: List[Dict[str, Any]]
    checks: List[Dict[str, Any]]


class RetrievalLogResp(BaseModel):
    """检索日志"""
    id: int
    query_text: str
    doc_type_filter: Optional[str] = None
    top_k: int = 5
    result_count: int = 0
    results: List[Dict[str, Any]] = []
