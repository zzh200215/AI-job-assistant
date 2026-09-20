"""统一智能分析编排器（主线 — 线性流水线策略）

.. note::
    本模块现为 orchestration.strategies.LinearStrategy 的薄包装，
    保留原有 API 入口 `run_orchestrator_sync` 以兼容现有调用方。
    新增策略支持：可通过 analysis_service 配置切换为 layered，或把引擎切到 langgraph。
"""

import traceback
from typing import Any

# ===================== 向后兼容：Agent 注册表 =====================
# 旧代码直接 import AGENT_REGISTRY 时仍可用，但内部已走 DEFAULT_REGISTRY
from app.agents.intent_agent import IntentAgent
from app.agents.interview_question_agent import InterviewQuestionAgent
from app.agents.jd_parse_agent import JDParseAgent
from app.agents.match_analysis_agent import MatchAnalysisAgent
from app.agents.resume_optimize_agent import ResumeOptimizeAgent
from app.agents.resume_parse_agent import ResumeParseAgent
from app.agents.summary_agent import SummaryAgent
from app.core.database import SessionLocal
from app.models.agent import AgentTask
from app.orchestration.registry import DEFAULT_REGISTRY
from app.orchestration.strategies import LinearStrategy, _orchestrator_result
from app.utils.time_helper import utc_now

AGENT_REGISTRY = [
    ("IntentAgent", IntentAgent, True),
    ("ResumeParseAgent", ResumeParseAgent, True),
    ("JDParseAgent", JDParseAgent, True),
    ("MatchAnalysisAgent", MatchAnalysisAgent, True),
    ("ResumeOptimizeAgent", ResumeOptimizeAgent, True),
    ("InterviewQuestionAgent", InterviewQuestionAgent, True),
    ("SummaryAgent", SummaryAgent, True),
]

# 策略实例（复用）
_strategy: LinearStrategy | None = None


def _get_strategy() -> LinearStrategy:
    global _strategy
    if _strategy is None:
        _strategy = LinearStrategy(DEFAULT_REGISTRY)
    return _strategy


# ===================== 核心编排入口 =====================


def run_orchestrator_sync(
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: int = None,
) -> dict[str, Any]:
    """同步执行线性编排流程（后台线程中调用）

    内部委托给 orchestration.strategies.LinearStrategy.run，
    保持返回格式与旧版本完全一致。
    """
    db = SessionLocal()
    try:
        strategy = _get_strategy()
        return strategy.run(task_id, resume_id, jd_id, user_id, db)
    except Exception as e:
        traceback.print_exc()
        try:
            task = db.get(AgentTask, task_id)
            if task:
                task.status = "failed"
                task.error_msg = str(e)
                task.end_time = utc_now()
                db.add(task)
                db.commit()
        except Exception:
            pass
        return _orchestrator_result("failed", task_id, error=str(e))
    finally:
        db.close()
