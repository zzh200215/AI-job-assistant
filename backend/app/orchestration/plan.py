"""编排计划：把意图识别产出的 `required_steps` 变成能执行、能核对的节点计划。

C2 之前的状态（实测）：`required_steps` 一路写进 `agent_task.intent_detail` 就没人读了，
`_should_execute()` 只看一张硬编码的"意图 → agent 名"表；更糟的是提示词里的名单还留着
C4 删掉的 `task_planning` / `knowledge_retrieval` / `self_check` —— 模型在按一份不存在
的词汇表做计划。

两条边界写死在这里，不给模型选择：

- 解析类节点（意图、简历、JD）是后续任何节点的前置条件，计划不能砍掉它们；
- 汇总节点在有任何分析结果时保留，否则候选人拿到的就是一堆碎片。

置信度**故意不参与决策**：真机上每个任务都是 0.95，正好等于提示词里的示例值，
那是抄来的数字，不是判断。
"""

from typing import Any

from app.orchestration.protocol import normalize_step_name

# 结构前置：无论计划怎么写，这些都要跑
ALWAYS_RUN_STEPS = frozenset({"intent_recognition", "resume_parse", "jd_parse"})
# 计划可选的节点（规范步骤名 → 执行它的 agent 名）
OPTIONAL_STEP_TO_AGENT: dict[str, tuple[str, ...]] = {
    "match_analysis": ("MatchAnalysisAgent", "MatchAgent"),
    "resume_optimization": ("ResumeOptimizeAgent",),
    "interview_questions": ("InterviewQuestionAgent", "InterviewAgent"),
    "career_planning": ("CareerAgent",),
    "summary_report": ("SummaryAgent",),
}

# 意图 → 该跑哪些可选节点。这是模型没给出可用计划时的兜底，
# 内容与 C2 之前 _should_execute() 里那张表逐项等价。
INTENT_TO_STEPS: dict[str, tuple[str, ...]] = {
    "resume_match_only": ("match_analysis", "summary_report"),
    "optimize_only": ("resume_optimization", "summary_report"),
    "interview_only": ("interview_questions", "summary_report"),
    "full_analysis": ("match_analysis", "resume_optimization", "interview_questions", "summary_report"),
}

PLAN_SOURCE_MODEL = "model_steps"
PLAN_SOURCE_INTENT = "intent_fallback"


def plan_from_intent(intent_detail: dict[str, Any] | None, *, available_agents: list[str]) -> dict[str, Any]:
    """把意图识别的输出规约成一份可执行计划。

    返回 `{"steps": [...], "agents": set, "source": ..., "dropped": [...]}`：
    `dropped` 是模型写了但系统里根本不存在的节点名——那是需要被看见的信号，
    不是悄悄丢掉就算处理完了。
    """
    intent_detail = intent_detail or {}
    intent = intent_detail.get("intent") or "full_analysis"
    wanted_raw = intent_detail.get("required_steps") or []
    wanted = {normalize_step_name(str(step)) for step in wanted_raw if str(step).strip()}

    usable = wanted & set(OPTIONAL_STEP_TO_AGENT)
    source = PLAN_SOURCE_MODEL
    if not usable:
        usable = set(INTENT_TO_STEPS.get(intent, INTENT_TO_STEPS["full_analysis"]))
        source = PLAN_SOURCE_INTENT
    # 解析类节点由系统保留，模型写不写都在
    steps = sorted(ALWAYS_RUN_STEPS | usable)
    dropped = sorted(wanted - set(OPTIONAL_STEP_TO_AGENT) - ALWAYS_RUN_STEPS)

    agents = _agents_for_steps(steps, available_agents)
    return {
        "steps": steps,
        "agents": agents,
        "source": source,
        "dropped": dropped,
        "intent": intent,
    }


def _agents_for_steps(steps: set[str], available_agents: list[str]) -> list[str]:
    """把步骤名映射回本次流水线里真实存在的 agent，保持 available_agents 的顺序。

    顺序不能交给模型：resume_optimization 依赖 jd_parse，模型若给出乱序计划，
    轻则节点读不到上游结果，重则把整条链跑空。
    """
    allowed: set[str] = set()
    for step in steps:
        if step in ALWAYS_RUN_STEPS:
            continue
        for agent in OPTIONAL_STEP_TO_AGENT.get(step, ()):
            allowed.add(agent)

    ordered = [name for name in available_agents if name in allowed or normalize_step_name(name) in steps]
    return ordered


def as_plan_rows(steps: set[str], agents: list[str]) -> list[dict[str, Any]]:
    """落成 `agent_task.plan` 的样子：顺序、节点、归属步骤，三样都可核对。"""
    rows = []
    for index, agent in enumerate(agents, start=1):
        rows.append({"order": index, "agent": agent, "step": normalize_step_name(agent)})
    return rows
