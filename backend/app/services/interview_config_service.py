"""面试配置服务层（T3-2）：题库/评分规则的覆盖与回落。

2026-10-06 真删企业侧第六增量（D136，§10.32 他点「整族拆到底」）之前这里是**三级**回落：
租户自定义 → 平台默认（`tenant_id IS NULL`）→ 内置常量。租户那一级随 organization 一起出树，
现在只剩**两级**：平台配置 → 内置常量。列与模型保留（`tenant_id` 仍在那三张表里），
但没有任何读写侧按它分区了。

同批删掉的 `PUT /admin/interview-config` 是这三张表**唯一的写入端**，且它要求请求体带
`tenant_id`，所以历史上它能造的只有"租户级"行——也就是说平台级那一今天然是空的（dev 实测三张表
各 0 行），要填只能靠脚本/SQL 直接写 `tenant_id IS NULL` 的行。`InterviewReportTemplate` 与
`get_report_template` 一起删掉：前者是那张表的模型，后者**在生产里从来没有调用方**，
所以"租户自定义报告模板"这句话从没落到过屏幕上。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.interview_config import (
    InterviewQuestionBank,
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


def get_question_bank(db: Session, bank_type: str) -> InterviewQuestionBank | None:
    """平台题库配置（`tenant_id IS NULL`）；没有就返回 None，由调用方回落内置常量。"""
    return (
        db.query(InterviewQuestionBank)
        .filter(
            InterviewQuestionBank.type == bank_type,
            InterviewQuestionBank.is_active == 1,
            InterviewQuestionBank.tenant_id.is_(None),
        )
        .first()
    )


def list_question_banks(db: Session) -> list[dict[str, Any]]:
    """全部题型配置（供前端设置页）：平台行覆盖内置五档。"""
    platform = {
        row.type: row
        for row in db.query(InterviewQuestionBank)
        .filter(InterviewQuestionBank.is_active == 1, InterviewQuestionBank.tenant_id.is_(None))
        .all()
    }

    banks: list[dict[str, Any]] = []
    for bank_type, default in DEFAULT_QUESTION_BANKS.items():
        row = platform.get(bank_type)
        if row is None:
            banks.append(
                {
                    "type": bank_type,
                    "title": default["title"],
                    "persona": default["persona"],
                    "description": default["description"],
                    "focus": default["focus"],
                    "tags": [],
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
            }
        )
    return banks


def get_scoring_rules(db: Session) -> list[dict[str, Any]]:
    """平台评分规则（`tenant_id IS NULL`）；没有就回落内置常量。"""
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


def scoring_rule_map(db: Session) -> dict[str, float]:
    """dimension → weight 映射，供报告总分加权计算。"""
    return {rule["dimension"]: rule["weight"] for rule in get_scoring_rules(db)}


# ==================== 每题作答预算（P1.2）====================

# 题型的中文显示名。**这里是这份词表的唯一出处**：`interview_rest._map_category` 与引擎的
# 题型回推都读它。它原先在 api 层内联写了一遍，两处一旦漂开，出题侧写的标签和读题侧回推的
# 标签就对不上——那正下面那条"一词两域"的成因。
QUESTION_TYPE_LABELS: dict[str, str] = {
    "basic": "通用/HR",
    "tech": "技术基础",
    "project": "项目经验",
    "scenario": "场景应对",
}

# 文档 §4 P1.2 那张表：basic 45 / tech 120 / scenario 90 / project 120。
# 改任何一个数都要同时改那份文档，`test_interview_timeout_per_type` 逐字比着这四个值。
QUESTION_TIMEOUT_SECONDS: dict[str, int] = {
    "basic": 45,
    "tech": 120,
    "scenario": 90,
    "project": 120,
}

# 认不出题型时的**下限**。原来全场都是 30 秒，而 30 就是"系统设计题根本答不完"那条硬伤的根因，
# 所以认不出时不该继续发 30——发下限 45 秒，与最轻的那一档齐平。
TIMEOUT_FLOOR_SECONDS = 45

# 一场面试的题量：默认 10，允许 1–20。生成链、引擎上限与设置页展示都读这个函数，
# 不让任何一侧再抄一个 10。
MAX_QUESTIONS_DEFAULT = 10
MAX_QUESTIONS_FLOOR = 1
MAX_QUESTIONS_CEILING = 20


def max_questions() -> int:
    raw = getattr(settings, "INTERVIEW_MAX_QUESTIONS", MAX_QUESTIONS_DEFAULT)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = MAX_QUESTIONS_DEFAULT
    return max(MAX_QUESTIONS_FLOOR, min(MAX_QUESTIONS_CEILING, value))


# 词表的坑，实现时量出来的，别当透明：这张表按**运行时题型**索引（basic/tech/scenario/project，
# 就是 starter 模板与 `_map_category` 实际在用的那套），而 `interview_question_bank.type`
# 自己的定义与 `DEFAULT_QUESTION_BANKS` 用的是另一套（tech/hr/comprehensive/stress/group）。
# **两套的交集只有 "tech"**。今天 `interview_question_bank` 是 0 行所以不冲突；
# 真要在管理端配超时，得先把这两套词表对齐，否则配下去的行永远查不中、静默走内置默认。
TYPE_VOCABULARY_MISMATCH = (
    "运行时题型 {basic,tech,project,scenario} 与配置层题型 "
    "{tech,hr,comprehensive,stress,group} 只交集于 tech；对齐之前不要按配置层那套填超时行"
)


def timeout_for_type(db: Session | None, qtype: str) -> int:
    """题型 → 这一题的作答秒数。两级回落，与 `get_scoring_rules` 同形：
    平台配置行（`tenant_id IS NULL` 且启用）→ 内置默认表 → 认不出时的下限 45。

    行存在但 `timeout_seconds` 是 NULL 或 0 时**按该题型的内置默认**回落，不是全局下限——
    "这一题型配了、只是没配超时"与"这题型压根没配"是两件事，都该拿到自己那一档的默认值。
    """
    default = QUESTION_TIMEOUT_SECONDS.get(qtype, TIMEOUT_FLOOR_SECONDS)
    if db is None or not qtype:
        return default
    row = (
        db.query(InterviewQuestionBank)
        .filter(
            InterviewQuestionBank.is_active == 1,
            InterviewQuestionBank.tenant_id.is_(None),
            InterviewQuestionBank.type == qtype,
        )
        .first()
    )
    if row is not None and row.timeout_seconds:
        return int(row.timeout_seconds)
    return default
