"""LangGraph-backed orchestration flows。

两条流水线各有一张图：

- linear：7 个节点串成一条链（关键节点失败即提前 END）——它本来就是线性的，
  画成链是诚实表达，不为了"看起来 agentic"塞假分支。
- layered：每层是真拓扑 `route_i ──Send──▶ work_i ×N ──▶ join_i`。
  扇出交给图，而不是藏在一个节点里的 ThreadPoolExecutor 里（那样图画的是链、
  跑的也是链，只是换了个写法）。

线程归属是实测过的（langgraph 1.2.10）：普通节点跑在调用方线程，只有 Send 分支
跑在别的工作线程上。所以分支节点**只读不写**：每个分支自己开 session 跑 run_node，
所有落库集中在 join（调用方线程），避免多个分支共用同一个 SQLAlchemy Session。
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from sqlalchemy.orm import Session

from app.agents.base_agent import NodeOutcome, record_node_outcome
from app.core.database import SessionLocal
from app.models.agent import AgentStepLog, AgentTask
from app.models.agent_run import AgentRun
from app.orchestration.context import AgentContext
from app.orchestration.strategies import _orchestrator_result, _result_from_outcome
from app.utils.time_helper import utc_now

if TYPE_CHECKING:
    from app.orchestration.strategies import (
        LangGraphLayeredStrategy,
        LangGraphLinearStrategy,
    )

try:
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Overwrite, Send

    LANGGRAPH_AVAILABLE = True
except ImportError:
    END = "__end__"
    START = "__start__"
    StateGraph = None
    Overwrite = None
    Send = None
    LANGGRAPH_AVAILABLE = False


class LinearGraphState(TypedDict):
    task_id: int
    context: AgentContext
    steps: list[dict[str, Any]]
    failed_critical: bool
    error: str


class LayeredGraphState(TypedDict):
    """分层图状态。

    `branch` 是并发通道（每个扇出分支各写一次，必须用 reducer 累加），
    `steps` 只由汇聚节点整体重写，所以不需要 reducer。
    """

    task_id: int
    run_id: int
    context: AgentContext
    steps: list[dict[str, Any]]
    branch: Annotated[list[dict[str, Any]], operator.add]
    log_ids: dict[str, int]
    level: int
    step_index: int
    failed: bool
    error: str


def _is_task_cancelled(db: Session, task_id: int) -> bool:
    task = db.get(AgentTask, task_id)
    return bool(task and task.status == "cancelled")


def run_linear_graph(
    strategy: LangGraphLinearStrategy,
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: int | None,
    db: Session,
    run_id: int | None = None,
) -> dict[str, Any]:
    """Execute the linear pipeline with a LangGraph state graph."""
    _ensure_langgraph_available("langgraph_linear")

    task = db.get(AgentTask, task_id)
    if not task:
        return _task_not_found(task_id)

    run = strategy._ensure_run(db, task_id, resume_id, jd_id, run_id)
    context = strategy._new_context(task_id, run.id, resume_id, jd_id, user_id, db)
    graph = _build_linear_graph(strategy, db)
    app = graph.compile()
    final_state = app.invoke(
        {
            "task_id": task_id,
            "context": context,
            "steps": [],
            "failed_critical": False,
            "error": "",
        }
    )
    return _finalize_linear_run(strategy, db, task, run, resume_id, jd_id, user_id, final_state)


def run_layered_graph(
    strategy: LangGraphLayeredStrategy,
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: int | None,
    db: Session,
    run_id: int | None = None,
) -> dict[str, Any]:
    """Execute the layered pipeline with sequential graph levels."""
    _ensure_langgraph_available("langgraph_layered")

    task = db.get(AgentTask, task_id)
    if not task:
        return _task_not_found(task_id)

    run = strategy._ensure_run(db, task_id, resume_id, jd_id, run_id)
    context = strategy._new_context(task_id, run.id, resume_id, jd_id, user_id, db)
    graph = _build_layered_graph(strategy, db)
    app = graph.compile()
    final_state = app.invoke(
        {
            "task_id": task_id,
            "run_id": run.id,
            "context": context,
            "steps": [],
            "branch": [],
            "log_ids": {},
            "level": 0,
            "step_index": 0,
            "failed": False,
            "error": "",
        }
    )
    return _finalize_layered_run(strategy, db, task, run, resume_id, jd_id, user_id, final_state)


def _build_linear_graph(strategy: LangGraphLinearStrategy, db: Session) -> StateGraph:
    graph = StateGraph(LinearGraphState)

    for step_index, agent_name in enumerate(strategy.AGENT_ORDER, start=1):
        graph.add_node(agent_name, _make_linear_agent_node(strategy, db, agent_name, step_index))

    return _wire_sequential_graph(graph, strategy.AGENT_ORDER, "failed_critical")


def _build_layered_graph(strategy: LangGraphLayeredStrategy, db: Session) -> StateGraph:
    """每层画成 `route ──Send──▶ work ×N ──▶ join`，扇出交给图。

    之前是每个层级一个节点、节点内部自己开 ThreadPoolExecutor：图画的是链、跑的
    也是链，"分层并行"只是写在注释里。
    """
    graph = StateGraph(LayeredGraphState)
    levels = strategy.EXECUTION_LEVELS

    graph.add_edge(START, "route_0")

    for level_index, agent_names in enumerate(levels):
        route, work, join = _level_nodes(level_index)

        graph.add_node(route, _make_level_router(strategy, db, agent_names))
        graph.add_node(work, _make_level_branch(strategy))
        graph.add_node(join, _make_level_join(strategy, db))
        graph.add_conditional_edges(
            route,
            _make_fanout(work, join),
            {work: work, join: join, END: END},
        )
        graph.add_edge(work, join)

        next_route, _, _ = _level_nodes(level_index + 1)
        tail = next_route if level_index + 1 < len(levels) else END
        graph.add_conditional_edges(join, _make_next_level(tail), {tail: tail, END: END})

    return graph


def _level_nodes(level_index: int) -> tuple[str, str, str]:
    return f"route_{level_index}", f"work_{level_index}", f"join_{level_index}"


def _make_level_router(strategy: LangGraphLayeredStrategy, db: Session, agent_names: list[str]):
    def _run(state: LayeredGraphState) -> LayeredGraphState:
        context = state["context"]

        if _is_task_cancelled(db, state["task_id"]):
            return {"failed": True, "error": "Cancelled by user", "log_ids": {}}

        step_index = state["step_index"]
        log_ids = {}
        for offset, name in enumerate(agent_names, start=1):
            log = strategy._create_step_log(db, state["task_id"], name, step_index + offset, "running", context=context)
            log_ids[name] = log.id

        # branch 用 Overwrite 清空：上一级扇出的结果不该被这一级重复消费
        return {"log_ids": log_ids, "step_index": step_index + len(agent_names), "branch": Overwrite([])}

    return _run


def _make_fanout(work_node: str, join_node: str):
    def _route(state: LayeredGraphState):
        if state["failed"]:
            return END
        log_ids = state["log_ids"]
        if not log_ids:
            return join_node
        return [
            Send(
                work_node,
                {
                    "agent": agent_name,
                    "log_id": log_id,
                    "context": state["context"].fork(),
                    "task_id": state["task_id"],
                    "run_id": state["run_id"],
                },
            )
            for agent_name, log_id in log_ids.items()
        ]

    return _route


def _make_level_branch(strategy: LangGraphLayeredStrategy):
    def _run(payload: dict[str, Any]) -> dict[str, Any]:
        """扇出分支：跑在工作线程，只读不写。

        落库全留给 join —— 多个分支共用调用方那个 SQLAlchemy Session 是不安全的。
        """
        agent_name = payload["agent"]
        node_context = payload["context"]
        db = SessionLocal()
        try:
            agent = strategy._make_agent(agent_name, db)
            node_context = node_context.with_db(db)
            outcome = agent.run_node(node_context)
        except Exception as exc:  # 分支自身炸掉也要成为 failed 节点，不能把整层带走
            outcome = NodeOutcome(agent_name=agent_name, status="failed", error=str(exc)[:500])
        finally:
            db.close()

        return {
            "branch": [
                {
                    "agent": agent_name,
                    "log_id": payload["log_id"],
                    "outcome": outcome,
                    "input_data": node_context.to_log_dict(),
                }
            ]
        }

    return _run


def _make_level_join(strategy: LangGraphLayeredStrategy, db: Session):
    def _run(state: LayeredGraphState) -> LayeredGraphState:
        context = state["context"]
        steps = list(state["steps"])
        failed = state["failed"]
        error = state["error"]

        for record in state["branch"]:
            agent_name = record["agent"]
            outcome = record["outcome"]
            agent = strategy._make_agent(agent_name, db)
            record_node_outcome(db, state["run_id"], agent, context, outcome, input_data=record["input_data"])
            log = db.get(AgentStepLog, record["log_id"])
            if log is not None:
                strategy._update_step_log(db, log, outcome)
            steps.append(_result_from_outcome(agent_name, outcome))
            if outcome.succeeded:
                context.record_agent_output(agent_name, outcome.result)
            elif not failed:
                failed = True
                error = outcome.error or f"{agent_name} failed"

        return {"steps": steps, "failed": failed, "error": error, "log_ids": {}, "branch": Overwrite([])}

    return _run


def _make_next_level(next_node: str):
    def _route(state: LayeredGraphState) -> str:
        return END if state["failed"] else next_node

    return _route


def _wire_sequential_graph(graph: StateGraph, node_names: list[str], failure_key: str) -> StateGraph:
    graph.add_edge(START, node_names[0])

    for index, node_name in enumerate(node_names):
        if index == len(node_names) - 1:
            graph.add_edge(node_name, END)
            continue

        next_node = node_names[index + 1]
        graph.add_conditional_edges(
            node_name,
            _make_next_edge(next_node, failure_key),
            {
                next_node: next_node,
                END: END,
            },
        )

    return graph


def _make_linear_agent_node(
    strategy: LangGraphLinearStrategy,
    db: Session,
    agent_name: str,
    step_index: int,
):
    def _run(state: LinearGraphState) -> LinearGraphState:
        context = state["context"]
        steps = list(state["steps"])

        if _is_task_cancelled(db, state["task_id"]):
            return {
                **state,
                "steps": steps,
                "failed_critical": True,
                "error": "Cancelled by user",
            }

        if not strategy._should_execute(context, agent_name):
            steps.append(
                {
                    "agent_name": agent_name,
                    "status": "skipped",
                    "result": {"reason": "Skipped by intent routing"},
                    "error": "",
                }
            )
            strategy._create_step_log(
                db, state["task_id"], agent_name, step_index, "skipped", {"skipped": True}, context
            )
            return {
                **state,
                "steps": steps,
                "context": context,
            }

        log = strategy._create_step_log(db, state["task_id"], agent_name, step_index, "running", context=context)
        critical = strategy.registry.is_critical(agent_name)
        result = strategy._execute_agent_node(db, log, agent_name, context)
        steps.append(result)

        failed_critical = state["failed_critical"]
        error = state["error"]
        if result["status"] == "success":
            context.record_agent_output(agent_name, result["result"])
            if agent_name == "IntentAgent":
                strategy._apply_plan(context, strategy.AGENT_ORDER)
        elif critical:
            failed_critical = True
            error = result.get("error", "") or f"{agent_name} failed"

        return {
            **state,
            "context": context,
            "steps": steps,
            "failed_critical": failed_critical,
            "error": error,
        }

    return _run


def _make_next_edge(next_node: str, failure_key: str):
    def _route(state: dict[str, Any]) -> str:
        return END if state[failure_key] else next_node

    return _route


def _finalize_linear_run(
    strategy: LangGraphLinearStrategy,
    db: Session,
    task: AgentTask,
    run: AgentRun,
    resume_id: int,
    jd_id: int,
    user_id: int | None,
    state: LinearGraphState,
) -> dict[str, Any]:
    context = state["context"]
    step_results = state["steps"]
    failed_critical = state["failed_critical"]

    record_id = None
    if task.status == "cancelled":
        task.error_msg = "Cancelled by user"
    elif not failed_critical:
        record_id = strategy._save_analysis_record(db, resume_id, jd_id, user_id, context)

    if task.status == "cancelled":
        pass
    elif failed_critical:
        task.status = "failed"
        task.error_msg = state["error"] or "Critical step failed"
    else:
        failed_steps = [step for step in step_results if step["status"] == "failed"]
        task.status = "partial" if failed_steps else "completed"
        task.error_msg = None

    task.end_time = utc_now()
    task.intent = context.intent
    task.intent_detail = context.intent_detail
    task.plan = context.plan
    task.final_report = context.final_report
    task.analysis_record_id = record_id
    db.add(task)
    db.commit()

    run.summary_report = context.final_report or {}
    db.add(run)
    db.commit()
    strategy._finish_run(
        db,
        run,
        "failed" if (failed_critical or task.status == "cancelled") else "completed",
        task.error_msg,
    )

    return _orchestrator_result(
        status=task.status,
        task_id=task.id,
        record_id=record_id,
        steps=step_results,
        final_report=context.final_report or {},
        error=task.error_msg or "",
    )


def _finalize_layered_run(
    strategy: LangGraphLayeredStrategy,
    db: Session,
    task: AgentTask,
    run: AgentRun,
    resume_id: int,
    jd_id: int,
    user_id: int | None,
    state: LayeredGraphState,
) -> dict[str, Any]:
    context = state["context"]
    step_results = state["steps"]

    if task.status == "cancelled":
        run.status = "failed"
        run.error_msg = "Cancelled by user"
        task.error_msg = "Cancelled by user"
        record_id = None
    elif state["failed"]:
        run.status = "failed"
        run.error_msg = state["error"] or "Layer execution failed"
        task.status = "failed"
        task.error_msg = run.error_msg
        record_id = None
    else:
        run.status = "completed"
        run.error_msg = None
        record_id = strategy._save_analysis_record(db, resume_id, jd_id, user_id, context)
        task.status = "completed"
        task.error_msg = None
        task.analysis_record_id = record_id

    run.summary_report = context.final_report or {}
    run.end_time = utc_now()
    db.add(run)

    task.end_time = utc_now()
    task.final_report = context.final_report
    db.add(task)
    db.commit()

    return _orchestrator_result(
        status=task.status,
        task_id=task.id,
        record_id=task.analysis_record_id,
        steps=step_results,
        final_report=context.final_report or {},
        error=task.error_msg or "",
    )


def _task_not_found(task_id: int) -> dict[str, Any]:
    return _orchestrator_result(
        status="failed",
        task_id=task_id,
        record_id=None,
        steps=[],
        final_report={},
        error="Task not found",
    )


def _ensure_langgraph_available(strategy_name: str):
    if not LANGGRAPH_AVAILABLE or StateGraph is None:
        raise RuntimeError(
            f"langgraph is not installed, cannot run {strategy_name}. "
            "Install the new dependency from backend/requirements.txt first."
        )
