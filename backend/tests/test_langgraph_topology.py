"""C5 — LangGraph 分层图必须是真拓扑，而不是"链换个写法"。

改之前每层只有一个节点、节点内部自己开 ThreadPoolExecutor：图画的是链、跑的也是链，
`_wire_sequential_graph` 只是把 for 循环换了个写法。现在是
`route_i ──Send──▶ work_i ×N ──▶ join_i`，扇出交给图。

并发不靠"看起来快"来证明：每个分支记录自己的起止时间区间，断言同层区间**重叠**。
"""

import threading
import time
from typing import Any

import pytest
from sqlalchemy import delete

from app.agents.base_agent import BaseAgent
from app.models.agent import AgentStepLog, AgentTask
from app.models.agent_run import AgentMessage, AgentRun
from app.orchestration.context import AgentContext
from app.orchestration.registry import AgentSpec, UnifiedRegistry
from app.orchestration.strategies import LayeredParallelStrategy, StrategyFactory

SLEEP_SECONDS = 0.3
LEVEL_0 = ("ResumeAgent", "JobAgent")
ALL_AGENTS = (*LEVEL_0, "MatchAgent", "InterviewAgent", "CareerAgent", "SummaryAgent")


class _SlowAgent(BaseAgent):
    """睡一小会儿，并把"我在哪个线程、什么时候开始/结束"写进结果。"""

    result_type = "slow"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        started = time.perf_counter()
        thread = threading.get_ident()
        time.sleep(SLEEP_SECONDS)
        return {"agent": self.name, "thread": thread, "started": started, "ended": time.perf_counter()}


def _agent_class(name: str) -> type[BaseAgent]:
    return type(f"Slow{name}", (_SlowAgent,), {"name": name})


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    import app.agents.base_agent as base_agent

    monkeypatch.setattr(base_agent, "RETRY_BACKOFF_SECONDS", 0)


@pytest.fixture
def registry() -> UnifiedRegistry:
    reg = UnifiedRegistry()
    strategies = ["layered", "langgraph_layered"]
    for name in ALL_AGENTS:
        reg.register(AgentSpec(name, _agent_class(name), strategies=strategies))
    return reg


@pytest.fixture
def task(db_session, make_resume, make_jd) -> dict[str, int]:
    resume_id, jd_id = make_resume(), make_jd()
    row = AgentTask(user_id=1, resume_id=resume_id, jd_id=jd_id, status="pending")
    db_session.add(row)
    db_session.commit()
    return {"task_id": row.id, "resume_id": resume_id, "jd_id": jd_id}


def _run(db_session, registry, task, strategy_name):
    return StrategyFactory.create(strategy_name, registry).run(
        task["task_id"], task["resume_id"], task["jd_id"], 1, db_session
    )


def _intervals(db_session, names):
    out = {}
    for name in names:
        data = db_session.query(AgentMessage).filter_by(agent_name=name).one().output_data
        out[name] = (data["started"], data["ended"], data["thread"])
    return out


# ===================== 拓扑本身 =====================


def test_layered_graph_has_a_fanout_not_a_chain(registry):
    """节点名里必须出现 route/work/join 三件套；只有链的话不会有 work_*。"""
    from app.orchestration.langgraph_flow import _build_layered_graph

    strategy = StrategyFactory.create("langgraph_layered", registry)
    names = set(_build_layered_graph(strategy, db=None).nodes)

    assert {"route_0", "work_0", "join_0"}.issubset(names)
    assert not [n for n in names if n.startswith("level_")]
    assert len([n for n in names if n.startswith("route_")]) == len(strategy.EXECUTION_LEVELS)


# ===================== 扇出真的并发 =====================


def test_same_level_branches_overlap_in_time(db_session, registry, task):
    _run(db_session, registry, task, "langgraph_layered")

    first, second = _intervals(db_session, LEVEL_0).values()

    assert first[2] != second[2], "同层两个节点跑在同一线程"
    assert max(first[0], second[0]) < min(first[1], second[1]), "时间区间不重叠：层内其实是串行"


def test_levels_still_run_in_order(db_session, registry, task):
    """并发只发生在层内；MatchAgent 必须等第一层全部结束。"""
    _run(db_session, registry, task, "langgraph_layered")

    spans = _intervals(db_session, ALL_AGENTS)
    level_0_end = max(spans[name][1] for name in LEVEL_0)

    assert spans["MatchAgent"][0] > level_0_end
    assert min(spans[name][0] for name in ("InterviewAgent", "CareerAgent")) > spans["MatchAgent"][1]


# ===================== 写库仍在调用方线程 =====================


def test_every_node_is_persisted_once_under_the_tasks_run(db_session, registry, task):
    """分支若自己也写库，这里就会出现重复行——行数严格等于节点数即是反证。"""
    result = _run(db_session, registry, task, "langgraph_layered")

    run = db_session.query(AgentRun).one()
    messages = db_session.query(AgentMessage).all()

    assert result["status"] == "completed"
    assert len(messages) == len(ALL_AGENTS)
    assert {m.run_id for m in messages} == {run.id}
    assert run.task_id == task["task_id"]
    assert db_session.query(AgentStepLog).filter_by(task_id=task["task_id"]).count() == len(ALL_AGENTS)


def test_langgraph_and_native_layered_agree(db_session, registry, task):
    """换引擎不能换结果：两边跑完得到同一批节点与同一状态。"""
    other = AgentTask(user_id=1, resume_id=task["resume_id"], jd_id=task["jd_id"], status="pending")
    db_session.add(other)
    db_session.commit()

    native = LayeredParallelStrategy(registry).run(other.id, task["resume_id"], task["jd_id"], 1, db_session)
    native_nodes = {m.agent_name for m in db_session.query(AgentMessage).all()}

    db_session.execute(delete(AgentMessage))
    db_session.execute(delete(AgentRun))
    db_session.execute(delete(AgentStepLog))
    db_session.commit()

    graphed = _run(db_session, registry, task, "langgraph_layered")
    graphed_nodes = {m.agent_name for m in db_session.query(AgentMessage).all()}

    assert native["status"] == graphed["status"] == "completed"
    assert native_nodes == graphed_nodes == set(ALL_AGENTS)
