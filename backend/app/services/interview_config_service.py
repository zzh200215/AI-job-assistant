"""面试配置服务层（T3-2）：题库/评分规则/报告模板按租户覆盖与回落。

租户约定（与 T3-1 一致）：
- 租户自定义（tenant_id=当前租户 且 is_active）优先；
- 未配置时回落平台默认（tenant_id IS NULL），仍无则回落内置常量。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.interview_config import (
    InterviewQuestionBank,
    InterviewReportTemplate,
    InterviewScoringRule,
)

# 内置默认评分规则（与 interview_engine._generate_report 的历史权重一致）
DEFAULT_SCORING_RULES: list[dict[str, Any]] = [
    {"dimension": "completeness", "label": "完整性", "weight": 0.30},
    {"dimension": "accuracy", "label": "准确性", "weight": 0.30},
    {"dimension": "depth", "label": "深度", "weight": 0.25},
    {"dimension": "expression", "label": "表达", "weight": 0.15},
]

# 内置默认题型配置（前端 typeOptions 的等价结构，供 GET /config/types 回落）
DEFAULT_QUESTION_BANKS: dict[str, dict[str, Any]] = {
    "tech": {
        "title": "技术深挖",
        "persona": "像一位会持续追问的技术面试官",
        "description": "优先检查技术基本功、系统理解、项目细节和设计取舍。",
        "focus": ["原理解释", "项目拆解", "设计权衡", "追问细节"],
    },
    "hr": {
        "title": "HR / 行为面",
        "persona": "像一位关注动机与表达的招聘经理",
        "description": "更看重表达、动机、协作方式、成长性与稳定性。",
        "focus": ["职业动机", "沟通表达", "冲突处理", "稳定性判断"],
    },
    "comprehensive": {
        "title": "综合面试",
        "persona": "像一位全流程面试官",
        "description": "技术、项目、行为与场景题混合，更接近真实面试组合拳。",
        "focus": ["技术基础", "项目贡献", "行为案例", "场景判断"],
    },
    "stress": {
        "title": "压力面试",
        "persona": "像一位会不断质疑和打断的面试官",
        "description": "持续追问、挑战你的回答，考察你在压力环境下的思维逻辑和情绪控制能力。",
        "focus": ["快速追问", "打断再问", "极限场景", "抗压能力"],
    },
    "group": {
        "title": "群面模拟",
        "persona": "像一位观察多个候选人的面试官",
        "description": "模拟无领导小组讨论场景，评估你的团队角色、协作方式和影响力。",
        "focus": ["团队角色", "观点输出", "协调能力", "总结能力"],
    },
}


def get_question_bank(db: Session, tenant_id: int, bank_type: str) -> InterviewQuestionBank | None:
    """获取租户可见的题库配置：租户自定义 → 平台默认 → None（回落内置）。"""
    row = (
        db.query(InterviewQuestionBank)
        .filter(
            InterviewQuestionBank.type == bank_type,
            InterviewQuestionBank.is_active == 1,
            InterviewQuestionBank.tenant_id == tenant_id,
        )
        .first()
    )
    if row is not None:
        return row
    return (
        db.query(InterviewQuestionBank)
        .filter(
            InterviewQuestionBank.type == bank_type,
            InterviewQuestionBank.is_active == 1,
            InterviewQuestionBank.tenant_id.is_(None),
        )
        .first()
    )


def list_question_banks(db: Session, tenant_id: int) -> list[dict[str, Any]]:
    """租户可见的全部题型配置（供前端设置页），合并租户/平台/内置三级。"""
    custom = {
        row.type: row
        for row in db.query(InterviewQuestionBank)
        .filter(InterviewQuestionBank.is_active == 1, InterviewQuestionBank.tenant_id == tenant_id)
        .all()
    }
    platform = {
        row.type: row
        for row in db.query(InterviewQuestionBank)
        .filter(InterviewQuestionBank.is_active == 1, InterviewQuestionBank.tenant_id.is_(None))
        .all()
    }

    banks: list[dict[str, Any]] = []
    for bank_type, default in DEFAULT_QUESTION_BANKS.items():
        row = custom.get(bank_type) or platform.get(bank_type)
        if row is None:
            banks.append(
                {
                    "type": bank_type,
                    "title": default["title"],
                    "persona": default["persona"],
                    "description": default["description"],
                    "focus": default["focus"],
                    "tags": [],
                    "is_custom": False,
                }
            )
            continue
        banks.append(
            {
                "type": row.type,
                "title": row.title or default["title"],
                "persona": default["persona"],
                "description": default["description"],
                "focus": default["focus"],
                "tags": row.tags or [],
                "prompt_template": row.prompt_template or "",
                "is_custom": row.tenant_id is not None,
            }
        )
    return banks


def get_scoring_rules(db: Session, tenant_id: int) -> list[dict[str, Any]]:
    """获取租户可见评分规则：租户自定义 → 平台默认 → 内置常量。"""
    rows = (
        db.query(InterviewScoringRule)
        .filter(InterviewScoringRule.is_active == 1, InterviewScoringRule.tenant_id == tenant_id)
        .order_by(InterviewScoringRule.sort_order, InterviewScoringRule.id)
        .all()
    )
    if not rows:
        rows = (
            db.query(InterviewScoringRule)
            .filter(InterviewScoringRule.is_active == 1, InterviewScoringRule.tenant_id.is_(None))
            .order_by(InterviewScoringRule.sort_order, InterviewScoringRule.id)
            .all()
        )
    if not rows:
        return [dict(rule) for rule in DEFAULT_SCORING_RULES]

    return [
        {
            "dimension": row.dimension,
            "label": row.label or row.dimension,
            "weight": float(row.weight or 0),
        }
        for row in rows
    ]


def scoring_rule_map(db: Session, tenant_id: int) -> dict[str, float]:
    """dimension → weight 映射，供报告总分加权计算。"""
    return {rule["dimension"]: rule["weight"] for rule in get_scoring_rules(db, tenant_id)}


def get_report_template(db: Session, tenant_id: int) -> str | None:
    """获取租户可见报告模板：租户自定义 → 平台默认 → None（回落内置）。"""
    row = (
        db.query(InterviewReportTemplate)
        .filter(InterviewReportTemplate.is_active == 1, InterviewReportTemplate.tenant_id == tenant_id)
        .first()
    )
    if row is not None:
        return row.template
    row = (
        db.query(InterviewReportTemplate)
        .filter(InterviewReportTemplate.is_active == 1, InterviewReportTemplate.tenant_id.is_(None))
        .first()
    )
    return row.template if row is not None else None
