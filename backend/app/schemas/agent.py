"""Agentic RAG Pydantic 请求/响应模型"""

from typing import Any

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
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    error_msg: str | None = None
    retry_count: int = 0


class AgentTaskResp(BaseModel):
    """任务详情响应"""

    id: int
    user_id: int
    resume_id: int
    jd_id: int
    analysis_record_id: int | None = None
    intent: str | None = None
    intent_detail: dict[str, Any] | None = None
    plan: list[dict[str, Any]] | None = None
    final_report: dict[str, Any] | None = None
    status: str
    error_msg: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    create_time: str | None = None


class AgentTaskDetailResp(BaseModel):
    """任务完整详情（含步骤和检索）"""

    task: AgentTaskResp
    steps: list[AgentStepResp]
    retrievals: list[dict[str, Any]]
    checks: list[dict[str, Any]]


class RetrievalLogResp(BaseModel):
    """检索日志"""

    id: int
    query_text: str
    doc_type_filter: str | None = None
    top_k: int = 5
    result_count: int = 0
    results: list[dict[str, Any]] = []
