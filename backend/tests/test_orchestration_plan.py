"""C2（保守版）— 计划真的驱动执行，词汇表真的对上现存节点。

修之前的实测状态：`required_steps` 一路写进 `agent_task.intent_detail` 却没人读，
`_should_execute()` 只看一张硬编码的"意图 → agent"表；而意图提示词里的名单还留着
C4 已删除的 `task_planning` / `knowledge_retrieval` / `self_check`，等于让模型按一份
不存在的词汇表做计划。`agent_task.plan` 也自 C4 起没有任何写入方。
"""

from typing import Any

import pytest

from app.agents.base_agent import BaseAgent
from app.models.agent import AgentStepLog, AgentTask
from app.orchestration.context import AgentContext
from app.orchestration.plan import (
    ALWAYS_RUN_STEPS,
    PLAN_SOURCE_INTENT,
    PLAN_SOURCE_MODEL,
    as_plan_rows,
    plan_from_intent,
)
from app.orchestration.registry import AgentSpec, UnifiedRegistry
from app.orchestration.strategies import LinearStrategy, StrategyFactory
from app.prompts.agent_intent import AGENT_INTENT_PROMPT

# 2026-06 真实落库的一份意图输出（步骤名来自已删除的 step_by_step 词汇表）
STALE_INTENT_DETAIL = {
    "intent": "full_analysis",
    "confidence": 0.95,
    "required_steps": [
        "intent_recognition",
        "resume_parse",
        "jd_parse",
        "task_planning",
        "knowledge_retrieval",
        "matching_analysis",
        "resume_optimization",
        "interview_question_generation",
        "self_check",
        "final_report",
    ],
}

LINEAR_AGENTS = [
    "IntentAgent",
    "ResumeParseAgent",
    "JDParseAgent",
    "MatchAnalysisAgent",
    "ResumeOptimizeAgent",
    "InterviewQuestionAgent",
    "SummaryAgent",
]


# ===================== 计划规约 =====================


def test_deleted_step_names_are_reported_not_silently_dropped():
    """坏词汇表留下的名字必须被点名，不能悄悄丢掉。"""
    plan = plan_from_intent(STALE_INTENT_DETAIL, available_agents=LINEAR_AGENTS)

    assert plan["source"] == PLAN_SOURCE_MODEL
    assert plan["dropped"] == ["knowledge_retrieval", "self_check", "task_planning"]
    # 别名要归一到规范名：matching_analysis → match_analysis
    assert "match_analysis" in plan["steps"]
    assert "interview_questions" in plan["steps"]
    assert "summary_report" in plan["steps"]


def test_always_run_steps_cannot_be_dropped_by_the_model():
    plan = plan_from_intent(
        {"intent": "optimize_only", "required_steps": ["resume_optimization"]}, available_agents=LINEAR_AGENTS
    )

    assert ALWAYS_RUN_STEPS.issubset(set(plan["steps"]))
    assert {"IntentAgent", "ResumeParseAgent", "JDParseAgent"}.issubset(set(plan["agents"]))
    # 没写 match/interview，就不该出现在计划里
    assert "MatchAnalysisAgent" not in plan["agents"]
    assert "InterviewQuestionAgent" not in plan["agents"]


def test_empty_or_unusable_plan_falls_back_to_the_intent_table():
    """模型什么都没说（或只说了不存在的名字）时，行为等同 C2 之前。"""
    for detail in (None, {}, {"intent": "interview_only", "required_steps": []}):
        plan = plan_from_intent(detail, available_agents=LINEAR_AGENTS)
        assert plan["source"] == PLAN_SOURCE_INTENT

    matched = plan_from_intent(
        {"intent": "interview_only", "required_steps": ["made_up_step"]}, available_agents=LINEAR_AGENTS
    )
    assert matched["source"] == PLAN_SOURCE_INTENT
    assert matched["agents"] == [
        "IntentAgent",
        "ResumeParseAgent",
        "JDParseAgent",
        "InterviewQuestionAgent",
        "SummaryAgent",
    ]


def test_execution_order_is_the_pipelines_not_the_models():
    """模型给的顺序不能信：解析节点必须先跑，否则下游读不到上游结果。"""
    plan = plan_from_intent(
        {"intent": "full_analysis", "required_steps": ["summary_report", "interview_questions", "match_analysis"]},
        available_agents=LINEAR_AGENTS,
    )

    assert plan["agents"] == [
        "IntentAgent",
        "ResumeParseAgent",
        "JDParseAgent",
        "MatchAnalysisAgent",
        "InterviewQuestionAgent",
        "SummaryAgent",
    ]
    rows = as_plan_rows(set(plan["steps"]), plan["agents"])
    assert [row["order"] for row in rows] == [1, 2, 3, 4, 5, 6]


def test_confidence_is_never_a_decision_input():
    """真机上它恒等于提示词的示例值 0.95，是抄来的数字，不能拿来裁执行。"""
    high = plan_from_intent(
        {"intent": "optimize_only", "confidence": 0.99, "required_steps": ["resume_optimization"]},
        available_agents=LINEAR_AGENTS,
    )
    low = plan_from_intent(
        {"intent": "optimize_only", "confidence": 0.05, "required_steps": ["resume_optimization"]},
        available_agents=LINEAR_AGENTS,
    )

    assert high["agents"] == low["agents"]


# ===================== 裁剪真的按计划走 =====================


def test_should_execute_prefers_the_plan_over_the_intent_table():
    class _Carrier(LinearStrategy):
        pass

    strategy = _Carrier(UnifiedRegistry())
    context = AgentContext.for_analysis(1, 2, user_id=1)
    context.intent_detail = {"intent": "full_analysis"}
    context.plan = as_plan_rows(
        {"intent_recognition", "resume_parse", "jd_parse", "match_analysis"},
        ["IntentAgent", "ResumeParseAgent", "JDParseAgent", "MatchAnalysisAgent"],
    )

    assert strategy._should_execute(context, "MatchAnalysisAgent") is True
    # 意图说 full_analysis，但计划里没有优化节点——计划赢
    assert strategy._should_execute(context, "ResumeOptimizeAgent") is False


def test_should_execute_falls_back_when_there_is_no_plan():
    strategy = LinearStrategy(UnifiedRegistry())
    context = AgentContext.for_analysis(1, 2, user_id=1)
    context.intent_detail = {"intent": "optimize_only"}

    assert strategy._should_execute(context, "ResumeOptimizeAgent") is True
    assert strategy._should_execute(context, "MatchAnalysisAgent") is False


# ===================== 端到端：计划落库 =====================


class _IntentOnly(BaseAgent):
    name = "IntentAgent"
    result_type = "intent"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        return {
            "intent": "optimize_only",
            "confidence": 0.95,
            "required_steps": ["resume_optimization", "summary_report"],
        }


class _Noop(BaseAgent):
    result_type = "noop"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        return {"ok": True}


@pytest.fixture
def plan_registry() -> UnifiedRegistry:
    reg = UnifiedRegistry()
    for name in LINEAR_AGENTS:
        cls = _IntentOnly if name == "IntentAgent" else type(f"Mock{name}", (_Noop,), {"name": name})
        reg.register(AgentSpec(name, cls, strategies=["linear", "langgraph_linear"]))
    return reg


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    import app.agents.base_agent as base_agent

    monkeypatch.setattr(base_agent, "RETRY_BACKOFF_SECONDS", 0)


@pytest.mark.parametrize("strategy_name", ["linear", "langgraph_linear"])
def test_run_persists_a_plan_that_matches_the_executed_nodes(strategy_name, db_session, plan_registry):
    task = AgentTask(user_id=1, resume_id=1, jd_id=1, status="pending")
    db_session.add(task)
    db_session.commit()

    result = StrategyFactory.create(strategy_name, plan_registry).run(task.id, 1, 1, 1, db_session)

    db_session.refresh(task)
    assert result["status"] == "completed"
    planned = [row["agent"] for row in task.plan]
    assert planned == ["IntentAgent", "ResumeParseAgent", "JDParseAgent", "ResumeOptimizeAgent", "SummaryAgent"]

    ran = {log.step_name: log.status for log in db_session.query(AgentStepLog).filter_by(task_id=task.id).all()}
    for agent in planned:
        assert ran[agent] == "completed", f"{agent} 在计划里却没有执行"
    for agent in set(LINEAR_AGENTS) - set(planned):
        assert ran[agent] == "skipped", f"{agent} 不在计划里却跑了"


def test_prompt_vocabulary_no_longer_names_deleted_steps():
    """提示词不能再教模型点名 C4 删掉的步骤。"""
    forbidden = ("task_planning", "knowledge_retrieval", "self_check", "final_report", "matching_analysis")
    assert not [name for name in forbidden if name in AGENT_INTENT_PROMPT]


# ===================== C7：注册表不许再把不同职责的类当成同一个 =====================


def test_registry_has_no_cross_pipeline_aliases():
    """`ResumeAgent`(调模型的诊断报告) 与 `ResumeParseAgent`(纯规则解析，0 token)
    不是同一件事；曾经注册表用别名把它们缝在一起，按别名解析出来的对象会带着自己的
    name 落库，步骤日志与节点消息就对不上了。"""
    from app.agents.resume_agent import ResumeAgent
    from app.agents.resume_parse_agent import ResumeParseAgent
    from app.orchestration.registry import DEFAULT_REGISTRY

    assert DEFAULT_REGISTRY.get("ResumeParseAgent").agent_class is ResumeParseAgent
    assert DEFAULT_REGISTRY.get("ResumeAgent").agent_class is ResumeAgent
    assert not hasattr(DEFAULT_REGISTRY, "_aliases")


def test_unknown_agent_fails_loudly_with_the_known_list():
    from app.orchestration.registry import DEFAULT_REGISTRY

    with pytest.raises(KeyError, match="not registered"):
        DEFAULT_REGISTRY.get("ResumeParse")
