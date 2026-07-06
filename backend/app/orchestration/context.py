# -*- coding: utf-8 -*-
"""Structured agent context shared across orchestration strategies."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List, Optional

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

_STEP_RESULT_FIELD_MAP = {
    "intent_recognition": "intent_detail",
    "resume_parse": "resume_parsed",
    "jd_parse": "jd_parsed",
    "task_planning": "plan",
    "knowledge_retrieval": "retrieval_results",
    "matching_analysis": "match_result",
    "resume_optimization": "optimize_result",
    "interview_question_generation": "interview_result",
    "career_planning": "career_result",
    "self_check": "self_checks",
    "final_report": "final_report",
}


@dataclass
class AgentContext:
    """Structured execution context for agents and step-based workflows."""

    resume_id: int = 0
    jd_id: int = 0
    user_id: Optional[int] = None
    user_request: str = ""
    db: Optional[Session] = field(default=None, repr=False, compare=False)

    intent: Optional[str] = None
    intent_detail: Optional[Dict[str, Any]] = None
    required_steps: List[str] = field(default_factory=list)
    plan: List[Dict[str, Any]] = field(default_factory=list)

    resume_parsed: Optional[Dict[str, Any]] = None
    jd_parsed: Optional[Dict[str, Any]] = None
    retrieval_results: Dict[str, Any] = field(default_factory=dict)
    rag_confidence: Optional[Dict[str, Any]] = None

    match_result: Optional[Dict[str, Any]] = None
    optimize_result: Optional[Dict[str, Any]] = None
    interview_result: Optional[Dict[str, Any]] = None
    career_result: Optional[Dict[str, Any]] = None
    self_checks: List[Dict[str, Any]] = field(default_factory=list)
    final_report: Optional[Dict[str, Any]] = None

    agent_outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def for_analysis(
        cls,
        resume_id: int,
        jd_id: int,
        user_id: Optional[int] = None,
        db: Optional[Session] = None,
        user_request: str = "",
    ) -> "AgentContext":
        return cls(
            resume_id=resume_id,
            jd_id=jd_id,
            user_id=user_id,
            db=db,
            user_request=user_request,
        )

    def with_db(self, db: Optional[Session]) -> "AgentContext":
        copied = self.fork()
        copied.db = db
        return copied

    def fork(self) -> "AgentContext":
        copied = AgentContext(
            resume_id=self.resume_id,
            jd_id=self.jd_id,
            user_id=self.user_id,
            user_request=self.user_request,
            db=self.db,
            intent=self.intent,
            intent_detail=deepcopy(self.intent_detail),
            required_steps=deepcopy(self.required_steps),
            plan=deepcopy(self.plan),
            resume_parsed=deepcopy(self.resume_parsed),
            jd_parsed=deepcopy(self.jd_parsed),
            retrieval_results=deepcopy(self.retrieval_results),
            rag_confidence=deepcopy(self.rag_confidence),
            match_result=deepcopy(self.match_result),
            optimize_result=deepcopy(self.optimize_result),
            interview_result=deepcopy(self.interview_result),
            career_result=deepcopy(self.career_result),
            self_checks=deepcopy(self.self_checks),
            final_report=deepcopy(self.final_report),
            agent_outputs=deepcopy(self.agent_outputs),
            extras=deepcopy(self.extras),
        )
        return copied

    def record_agent_output(self, agent_name: str, result: Dict[str, Any]):
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

    def record_step_output(self, step_name: str, result: Dict[str, Any]):
        field_name = _STEP_RESULT_FIELD_MAP.get(step_name)
        if field_name == "intent_detail":
            self.intent_detail = result
            self.intent = result.get("intent", self.intent)
            self.required_steps = result.get("required_steps", self.required_steps)
        elif field_name == "resume_parsed":
            self.resume_parsed = result.get("parsed", result)
        elif field_name == "jd_parsed":
            self.jd_parsed = result.get("parsed", result)
        elif field_name == "plan":
            self.plan = result.get("plan", []) if isinstance(result, dict) else []
        elif field_name == "retrieval_results":
            self.retrieval_results = result.get("retrievals", {}) if isinstance(result, dict) else {}
            self.rag_confidence = result.get("rag_confidence") if isinstance(result, dict) else None
        elif field_name == "self_checks":
            self.self_checks = result.get("checks", []) if isinstance(result, dict) else []
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

    def __getitem__(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: Any):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self.extras[key] = value

    def to_log_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for item in fields(self):
            if item.name == "db":
                continue
            data[item.name] = deepcopy(getattr(self, item.name))
        return data
