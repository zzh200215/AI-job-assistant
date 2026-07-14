"""多智能体协作 Pydantic 模型"""

from typing import Any

from pydantic import BaseModel, Field


class MultiAgentStartReq(BaseModel):
    resume_id: int = Field(..., description="简历 ID")
    jd_id: int = Field(..., description="岗位 JD ID")


class AutoStartReq(BaseModel):
    """智能调度入口：自然语言需求驱动，简历/JD 可不填（自动取最近一次）"""

    user_request: str = Field("", description="用户自然语言需求")
    resume_id: int | None = Field(None, description="简历 ID，可选；缺省取最近一次")
    jd_id: int | None = Field(None, description="岗位 JD ID，可选；缺省取最近一次")


class AgentMessageResp(BaseModel):
    id: int
    run_id: int
    agent_name: str
    status: str
    depends_on: list[str] = []
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error_msg: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    tokens_used: int = 0
    cost_cents: float = 0.0


class AgentRunResp(BaseModel):
    id: int
    resume_id: int
    jd_id: int
    status: str
    summary_report: dict[str, Any] = {}
    error_msg: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    create_time: str | None = None


class MultiAgentDetailResp(BaseModel):
    run: AgentRunResp
    messages: list[AgentMessageResp]
    results: list[dict[str, Any]]
