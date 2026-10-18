"""P3.1 测试护栏（先于功能代码落地，2026-10-17）。

这份文件**照原稿的顺序**写：护栏先落，实现后补。它现在大部分是红的，那是合规状态，不是坏了
——本仓库这一族的完成标准链条是"护栏先行（红着落地）→ 功能代码 → 全量不回退 → 数字回写文档
→ 真 provider 抽样"，见 `简历与面试优化.md` §8。

原稿 §4 P3.1 写了五条护栏，这里落成六条能执行的断言：

1. 三档评分输入下**启发式路径**的输出必须是确定的（好/中/差 × 是否已追问）。
2. LangGraph 那张状态机：三节点齐、每条路径可达、没有死状态。
3. 兜底链逐级回落：LLM 决策抛异常 ⇒ 落启发式且不卡会话；启发式的题源空 ⇒ 落 starter。
4. 决策器不许改 `next_question` 已有的 metadata 字段形状（只许加可选键），协议文档要同步。
5. 决策器一次调用都不许自己开 DB 会话——题源、评分、追问历史都由引擎传进来。
6. 混合动态那条延迟策略要在**数据结构上**能测：advance 必须命中候选池（零 LLM 等待），
   deepen/generate 才允许走现场生成。

第 3、5 条是原稿没写、我读代码时加的：原稿说"其余一行不动"，而 `InterviewEngine` 现在整个
类只有 `self.db` 一个入口，决策器若顺手 `SessionLocal()` 就会变成第二条独立会话链——这一族
在本仓库已经栽过（"一实例一链"那条不变量没有任何门会红）。所以把它写成一条能跑的断言。
"""

from __future__ import annotations

import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]

try:  # 实现落地之前，这份护栏必须是"干净的红"，不能是收集期爆炸
    from app.services import interviewer_decision as dec
except ImportError:  # pragma: no cover - 护栏先落地的预期状态
    dec = None


def _module() -> object:
    assert dec is not None, (
        "P3.1 护栏先落：`app/services/interviewer_decision.py` 还没实现。"
        "实现之后这一条会自动变绿；不要为了让它绿而在这里造替身。"
    )
    return dec


def _state(
    *,
    scores: list[int],
    evidence: list[str] | None = None,
    asked_followup: bool = False,
    pool: list[dict] | None = None,
    weaknesses: list[str] | None = None,
) -> dict:
    """决策器的输入契约（引擎传进来，决策器不自己取库）。"""
    return {
        "round_index": len(scores),
        "scores": scores,
        "evidence": evidence or [""] * len(scores),
        "asked_followup": asked_followup,
        "candidate_pool": pool
        if pool is not None
        else [{"id": 1, "question": "讲讲 RAG 的召回", "category": "技术基础"}],
        "weaknesses": weaknesses or [],
    }


# ---------------------------------------------------------------------------
# 1. 三档评分下的启发式输出必须是确定的
# ---------------------------------------------------------------------------


def test_heuristic_deepens_on_weak_answer_without_followup() -> None:
    """差档：最后一题得分低于阈值且这题还没追问过 ⇒ deepen。这是兜底链的第一级，
    必须完全不碰 LLM，所以 mock/无 provider 也能跑（答辩演示的前提）。"""
    decided = _module().decide_heuristic(_state(scores=[85, 78, 52]))
    assert decided["action"] == "deepen", decided
    assert decided["source"] == "heuristic", decided


def test_heuristic_advances_on_strong_answer() -> None:
    """好档：得分达标 ⇒ advance，从候选池顺序取题。"""
    decided = _module().decide_heuristic(_state(scores=[88, 90, 86]))
    assert decided["action"] == "advance", decided


def test_heuristic_does_not_loop_on_a_weak_already_followed_up_question() -> None:
    """差档但**已经追问过一次** ⇒ 推进，不许在同一题上无限深挖。
    这条是防"决策器把面试变成针对同一短板的审讯"，原稿只写了"评分<70且未追问→deepen"，
    没写已追问过怎么办——不钉住就会实现成死循环。"""
    decided = _module().decide_heuristic(_state(scores=[85, 74, 41], asked_followup=True))
    assert decided["action"] == "advance", decided


def test_mid_grade_boundary_is_explicit() -> None:
    """阈值本身要能被读出来，且在边界上判得确定。原稿写的是"**评分 <70** 且未追问→deepen"，
    所以 70 这一档是**推进**而不是深挖——边界归哪一侧必须钉住，不然实现会两边漂。"""
    threshold = _module().DEEPEN_SCORE_CEILING
    assert threshold == 70, f"追问阈值必须与兜底链那格一致（<70 才深挖），读到的是 {threshold}"
    assert _module().decide_heuristic(_state(scores=[threshold - 1]))["action"] == "deepen"
    assert _module().decide_heuristic(_state(scores=[threshold]))["action"] == "advance"


# ---------------------------------------------------------------------------
# 2. 状态机完整性：三节点齐、可达、无死状态
# ---------------------------------------------------------------------------


def test_graph_has_the_three_documented_nodes() -> None:
    """原稿那张三节点图（update_profile → decide → compose_question）是 P3.1 的形状本身；
    少一个节点就说明实现退化成了一次函数调用，那就不需要 LangGraph。"""
    graph = _module().InterviewerDecisionGraph()
    names = set(graph.node_names())
    assert names == {"update_profile", "decide", "compose_question"}, names


def test_every_node_is_reachable_and_no_state_is_dead() -> None:
    """从入口能走到 compose_question，且每个节点都有后继出口（没有"进了就出不来"的死状态）。"""
    graph = _module().InterviewerDecisionGraph()
    transitions = graph.edges()
    for node in graph.node_names():
        assert transitions.get(node), f"{node} 是死状态：没有出边"
    reached = _module().reachable_from(graph, "update_profile")
    assert reached >= set(graph.node_names()), f"不可达节点：{set(graph.node_names()) - reached}"


# ---------------------------------------------------------------------------
# 3. 兜底链逐级回落
# ---------------------------------------------------------------------------


def test_llm_failure_falls_back_to_heuristic_without_raising() -> None:
    """LLM 决策抛异常 ⇒ 落启发式。会话不许因为决策器失败而中断——
    这是本项目当反面教材的那一族（AI 降级对候选人静默、对内可查）。"""

    def boom(prompt: str) -> dict:  # 决策调用直接炸
        raise RuntimeError("provider down")

    decided = _module().decide_next(_state(scores=[85, 60, 44]), chat=boom)
    assert decided["action"] in {"deepen", "advance"}, decided
    assert decided["degraded"] is True, f"决策降级必须带对内可查的标志：{decided}"


def test_empty_pool_falls_back_to_starter() -> None:
    """启发式的题源（候选池）空 ⇒ 落 starter，也就是引擎原来那份题目列表，不许返回"没题了"。
    这条是"候选人正在等着下一题"那一侧的兜底：决策器不许把面试提前结束。"""
    decided = _module().decide_next(_state(scores=[80, 82], pool=[]))
    assert decided["source"] == "starter", decided
    assert decided["action"] == "advance", decided
    assert _question_text(decided), f"starter 那一档给了个空题面：{decided}"


def _question_text(decided: dict) -> str:
    """把"下一题的题面"取出来。决策器返回的 question 是**一整个题目 dict**（引擎要按 dict 用），
    所以 `assert decided.get("question")` 是**空断言**——只要那个 dict 非空就永远为真，
    里面题面是空串也照过。这一条是变异验证逮出来的（把 starter 题面改成空串，14 条全绿），
    所以判据必须落到题面字符串上。"""
    question = decided.get("question")
    if isinstance(question, dict):
        return str(question.get("question") or question.get("q") or "").strip()
    return str(question or "").strip()


def test_decide_never_returns_no_question() -> None:
    """任何输入组合都不许让下一题消失（这是 finish 以外的路径）。判据是**题面非空**，
    不是"有个 question 键"。"""
    for state in (
        _state(scores=[]),
        _state(scores=[0]),
        _state(scores=[100, 100, 100], pool=[]),
        _state(scores=[33, 21], weaknesses=["分布式事务"]),
    ):
        decided = _module().decide_next(state)
        assert _question_text(decided), f"决策器让下一题的题面变成空：{state['scores']} → {decided}"


# ---------------------------------------------------------------------------
# 4. metadata 只许加可选键；协议文档同步
# ---------------------------------------------------------------------------


def test_engine_metadata_shape_is_untouched() -> None:
    """原稿那句"其余一行不动"要能被机器复核：`next_question` 现在发的六个 metadata 键
    一个都不许消失或改名。决策器只能**加**可选键。"""
    source = (BACKEND / "app/services/interview_engine.py").read_text(encoding="utf-8")
    block = source[source.index("def next_question") : source.index("def handle_answer")]
    for key in ("round", "total", "category", "timeout_seconds", "question_id", "turn_id"):
        assert f'"{key}"' in block, f"next_question 的 metadata 少了既有键 {key}：{key}"


def test_decision_metadata_is_documented() -> None:
    """新增的决策键必须同时出现在协议文档里——这一族的纪律：WS 字段改动要回写
    `docs/面试消息协议.md`（上一格 timeout_seconds 就是这么做的）。"""
    doc = (BACKEND.parent / "docs/面试消息协议.md").read_text(encoding="utf-8")
    assert re.search(r"`decision`", doc), "协议文档里没有 decision 那一格 metadata 的说明"


# ---------------------------------------------------------------------------
# 5. 决策器不许自己开 DB 会话
# ---------------------------------------------------------------------------


def test_decision_module_does_not_open_its_own_session() -> None:
    """题源/评分/追问历史一律由引擎传进来。决策器里出现 SessionLocal / get_db 就是第二条
    独立会话链，而本仓库没有任何门会红那种形状（D44 查过），所以只能靠这条断言钉。"""
    path = BACKEND / "app/services/interviewer_decision.py"
    text = path.read_text(encoding="utf-8")
    for forbidden in ("SessionLocal", "get_db(", "from app.core.database import"):
        assert forbidden not in text, f"决策器不该自己开会话：{forbidden}"


# ---------------------------------------------------------------------------
# 6. advance 必须零 LLM 等待
# ---------------------------------------------------------------------------


def test_advance_makes_no_chat_call() -> None:
    """混合动态那条延迟策略的全部价值：advance 从候选池选题 = 零等待。
    要是它偷偷调了 chat，节奏目标（≥75% 题目零额外等待）就成了空话。"""
    calls: list[str] = []

    def spy(prompt: str) -> dict:
        calls.append(prompt)
        return {"action": "advance"}

    _module().decide_next(
        _state(scores=[88, 90], pool=[{"id": 7, "question": "讲讲幂等", "category": "技术基础"}]), chat=spy
    )
    assert calls == [], f"advance 那一档不该有任何 LLM 调用，实际发了 {len(calls)} 次"


def test_deepen_may_generate_but_always_returns_a_question() -> None:
    """deepen 允许现场生成（那是它的价值），但生成失败时必须回落成"针对该题的单点追问"，
    不许把 None 递给引擎。"""

    def boom(prompt: str) -> dict:
        raise RuntimeError("generation failed")

    decided = _module().decide_next(
        _state(scores=[85, 42], evidence=["成果没有量化"], weaknesses=["量化指标"]),
        chat=boom,
    )
    assert decided["action"] == "deepen", decided
    assert _question_text(decided), f"生成失败又没回落出题面：{decided}"
    assert decided["source"] in {"heuristic", "starter"}, decided


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
