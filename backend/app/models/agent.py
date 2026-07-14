"""Agentic RAG 工作流 ORM 模型"""

from sqlalchemy import JSON, BigInteger, Column, DateTime, Float, ForeignKey, Integer, SmallInteger, String, Text

from app.core.database import Base
from app.orchestration.protocol import (
    get_step_label,
    get_step_output_schema,
    normalize_step_name,
    normalize_step_status,
    normalize_task_status,
)
from app.utils.time_helper import utc_now


class AgentTask(Base):
    """Agent 任务表"""

    __tablename__ = "agent_task"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    resume_id = Column(BigInteger, nullable=False, comment="关联简历ID")
    jd_id = Column(BigInteger, nullable=False, comment="关联JDID")
    analysis_record_id = Column(BigInteger, comment="关联分析记录ID")
    strategy_name = Column(String(50), comment="执行策略名称")
    retry_of_task_id = Column(BigInteger, comment="重试来源任务ID")
    intent = Column(String(100), comment="用户意图")
    intent_detail = Column(JSON, comment="意图识别详情")
    plan = Column(JSON, comment="任务规划")
    final_report = Column(JSON, comment="最终报告")
    status = Column(String(20), nullable=False, default="pending", comment="状态: pending/running/completed/failed")
    error_msg = Column(Text, comment="失败原因")
    start_time = Column(DateTime, comment="开始时间")
    end_time = Column(DateTime, comment="结束时间")
    create_time = Column(DateTime, default=utc_now, comment="创建时间")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "analysis_record_id": self.analysis_record_id,
            "strategy_name": self.strategy_name,
            "retry_of_task_id": self.retry_of_task_id,
            "intent": self.intent,
            "intent_detail": self.intent_detail or {},
            "plan": self.plan or [],
            "final_report": self.final_report or {},
            "status": normalize_task_status(self.status),
            "raw_status": self.status,
            "protocol_version": "analysis-task.v1",
            "error_msg": self.error_msg,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }


class AgentStepLog(Base):
    """Agent 步骤日志表"""

    __tablename__ = "agent_step_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("agent_task.id", ondelete="CASCADE"), nullable=False)
    step_name = Column(String(100), nullable=False, comment="步骤名称")
    step_index = Column(Integer, nullable=False, comment="步骤序号")
    status = Column(String(20), nullable=False, default="pending", comment="状态: pending/running/completed/failed")
    input_data = Column(JSON, comment="步骤输入")
    output_data = Column(JSON, comment="步骤输出")
    started_at = Column(DateTime, comment="步骤开始时间")
    completed_at = Column(DateTime, comment="步骤完成时间")
    duration_ms = Column(Integer, comment="耗时(毫秒)")
    error_msg = Column(Text, comment="失败原因")
    retry_count = Column(Integer, default=0, comment="重试次数")
    create_time = Column(DateTime, default=utc_now)

    def to_dict(self):
        canonical_step_name = normalize_step_name(self.step_name)
        return {
            "id": self.id,
            "task_id": self.task_id,
            "step_name": canonical_step_name,
            "raw_step_name": self.step_name,
            "step_label": get_step_label(canonical_step_name),
            "output_schema": get_step_output_schema(canonical_step_name),
            "step_index": self.step_index,
            "status": normalize_step_status(self.status),
            "raw_status": self.status,
            "protocol_version": "analysis-step.v1",
            "input_data": self.input_data or {},
            "output_data": self.output_data or {},
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
            "error_msg": self.error_msg,
            "retry_count": self.retry_count,
        }


class RetrievalLog(Base):
    """知识检索日志表"""

    __tablename__ = "retrieval_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("agent_task.id", ondelete="CASCADE"), nullable=False)
    step_log_id = Column(BigInteger, nullable=True)
    query_text = Column(Text, nullable=False, comment="检索查询")
    doc_type_filter = Column(String(50), comment="文档类型过滤")
    top_k = Column(Integer, default=5)
    result_count = Column(Integer, default=0)
    results = Column(JSON, comment="检索结果")
    duration_ms = Column(Integer, comment="耗时(毫秒)")
    create_time = Column(DateTime, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "step_log_id": self.step_log_id,
            "query_text": self.query_text,
            "doc_type_filter": self.doc_type_filter,
            "top_k": self.top_k,
            "result_count": self.result_count,
            "results": self.results or [],
            "duration_ms": self.duration_ms,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }


class SelfCheckLog(Base):
    """自我校验日志表"""

    __tablename__ = "self_check_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("agent_task.id", ondelete="CASCADE"), nullable=False)
    check_target = Column(String(100), comment="校验目标")
    passed = Column(SmallInteger, default=0, comment="是否通过: 0/1")
    score = Column(Float, comment="得分")
    issues = Column(JSON, comment="问题列表")
    improvement = Column(JSON, comment="改进建议")
    retry_needed = Column(SmallInteger, default=0, comment="是否需要重试: 0/1")
    create_time = Column(DateTime, default=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "check_target": self.check_target,
            "passed": self.passed,
            "score": self.score,
            "issues": self.issues or [],
            "improvement": self.improvement or {},
            "retry_needed": self.retry_needed,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }
