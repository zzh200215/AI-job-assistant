"""编排那一层的 trace 归属：每条模型调用要能说清"哪个节点、用的哪版 prompt"。

起因是 2026-10-13 那一整条真 provider 的编排链（D233）：7 行 `prompt_trace` 里
只有 match 那一发带着 `prompt_version`，其余 6 行是 `unknown`——`source` 那列其实有
`agent.<Name>`（`_seed_trace_context` 一直在打），**缺的是"哪一版 prompt"**。
事后想比较两版 prompt 的耗时/降级率，光这一位就分不出来。

三条腿：
1. 每个会打模型的 agent 都声明 `prompt_version`，且值必须等于某个 prompt 模块里的常量
   （不许在 agent 这边再抄一遍字面量）；
2. 这份声明真的进了 trace 上下文（行为，不是读属性）；
3. 没声明 ⇒ 落成 `unknown`，而不是被一个假的默认值蒙过去。
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from pathlib import Path

from app.agents.base_agent import BaseAgent, _seed_trace_context
from app.orchestration.context import AgentContext
from app.prompts.rendering import render_prompt
from app.services import llm_service
from app.services.llm_service import LLMTraceScope

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "app" / "prompts"

# 这些节点确实会打模型，就必须带版本；`run_parse` 那几支是纯规则、0 token，不进这张表。
MODEL_CALLING_AGENTS = (
    "IntentAgent",
    "ResumeAgent",
    "JobAgent",
    "MatchAgent",
    "InterviewAgent",
    "CareerAgent",
    "SummaryAgent",
    "InterviewQuestionAgent",
    "ResumeOptimizeAgent",
)


def _declared_prompt_versions() -> set[str]:
    versions: set[str] = set()
    for module in pkgutil.iter_modules([str(PROMPTS_DIR)]):
        text = (PROMPTS_DIR / f"{module.name}.py").read_text(encoding="utf-8")
        versions.update(re.findall(r'^PROMPT_VERSION = "(.+)"$', text, re.M))
    return versions


AGENT_MODULES = {
    "IntentAgent": "app.agents.intent_agent",
    "ResumeAgent": "app.agents.resume_agent",
    "JobAgent": "app.agents.job_agent",
    "MatchAgent": "app.agents.match_agent",
    "InterviewAgent": "app.agents.interview_agent",
    "CareerAgent": "app.agents.career_agent",
    "SummaryAgent": "app.agents.summary_agent",
    "InterviewQuestionAgent": "app.agents.interview_question_agent",
    "ResumeOptimizeAgent": "app.agents.resume_optimize_agent",
}


def _agent_class(name: str) -> type[BaseAgent]:
    """直接从模块取类，不绕注册表——注册表在各测试之间会被重建（读它的时机不稳）。"""
    return getattr(importlib.import_module(AGENT_MODULES[name]), name)


def test_every_model_calling_agent_declares_a_prompt_version():
    declared = {name: _agent_class(name).prompt_version for name in MODEL_CALLING_AGENTS}

    missing = [name for name, value in declared.items() if not value]
    assert not missing, f"这些节点没声明 prompt_version：{missing}"


def test_declared_versions_are_the_prompt_modules_own_constants():
    """值必须能在 `app/prompts/*` 里找到——防的就是"在 agent 这边再抄一遍字面量"。"""
    known = _declared_prompt_versions()
    declared = {name: _agent_class(name).prompt_version for name in MODEL_CALLING_AGENTS}

    assert set(declared.values()) <= known, f"这些版本串不在任何 prompt 模块里：{set(declared.values()) - known}"
    assert len(set(declared.values())) == len(declared), "两个节点共用同一个版本串：改一版 prompt 会同时改两条读数"


def test_the_seeded_context_reaches_the_trace_row(monkeypatch):
    seen: list[str] = []

    def fake_chat(prompt, **kwargs):
        scope = LLMTraceScope.begin(prompt=prompt, provider="mock", writer="chat_json")
        seen.append(scope.prompt_version)
        return {"ok": True}

    monkeypatch.setattr(llm_service, "chat_json", fake_chat)
    agent = importlib.import_module("app.agents.resume_agent").ResumeAgent()
    context = AgentContext(resume_id=1, jd_id=1, task_id=7, run_id=9, db=None)

    _seed_trace_context(agent.name, context, agent.prompt_version)
    llm_service.chat_json("prompt-text")

    assert seen == ["resume-agent-v2"]


def test_an_undeclared_agent_falls_back_to_unknown_not_a_fake_value(monkeypatch):
    seen: list[str] = []

    def fake_chat(prompt, **kwargs):
        scope = LLMTraceScope.begin(prompt=prompt, provider="mock", writer="chat_json")
        seen.append(scope.prompt_version)
        return {"ok": True}

    monkeypatch.setattr(llm_service, "chat_json", fake_chat)
    context = AgentContext(resume_id=1, jd_id=1, db=None)

    _seed_trace_context("SomeNewAgent", context, "")
    llm_service.chat_json("prompt-text")

    assert seen == ["unknown"], "没声明就该显式落成 unknown，不能被一个假默认值蒙过去"


def test_resume_agent_prompt_renders_with_the_rubric_injected():
    """prompt 里那段七维口径是生成的：表改了 prompt 没跟着走，这一发当场红。"""
    from app.prompts.resume_agent import RESUME_AGENT_PROMPT
    from app.services import resume_report_rubric as rubric

    rendered = render_prompt(
        RESUME_AGENT_PROMPT,
        resume_json="{}",
        rubric_block=rubric.rubric_prompt_block(),
    )

    assert importlib.import_module("app.prompts.resume_agent").PROMPT_VERSION == "resume-agent-v2"
    for key, _label, _full, _star, _desc in rubric.DIMENSIONS:
        assert key in rendered
