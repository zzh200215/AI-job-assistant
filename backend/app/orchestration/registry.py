"""Unified agent registry shared by all orchestration strategies.

这里不再有"别名"：曾经 `ResumeAgent` 别名挂着 `ResumeParseAgent`、`JobAgent` 挂着
`JDParseAgent`，可它们根本不是同一件事——前者是调模型出的诊断报告，后者是纯规则解析
（0 token）。别名让两个不同职责的类看起来可以互换，而按别名解析出来的对象会带着自己
的 `name` 落库，步骤日志与节点消息就会对不上。两条流水线各自用自己的名字，别名的唯一
作用是埋雷。
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentSpec:
    """Metadata for a registered agent."""

    name: str
    agent_class: type
    critical: bool = True
    strategies: list[str] = field(default_factory=list)


class UnifiedRegistry:
    """Primary-name registry; an unknown name is an error, not a guess."""

    def __init__(self):
        self._agents: dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> "UnifiedRegistry":
        self._agents[spec.name] = spec
        return self

    def get(self, name: str) -> AgentSpec:
        spec = self._agents.get(name)
        if spec is None:
            raise KeyError(f"Agent '{name}' is not registered; known: {sorted(self._agents)}")
        return spec

    def get_class(self, name: str) -> type:
        return self.get(name).agent_class

    def is_critical(self, name: str) -> bool:
        return self.get(name).critical

    def list_names(self, strategy: str = None) -> list[str]:
        result = []
        for spec in self._agents.values():
            if strategy is None or strategy in spec.strategies:
                result.append(spec.name)
        return result

    def filter_by_strategy(self, strategy: str) -> list[AgentSpec]:
        return [spec for spec in self._agents.values() if strategy in spec.strategies]


DEFAULT_REGISTRY = UnifiedRegistry()


def _build_default_registry() -> UnifiedRegistry:
    """Build the default registry lazily to avoid circular imports."""
    reg = UnifiedRegistry()

    from app.agents.intent_agent import IntentAgent
    from app.agents.interview_question_agent import InterviewQuestionAgent
    from app.agents.jd_parse_agent import JDParseAgent
    from app.agents.match_analysis_agent import MatchAnalysisAgent
    from app.agents.resume_optimize_agent import ResumeOptimizeAgent
    from app.agents.resume_parse_agent import ResumeParseAgent
    from app.agents.summary_agent import SummaryAgent

    linear = ["linear", "langgraph_linear"]
    layered = ["layered", "langgraph_layered"]

    for name, cls in (
        ("IntentAgent", IntentAgent),
        ("ResumeParseAgent", ResumeParseAgent),
        ("JDParseAgent", JDParseAgent),
        ("MatchAnalysisAgent", MatchAnalysisAgent),
        ("ResumeOptimizeAgent", ResumeOptimizeAgent),
        ("InterviewQuestionAgent", InterviewQuestionAgent),
    ):
        reg.register(AgentSpec(name, cls, strategies=linear))

    # 汇总节点两条流水线都用
    reg.register(AgentSpec("SummaryAgent", SummaryAgent, strategies=[*linear, *layered]))

    from app.agents.career_agent import CareerAgent
    from app.agents.interview_agent import InterviewAgent
    from app.agents.job_agent import JobAgent
    from app.agents.match_agent import MatchAgent
    from app.agents.resume_agent import ResumeAgent

    for name, cls in (
        ("ResumeAgent", ResumeAgent),
        ("JobAgent", JobAgent),
        ("MatchAgent", MatchAgent),
        ("InterviewAgent", InterviewAgent),
        ("CareerAgent", CareerAgent),
    ):
        reg.register(AgentSpec(name, cls, strategies=layered))

    return reg


try:
    DEFAULT_REGISTRY = _build_default_registry()
except Exception:
    # 注册表建不起来时给一个空表，等于让每次编排都以"Agent 未注册"失败，
    # 而真正的 import 错误被吞在这里 —— 至少要留在日志里。
    logger.exception("默认 Agent 注册表构建失败，编排将以未注册报错")
    DEFAULT_REGISTRY = UnifiedRegistry()
