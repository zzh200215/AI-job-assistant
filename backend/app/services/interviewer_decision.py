"""P3.1 面试官决策器：把"下一题问什么"从按下标取，换成一次可回落的决策。

形状照 `简历与面试优化.md` §4 P3.1 那张图：**三节点状态机**（update_profile → decide →
compose_question），外围 `InterviewEngine` 的 WS/评分/租约/断线恢复一概不动，题源这一处换成问决策器。

三条设计约束，都是被本仓库既有教训钉住的：

1. **这个模块不碰数据库**。引擎只有 `self.db` 一个入口，题源、评分、追问历史一律由调用方传进
   状态里，本文件既不建会话也不取会话。决策器里一旦出现自己建的库连接，就是第二条独立会话链——
   而 D44 已经查过：那种形状**没有任何门会红**（两个文件各扫各的都合法），所以只能靠
   `test_interview_decision_graph_guardrails.py` 那条断言钉住。（这里刻意不复述那条断言扫的
   那几个字面量：静态守卫按文本扫，注释里逐字写被禁形态会把自己钉红。）
2. **兜底链逐级回落，且任何一级都不许把"下一题"变成空**。LLM 决策炸 ⇒ 落启发式；启发式题源空 ⇒
   落 starter。候选人那边看到的是"面试官接着问"，看不到降级（`AI 降级对候选人静默、对内可查`
   那条产品决策）；对内可查靠返回体里那个 `degraded` 与 `source`。
3. **advance 一档零 LLM 调用**。原稿那格"75% 以上题目零额外等待"的全部价值就在这：得分达标时
   直接从候选池顺序取题，一次网络往返都不发。所以启发式先判，判出 advance 就立刻返回。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

DECISION_VERSION = "p3.1"

# 低于这个分才深挖；等于 70 算"没达标"（< 70 的语义，不做四舍五入）。
DEEPEN_SCORE_CEILING = 70

NODES = ("update_profile", "decide", "compose_question")

EDGES: dict[str, tuple[str, ...]] = {
    "update_profile": ("decide",),
    "decide": ("compose_question",),
    "compose_question": ("__end__",),
}

# 题源空到连 starter 都没有时用的兜底问句。它必须存在：返回空题等于让决策器把面试提前结束。
FALLBACK_QUESTION = "请讲讲你最近做过的一个项目里，最难的一个决定，以及当时为什么这么定。"

DECIDE_PROMPT_HEADER = (
    '你是面试官。只输出 JSON：{"action": "deepen|advance", "question": "一句单点追问"}。'
    "deepen 时 question 必填、只问一个点；advance 时 question 留空。"
)


class InterviewerDecisionGraph:
    """三节点状态机的声明层。

    节点名与边表就是 P3.1 那张图本身；`compile()` 才产生可跑的 LangGraph 图。声明与可跑分开，
    是因为护栏要能在没有 provider 的机器上复核形状（三节点齐、可达、无死状态）。
    """

    def node_names(self) -> tuple[str, ...]:
        return NODES

    def edges(self) -> dict[str, set[str]]:
        return {node: set(targets) for node, targets in EDGES.items()}

    def compile(self):  # pragma: no cover - 由 P3.1 第二格的引擎接线使用
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(dict)
        graph.add_node("update_profile", update_profile)
        graph.add_node("decide", _decide_node)
        graph.add_node("compose_question", compose_question)
        graph.add_edge(START, "update_profile")
        graph.add_edge("update_profile", "decide")
        graph.add_edge("decide", "compose_question")
        graph.add_edge("compose_question", END)
        return graph.compile()


def reachable_from(graph: InterviewerDecisionGraph, start: str) -> set[str]:
    """从 start 沿出边走到底，返回能到达的节点集合（含 start）。"""
    edges = graph.edges()
    seen: set[str] = set()
    frontier = [start]
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        for target in edges.get(node, ()):
            if target != "__end__":
                frontier.append(target)
    return seen


def update_profile(state: dict[str, Any]) -> dict[str, Any]:
    """把这一轮的得分与证据并进候选人画像：强弱项、已覆盖考点、追问深度。"""
    scores = list(state.get("scores") or [])
    weaknesses = list(state.get("weaknesses") or [])
    evidence_chain = [item for item in (state.get("evidence") or []) if item]
    covered = sorted({str(item.get("category")) for item in _pool(state) if item.get("category")})
    last_score = scores[-1] if scores else 100
    return {
        **state,
        "profile": {
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "last_score": last_score,
            "weaknesses": weaknesses,
            "evidence": evidence_chain[-1] if evidence_chain else "",
            "covered_categories": covered,
            "followup_depth": 1 if state.get("asked_followup") else 0,
        },
    }


def decide_heuristic(state: dict[str, Any]) -> dict[str, Any]:
    """启发式那一档：零 LLM、零 DB，输出必须确定。

    规则只有两条边界：<70 且这题还没追问过 ⇒ 深挖；**已经追问过一次就推进**，不许在同一
    短板上无限深挖（那会把面试变成针对一件事的审讯）。
    """
    scores = list(state.get("scores") or [])
    last = scores[-1] if scores else 100
    if last < DEEPEN_SCORE_CEILING and not state.get("asked_followup"):
        return {"action": "deepen", "source": "heuristic"}
    return {"action": "advance", "source": "heuristic"}


def _decide_node(state: dict[str, Any]) -> dict[str, Any]:
    return decide_heuristic(state)


def compose_question(
    state: dict[str, Any], decision: dict[str, Any], llm_question: str | None = None
) -> dict[str, Any]:
    """按决策产出下一题。返回体里一定带 question——这是"下一题不许变空"那条护栏的落点。

    题源空到只能吃 starter 时，顶层 `source` 要说实话（报成 heuristic 就等于把"引擎原来那份
    题目列表在顶上"这件事藏起来了，而 P3.2 的对比评测要按这个数算"动态到底接管了多少题"）。

    `llm_question` 是 LLM 现场组织的那句。它非空就用它——启发式那句是模板，LLM 那句才谈得上
    "针对回答内容"；为空（LLM 没回/回得不合格/超时）就落回模板句。
    """
    if decision.get("action") == "deepen":
        question = _followup(state)
        if llm_question and llm_question.strip():
            question = {
                "question": llm_question.strip(),
                "category": "项目经验",
                "id": f"followup-{state.get('round_index', 0)}",
                "source": "llm",
            }
        return {"action": "deepen", "source": decision.get("source", "heuristic"), "question": question}
    question = _next_from_pool(state)
    source = "starter" if question.get("source") == "starter" else decision.get("source", "heuristic")
    return {"action": "advance", "source": source, "question": question, "transition": ""}


def decide_next(state: dict[str, Any], *, chat: Callable[[str], dict[str, Any]] | None = None) -> dict[str, Any]:
    """问决策器要下一题。`chat` 是注入进来的（不 import 被测模块），None 就是纯启发式。

    顺序是"先启发、再问 LLM"：启发式判出 advance 时一次调用都不发（混合动态那格的零等待前提）；
    只有判出 deepen 才让 LLM 去现场组织一句针对性追问，它炸了就落回启发式自己拼的那句。
    """
    decision = decide_heuristic(state)
    if decision["action"] == "advance":
        return compose_question(state, decision)

    if chat is not None:
        try:
            raw = chat(_decision_prompt(state, decision))
            action = (raw or {}).get("action")
            if action in {"deepen", "advance"}:
                llm_question = raw.get("question") if action == "deepen" else None
                return compose_question(state, {"action": action, "source": "llm"}, llm_question=llm_question)
            # 回了但不是一个合法动作（mock 的常量、模型跑题）⇒ 这一发也算降级，不能装作没事。
            decision = {**decision, "degraded": True}
        except Exception:  # noqa: BLE001 - 决策失败不许打断会话
            decision = {**decision, "degraded": True}

    composed = compose_question(state, decision)
    if decision.get("degraded"):
        composed["degraded"] = True
    return composed


def _pool(state: dict[str, Any]) -> list[dict[str, Any]]:
    pool = state.get("candidate_pool") or []
    return [item for item in pool if isinstance(item, dict)]


def _next_from_pool(state: dict[str, Any]) -> dict[str, Any]:
    pool = _pool(state)
    if not pool:
        return {
            "question": FALLBACK_QUESTION,
            "category": "通用HR",
            "id": "starter-fallback",
            "source": "starter",
        }
    index = int(state.get("round_index") or 0) % len(pool)
    picked = dict(pool[index])
    picked.setdefault("source", "pool")
    return picked


def _followup(state: dict[str, Any]) -> dict[str, Any]:
    """针对上一题回答里的模糊点拼一句单点追问（模板追问的升级形状）。"""
    profile = update_profile(state)["profile"]
    focus = profile["weaknesses"][0] if profile["weaknesses"] else ""
    evidence = (profile["evidence"] or "").strip()
    if evidence:
        text = f"你刚才提到「{evidence[:40]}」，这一块的成果当时是怎么量化的？"
    elif focus:
        text = f"这块我想再深入一点：你在{focus}上具体做过什么？"
    else:
        text = "刚才的回答可以再具体一些：你本人负责的是哪一段？"
    return {
        "question": text,
        "category": "项目经验",
        "id": f"followup-{state.get('round_index', 0)}",
        "source": "heuristic",
    }


def _decision_prompt(state: dict[str, Any], decision: dict[str, Any]) -> str:
    profile = update_profile(state)["profile"]
    payload = {
        "ceiling": DEEPEN_SCORE_CEILING,
        "profile": profile,
        "heuristic_action": decision["action"],
    }
    return f"{DECIDE_PROMPT_HEADER}\n输入：{json.dumps(payload, ensure_ascii=False)}"
