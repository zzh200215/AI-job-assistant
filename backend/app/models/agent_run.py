"""多智能体协作 ORM 模型"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class AgentRun(Base):
    """多智能体运行记录"""

    __tablename__ = "agent_run"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, index=True, comment="归属的编排任务 agent_task.id")
    resume_id = Column(BigInteger, nullable=False, comment="关联简历ID")
    jd_id = Column(BigInteger, nullable=False, comment="关联JDID")
    user_request = Column(Text, comment="用户自然语言需求（智能调度入口）")
    intent = Column(String(50), comment="调度识别出的意图")
    selected_agents = Column(JSON, comment="本次实际调用的智能体列表")
    dispatch_reason = Column(Text, comment="调度理由")
    status = Column(String(20), nullable=False, default="pending", comment="状态: pending/running/completed/failed")
    summary_report = Column(JSON, comment="汇总报告")
    error_msg = Column(Text, comment="失败原因")
    start_time = Column(DateTime, comment="开始时间")
    end_time = Column(DateTime, comment="结束时间")
    create_time = Column(DateTime, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "user_request": self.user_request,
            "intent": self.intent,
            "selected_agents": self.selected_agents or [],
            "dispatch_reason": self.dispatch_reason,
            "status": self.status,
            "summary_report": self.summary_report or {},
            "error_msg": self.error_msg,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }


class AgentMessage(Base):
    """智能体消息（每个智能体每次执行）"""

    __tablename__ = "agent_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(String(50), nullable=False, comment="智能体名称")
    status = Column(String(20), nullable=False, default="pending", comment="状态: pending/running/completed/failed")
    depends_on = Column(JSON, comment="依赖列表")
    input_data = Column(JSON, comment="输入")
    output_data = Column(JSON, comment="输出")
    error_msg = Column(Text, comment="错误")
    started_at = Column(DateTime, comment="开始时间")
    completed_at = Column(DateTime, comment="完成时间")
    duration_ms = Column(Integer, comment="耗时ms")
    tokens_used = Column(Integer, default=0, comment="LLM token 用量")
    cost_cents = Column(Float, default=0.0, comment="LLM 成本（美分）")
    create_time = Column(DateTime, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "status": self.status,
            "depends_on": self.depends_on or [],
            "input_data": self.input_data or {},
            "output_data": self.output_data or {},
            "error_msg": self.error_msg,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "tokens_used": self.tokens_used or 0,
            "cost_cents": round(float(self.cost_cents or 0.0), 6),
        }


class AgentResult(Base):
    """智能体结果"""

    __tablename__ = "agent_result"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(BigInteger, nullable=True)
    agent_name = Column(String(50), nullable=False)
    result_type = Column(String(50), nullable=False)
    result_json = Column(JSON, nullable=False)
    summary = Column(String(500))
    create_time = Column(DateTime, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "result_type": self.result_type,
            "result_json": self.result_json or {},
            "summary": self.summary,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }
