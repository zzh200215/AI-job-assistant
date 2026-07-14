"""分析相关 Pydantic 模型"""

from typing import Any

from pydantic import BaseModel, Field

# ===================== 匹配度解释器 =====================


class ExplainMatchReq(BaseModel):
    resume_id: int = Field(..., description="简历 ID")
    jd_id: int = Field(..., description="岗位 JD ID")


class ExplainMatchResp(BaseModel):
    overall_score: float
    overall_reason: str
    dimensions: list[dict]
    skill_match: dict
    risk_points: list[str]
    optimization_suggestions: list[str]
    recommendation: str
    weights_used: dict


class MatchReq(BaseModel):
    resume_id: int = Field(..., description="简历 ID")
    jd_id: int = Field(..., description="岗位 JD ID")
    remark: str | None = Field("", description="可选备注")


class FullAnalysisReq(BaseModel):
    """一键智能分析请求"""

    resume_id: int = Field(..., description="简历 ID")
    jd_id: int = Field(..., description="岗位 JD ID")


# ===================== 编排器响应模型 =====================


class AgentStepResult(BaseModel):
    """单个 Agent 步骤结果"""

    agent_name: str = Field(..., description="Agent 名称")
    status: str = Field(..., description="success / failed / skipped")
    result: dict[str, Any] | None = Field(None, description="Agent 输出")
    error: str = Field("", description="失败时的错误信息")


class OrchestratorResult(BaseModel):
    """编排器统一返回格式"""

    status: str = Field(..., description="success / partial / failed")
    task_id: int = Field(..., description="AgentTask ID")
    record_id: int | None = Field(None, description="AnalysisRecord ID")
    steps: list[AgentStepResult] = Field([], description="各步骤结果")
    final_report: dict[str, Any] | None = Field(None, description="最终汇总报告")
    error: str = Field("", description="失败时的错误信息")
