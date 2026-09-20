"""面试配置 ORM 模型（T3-2：题型/评分/报告模板按租户配置化）。

租户约定（与 T3-1 一致）：tenant_id=NULL 表示平台默认配置；
租户自定义行覆盖对应类型/维度的平台默认，未配置时回落内置默认。
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Column, DateTime, Index, Integer, Numeric, String, Text

from app.core.database import Base
from app.utils.time_helper import utc_now


class InterviewQuestionBank(Base):
    """面试题库配置：题型级（tech/hr/comprehensive 等）模板。

    - prompt_template：LLM 个性化生成时的提示词（覆盖内置 type_instructions）；
    - questions：可选静态题列表，格式 [{type, question, intent, ref_answer}]，
      配置后覆盖内置 starter 题库（离线/mock 环境同样生效）；
    - tags：题型标签（前端展示用）。
    """

    __tablename__ = "interview_question_bank"
    __table_args__ = (Index("uq_interview_question_bank_tenant_type", "tenant_id", "type", unique=True),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    type = Column(String(30), nullable=False, comment="题型: tech/hr/comprehensive/stress/group")
    title = Column(String(100), default="", comment="题型展示名称")
    prompt_template = Column(Text, default="", comment="个性化生成提示词（覆盖内置指令）")
    questions = Column(JSON, nullable=True, comment="静态题列表 [{type,question,intent,ref_answer}]，NULL=回落内置题库")
    tags = Column(JSON, default=list, comment="标签列表")
    tenant_id = Column(
        BigInteger,
        nullable=True,
        index=True,
        comment="归属租户 organization.id；NULL=平台默认题库（T3-2）",
    )
    is_active = Column(Integer, default=1, comment="是否启用")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class InterviewScoringRule(Base):
    """面试评分规则：维度 + 权重（租户可配置）。

    dimension 限内置四个评分维度（completeness/accuracy/depth/expression），
    与 InterviewTurnEvaluation 存储列保持一致；label 与 weight 可租户化。
    """

    __tablename__ = "interview_scoring_rule"
    __table_args__ = (Index("uq_interview_scoring_rule_tenant_dim", "tenant_id", "dimension", unique=True),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dimension = Column(String(30), nullable=False, comment="维度 key: completeness/accuracy/depth/expression")
    label = Column(String(50), default="", comment="维度展示名")
    weight = Column(Numeric(5, 4), default=0.25, comment="权重（合计应=1）")
    tenant_id = Column(
        BigInteger,
        nullable=True,
        index=True,
        comment="归属租户 organization.id；NULL=平台默认评分规则（T3-2）",
    )
    is_active = Column(Integer, default=1, comment="是否启用")
    sort_order = Column(Integer, default=0, comment="排序")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class InterviewReportTemplate(Base):
    """面试报告模板（租户可配置，Markdown 模板文本）。"""

    __tablename__ = "interview_report_template"
    __table_args__ = (Index("uq_interview_report_template_tenant", "tenant_id", unique=True),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    template = Column(Text, nullable=False, default="", comment="报告模板（Markdown）")
    tenant_id = Column(
        BigInteger,
        nullable=True,
        index=True,
        comment="归属租户 organization.id；NULL=平台默认模板（T3-2）",
    )
    is_active = Column(Integer, default=1, comment="是否启用")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
