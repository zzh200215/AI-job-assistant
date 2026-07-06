# -*- coding: utf-8 -*-
"""Unified agent registry shared by all orchestration strategies."""
from dataclasses import dataclass, field
from typing import Dict, List, Type


@dataclass
class AgentSpec:
    """Metadata for a registered agent."""

    name: str
    agent_class: Type
    critical: bool = True
    aliases: List[str] = field(default_factory=list)
    strategies: List[str] = field(default_factory=list)


class UnifiedRegistry:
    """Primary-name registry with a separate alias index."""

    def __init__(self):
        self._agents: Dict[str, AgentSpec] = {}
        self._aliases: Dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> "UnifiedRegistry":
        self._agents[spec.name] = spec
        for alias in spec.aliases:
            self._aliases[alias] = spec
        return self

    def get(self, name: str) -> AgentSpec:
        if name in self._agents:
            return self._agents[name]
        if name in self._aliases:
            return self._aliases[name]
        raise KeyError(f"Agent '{name}' is not registered")

    def get_class(self, name: str) -> Type:
        return self.get(name).agent_class

    def is_critical(self, name: str) -> bool:
        return self.get(name).critical

    def list_names(self, strategy: str = None) -> List[str]:
        result = []
        for spec in self._agents.values():
            if strategy is None or strategy in spec.strategies:
                result.append(spec.name)
        return result

    def filter_by_strategy(self, strategy: str) -> List[AgentSpec]:
        result = []
        for spec in self._agents.values():
            if strategy in spec.strategies:
                result.append(spec)
        return result


DEFAULT_REGISTRY = UnifiedRegistry()


def _build_default_registry() -> UnifiedRegistry:
    """Build the default registry lazily to avoid circular imports."""
    reg = UnifiedRegistry()

    from app.agents.intent_agent import IntentAgent
    from app.agents.resume_parse_agent import ResumeParseAgent
    from app.agents.jd_parse_agent import JDParseAgent
    from app.agents.match_analysis_agent import MatchAnalysisAgent
    from app.agents.resume_optimize_agent import ResumeOptimizeAgent
    from app.agents.interview_question_agent import InterviewQuestionAgent
    from app.agents.summary_agent import SummaryAgent

    linear_strategies = ["linear", "langgraph_linear"]
    reg.register(AgentSpec("IntentAgent", IntentAgent, critical=True, strategies=linear_strategies))
    reg.register(AgentSpec("ResumeParseAgent", ResumeParseAgent, critical=True, strategies=linear_strategies))
    reg.register(AgentSpec("JDParseAgent", JDParseAgent, critical=True, strategies=linear_strategies))
    reg.register(AgentSpec("MatchAnalysisAgent", MatchAnalysisAgent, critical=True, strategies=linear_strategies))
    reg.register(AgentSpec("ResumeOptimizeAgent", ResumeOptimizeAgent, critical=True, strategies=linear_strategies))
    reg.register(AgentSpec("InterviewQuestionAgent", InterviewQuestionAgent, critical=True, strategies=linear_strategies))
    reg.register(
        AgentSpec(
            "SummaryAgent",
            SummaryAgent,
            critical=True,
            strategies=[*linear_strategies, "layered", "langgraph_layered"],
        )
    )

    from app.agents.resume_agent import ResumeAgent
    from app.agents.job_agent import JobAgent
    from app.agents.career_agent import CareerAgent
    from app.agents.interview_agent import InterviewAgent
    from app.agents.match_agent import MatchAgent

    reg.register(
        AgentSpec(
            "ResumeAgent",
            ResumeAgent,
            critical=True,
            aliases=["ResumeParseAgent"],
            strategies=["layered", "langgraph_layered"],
        )
    )
    reg.register(
        AgentSpec(
            "JobAgent",
            JobAgent,
            critical=True,
            aliases=["JDParseAgent"],
            strategies=["layered", "langgraph_layered"],
        )
    )
    reg.register(
        AgentSpec(
            "MatchAgent",
            MatchAgent,
            critical=True,
            aliases=["MatchAnalysisAgent"],
            strategies=["layered", "langgraph_layered"],
        )
    )
    reg.register(
        AgentSpec(
            "InterviewAgent",
            InterviewAgent,
            critical=True,
            aliases=["InterviewQuestionAgent"],
            strategies=["layered", "langgraph_layered"],
        )
    )
    reg.register(AgentSpec("CareerAgent", CareerAgent, critical=True, strategies=["layered", "langgraph_layered"]))

    return reg


try:
    DEFAULT_REGISTRY = _build_default_registry()
except Exception:
    DEFAULT_REGISTRY = UnifiedRegistry()
