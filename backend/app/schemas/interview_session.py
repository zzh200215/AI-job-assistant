"""面试会话 Pydantic Schemas"""

from pydantic import BaseModel, Field


class InterviewSessionCreate(BaseModel):
    resume_id: int
    jd_id: int
    interview_type: str = "tech"  # tech / hr / comprehensive


class InterviewSessionResp(BaseModel):
    id: int
    resume_id: int | None
    jd_id: int | None
    interview_type: str
    status: str
    total_questions: int
    answered_count: int
    timeout_count: int
    created_at: str | None
    completed_at: str | None

    questions: list = []
    messages: list = []
    evaluation: dict = {}


class EvaluationDimension(BaseModel):
    completeness: int = Field(ge=0, le=100)
    accuracy: int = Field(ge=0, le=100)
    depth: int = Field(ge=0, le=100)
    expression: int = Field(ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)


class QuestionEvaluation(BaseModel):
    question_index: int
    question: str
    category: str
    completeness: int
    accuracy: int
    depth: int
    expression: int
    overall_score: int
    feedback: str
    improvement: str
    user_answer: str


class InterviewReport(BaseModel):
    """完整面试报告"""

    overall_score: int
    dimension_scores: dict
    radar: dict  # completeness/accuracy/depth/expression
    question_evaluations: list[QuestionEvaluation]
    strengths: list[str]
    weaknesses: list[str]
    improvement_suggestions: list[str]
    total_questions: int
    answered_questions: int
    total_duration_seconds: int
    interview_type: str


# ===== WebSocket 消息协议 =====
class WSMessage(BaseModel):
    type: str  # question / answer / evaluation / system / end / ping / pong
    content: str = ""
    metadata: dict = Field(default_factory=dict)
