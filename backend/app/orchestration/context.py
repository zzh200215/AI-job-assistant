"""Structured agent context shared across orchestration strategies."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields
from typing import Any

from sqlalchemy.orm import Session

_AGENT_RESULT_FIELD_MAP = {
    "IntentAgent": "intent_detail",
    "ResumeParseAgent": "resume_parsed",
    "JDParseAgent": "jd_parsed",
    "MatchAnalysisAgent": "match_result",
    "MatchAgent": "match_result",
    "ResumeOptimizeAgent": "optimize_result",
    "InterviewQuestionAgent": "interview_result",
    "InterviewAgent": "interview_result",
    "CareerAgent": "career_result",
    "SummaryAgent": "final_report",
}


@dataclass
class AgentContext:
    """Structured execution context for the agent pipelines."""

    resume_id: int = 0
    jd_id: int = 0
    user_id: int | None = None
    user_request: str = ""
    task_id: int | None = None
    run_id: int | None = None
    db: Session | None = field(default=None, repr=False, compare=False)

    intent: str | None = None
    intent_detail: dict[str, Any] | None = None
    required_steps: list[str] = field(default_factory=list)
    plan: list[dict[str, Any]] = field(default_factory=list)

    resume_parsed: dict[str, Any] | None = None
    jd_parsed: dict[str, Any] | None = None

    match_result: dict[str, Any] | None = None
    optimize_result: dict[str, Any] | None = None
    interview_result: dict[str, Any] | None = None
    career_result: dict[str, Any] | None = None
    final_report: dict[str, Any] | None = None

    agent_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def for_analysis(
        cls,
        resume_id: int,
        jd_id: int,
        user_id: int | None = None,
        db: Session | None = None,
        user_request: str = "",
        task_id: int | None = None,
        run_id: int | None = None,
    ) -> AgentContext:
        return cls(
            resume_id=resume_id,
            jd_id=jd_id,
            user_id=user_id,
            db=db,
            user_request=user_request,
            task_id=task_id,
            run_id=run_id,
        )

    def with_db(self, db: Session | None) -> AgentContext:
        copied = self.fork()
        copied.db = db
        return copied

    def fork(self) -> AgentContext:
        """深复制全部载荷字段，沿用同一个 session。

        清单直接来自 dataclass：再加字段不必记得回来补一行，手写清单漏一项就是静默丢数据。
        """
        copied = AgentContext(**{f.name: deepcopy(getattr(self, f.name)) for f in fields(self) if f.name != "db"})
        copied.db = self.db
        return copied

    def record_agent_output(self, agent_name: str, result: dict[str, Any]):
        self.agent_outputs[agent_name] = result

        field_name = _AGENT_RESULT_FIELD_MAP.get(agent_name)
        if field_name == "intent_detail":
            self.intent_detail = result
            self.intent = result.get("intent", self.intent)
            self.required_steps = result.get("required_steps", self.required_steps)
        elif field_name == "resume_parsed":
            self.resume_parsed = result.get("parsed", result)
        elif field_name == "jd_parsed":
            self.jd_parsed = result.get("parsed", result)
        elif field_name:
            setattr(self, field_name, result)

    def get_agent_output(self, agent_name: str, default: Any = None) -> Any:
        return self.agent_outputs.get(agent_name, default)

    def has_agent_output(self, agent_name: str) -> bool:
        return agent_name in self.agent_outputs

    def get(self, key: str, default: Any = None) -> Any:
        if key == "db":
            return self.db if self.db is not None else default
        if key in self.agent_outputs:
            return self.agent_outputs[key]
        if key in self.extras:
            return self.extras[key]
        if hasattr(self, key):
            value = getattr(self, key)
            return default if value is None else value
        return default

    def set_extra(self, key: str, value: Any):
        self.extras[key] = value

    def to_log_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for item in fields(self):
            if item.name == "db":
                continue
            data[item.name] = deepcopy(getattr(self, item.name))
        return data
