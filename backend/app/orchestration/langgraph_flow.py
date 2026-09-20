"""LangGraph-backed orchestration flows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from sqlalchemy.orm import Session

from app.agents.base_agent import record_node_outcome
from app.models.agent import AgentTask
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

    LANGGRAPH_AVAILABLE = True
except ImportError:
    END = "__end__"
    START = "__start__"
    StateGraph = None
    LANGGRAPH_AVAILABLE = False


class LinearGraphState(TypedDict):
    task_id: int
    context: AgentContext
    steps: list[dict[str, Any]]
    failed_critical: bool
    error: str


class LayeredGraphState(TypedDict):
    task_id: int
    run_id: int
    context: AgentContext
    steps: list[dict[str, Any]]
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
    graph = StateGraph(LayeredGraphState)
    node_names: list[str] = []

    for level_index, agent_names in enumerate(strategy.EXECUTION_LEVELS):
        node_name = f"level_{level_index}"
        node_names.append(node_name)
        graph.add_node(node_name, _make_layer_node(strategy, db, agent_names))

    return _wire_sequential_graph(graph, node_names, "failed")


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


def _make_layer_node(
    strategy: LangGraphLayeredStrategy,
    db: Session,
    agent_names: list[str],
):
    def _run(state: LayeredGraphState) -> LayeredGraphState:
        context = state["context"]
        steps = list(state["steps"])
        next_step_index = state["step_index"]

        if _is_task_cancelled(db, state["task_id"]):
            return {
                **state,
                "context": context,
                "steps": steps,
                "step_index": next_step_index,
                "failed": True,
                "error": "Cancelled by user",
            }

        # 整层先落 running 日志，再并发执行节点
        logs = {
            name: strategy._create_step_log(
                db, state["task_id"], name, next_step_index + i + 1, "running", context=context
            )
            for i, name in enumerate(agent_names)
        }
        next_step_index += len(agent_names)

        for name, (agent, node_context, outcome) in strategy._run_level(agent_names, context, db).items():
            record_node_outcome(db, state["run_id"], agent, node_context, outcome)
            strategy._update_step_log(db, logs[name], outcome)
            steps.append(_result_from_outcome(name, outcome))
            if outcome.succeeded:
                context.record_agent_output(name, outcome.result)

        failed = state["failed"]
        error = state["error"]
        for name in agent_names:
            result = next((item for item in reversed(steps) if item.get("agent_name") == name), None)
            if isinstance(result, dict) and result.get("status") == "failed":
                failed = True
                error = result.get("error", "") or f"{name} failed"
                break

        return {
            **state,
            "context": context,
            "steps": steps,
            "step_index": next_step_index,
            "failed": failed,
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
