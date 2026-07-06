# -*- coding: utf-8 -*-
"""LangGraph-backed orchestration flows."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, TYPE_CHECKING, TypedDict

from sqlalchemy.orm import Session

from app.models.agent import AgentTask
from app.models.agent_run import AgentRun
from app.orchestration.context import AgentContext
from app.orchestration.strategies import _agent_result, _orchestrator_result
from app.utils.time_helper import utc_now

if TYPE_CHECKING:
    from app.orchestration.strategies import (
        LangGraphLayeredStrategy,
        LangGraphLinearStrategy,
        LangGraphStepByStepStrategy,
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
    steps: List[Dict[str, Any]]
    failed_critical: bool
    error: str


class LayeredGraphState(TypedDict):
    task_id: int
    run_id: int
    context: AgentContext
    steps: List[Dict[str, Any]]
    step_index: int
    failed: bool
    error: str


class StepGraphState(TypedDict):
    task_id: int
    context: AgentContext
    steps: List[Dict[str, Any]]
    failed_critical: bool
    error: str


def _is_task_cancelled(db: Session, task_id: int) -> bool:
    task = db.get(AgentTask, task_id)
    return bool(task and task.status == "cancelled")


def run_linear_graph(
    strategy: "LangGraphLinearStrategy",
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: Optional[int],
    db: Session,
) -> Dict[str, Any]:
    """Execute the linear pipeline with a LangGraph state graph."""
    _ensure_langgraph_available("langgraph_linear")

    task = db.get(AgentTask, task_id)
    if not task:
        return _task_not_found(task_id)

    context = AgentContext.for_analysis(resume_id, jd_id, user_id=user_id, db=db)
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
    return _finalize_linear_run(strategy, db, task, resume_id, jd_id, user_id, final_state)


def run_layered_graph(
    strategy: "LangGraphLayeredStrategy",
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: Optional[int],
    db: Session,
) -> Dict[str, Any]:
    """Execute the layered pipeline with sequential graph levels."""
    _ensure_langgraph_available("langgraph_layered")

    task = db.get(AgentTask, task_id)
    if not task:
        return _task_not_found(task_id)

    run = AgentRun(
        resume_id=resume_id or 0,
        jd_id=jd_id or 0,
        user_request="langgraph_layered",
        status="running",
        start_time=utc_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    context = AgentContext.for_analysis(resume_id, jd_id, user_id=user_id, db=db)
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


def run_step_by_step_graph(
    strategy: "LangGraphStepByStepStrategy",
    task_id: int,
    resume_id: int,
    jd_id: int,
    user_id: Optional[int],
    db: Session,
) -> Dict[str, Any]:
    """Execute the step-by-step workflow with a LangGraph state graph."""
    _ensure_langgraph_available("langgraph_step_by_step")

    task = db.get(AgentTask, task_id)
    if not task:
        return _task_not_found(task_id)

    context = AgentContext.for_analysis(resume_id, jd_id, user_id=user_id, db=db)
    graph = _build_step_graph(strategy, db)
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
    return _finalize_step_run(strategy, db, task, resume_id, jd_id, user_id, final_state)


def _build_linear_graph(strategy: "LangGraphLinearStrategy", db: Session) -> StateGraph:
    graph = StateGraph(LinearGraphState)

    for step_index, agent_name in enumerate(strategy.AGENT_ORDER, start=1):
        graph.add_node(agent_name, _make_linear_agent_node(strategy, db, agent_name, step_index))

    return _wire_sequential_graph(graph, strategy.AGENT_ORDER, "failed_critical")


def _build_layered_graph(strategy: "LangGraphLayeredStrategy", db: Session) -> StateGraph:
    graph = StateGraph(LayeredGraphState)
    node_names: List[str] = []

    for level_index, agent_names in enumerate(strategy.EXECUTION_LEVELS):
        node_name = f"level_{level_index}"
        node_names.append(node_name)
        graph.add_node(node_name, _make_layer_node(strategy, db, agent_names))

    return _wire_sequential_graph(graph, node_names, "failed")


def _build_step_graph(strategy: "LangGraphStepByStepStrategy", db: Session) -> StateGraph:
    graph = StateGraph(StepGraphState)
    node_names: List[str] = []

    for step_index, (step_name, step_func_name, critical) in enumerate(strategy.STEP_REGISTRY, start=1):
        node_name = f"step_{step_name}"
        node_names.append(node_name)
        graph.add_node(
            node_name,
            _make_step_node(strategy, db, step_name, step_func_name, step_index, critical),
        )

    return _wire_sequential_graph(graph, node_names, "failed_critical")


def _wire_sequential_graph(graph: StateGraph, node_names: List[str], failure_key: str) -> StateGraph:
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
    strategy: "LangGraphLinearStrategy",
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
            strategy._create_step_log(db, state["task_id"], agent_name, step_index, "skipped", {"skipped": True})
            return {
                **state,
                "steps": steps,
                "context": context,
            }

        log = strategy._create_step_log(db, state["task_id"], agent_name, step_index, "running")
        critical = strategy.registry.is_critical(agent_name)
        result = strategy._execute_agent_with_retry(db, state["task_id"], log, agent_name, context, critical)
        steps.append(result)

        failed_critical = state["failed_critical"]
        error = state["error"]
        if result["status"] == "success":
            context.record_agent_output(agent_name, result["result"])
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
    strategy: "LangGraphLayeredStrategy",
    db: Session,
    agent_names: List[str],
):
    def _run(state: LayeredGraphState) -> LayeredGraphState:
        context = state["context"]
        prior = context.fork()
        steps = list(state["steps"])
        next_step_index = state["step_index"]
        planned_runs = []

        if _is_task_cancelled(db, state["task_id"]):
            return {
                **state,
                "context": context,
                "steps": steps,
                "step_index": next_step_index,
                "failed": True,
                "error": "Cancelled by user",
            }

        for agent_name in agent_names:
            next_step_index += 1
            log = strategy._create_step_log(db, state["task_id"], agent_name, next_step_index, "running")
            planned_runs.append((agent_name, log))

        if len(planned_runs) == 1:
            agent_name, log = planned_runs[0]
            result = strategy._run_one_agent(agent_name, state["run_id"], prior.fork())
            strategy._update_log_from_result(db, log, result)
            steps.append(result)
            if result.get("status") == "success":
                context.record_agent_output(agent_name, result.get("result", {}))
        else:
            results_by_name: Dict[str, Dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=len(planned_runs)) as executor:
                futures = {
                    executor.submit(strategy._run_one_agent, agent_name, state["run_id"], prior.fork()): agent_name
                    for agent_name, _ in planned_runs
                }
                for future in as_completed(futures):
                    agent_name = futures[future]
                    results_by_name[agent_name] = future.result()

            for agent_name, log in planned_runs:
                result = results_by_name[agent_name]
                strategy._update_log_from_result(db, log, result)
                steps.append(result)
                if result.get("status") == "success":
                    context.record_agent_output(agent_name, result.get("result", {}))

        failed = state["failed"]
        error = state["error"]
        for agent_name, _ in planned_runs:
            result = next((item for item in reversed(steps) if item.get("agent_name") == agent_name), None)
            if isinstance(result, dict) and result.get("status") == "failed":
                failed = True
                error = result.get("error", "") or f"{agent_name} failed"
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


def _make_step_node(
    strategy: "LangGraphStepByStepStrategy",
    db: Session,
    step_name: str,
    step_func_name: str,
    step_index: int,
    critical: bool,
):
    def _run(state: StepGraphState) -> StepGraphState:
        context = state["context"]
        steps = list(state["steps"])

        if _is_task_cancelled(db, state["task_id"]):
            return {
                **state,
                "context": context,
                "steps": steps,
                "failed_critical": True,
                "error": "Cancelled by user",
            }

        log = strategy._create_step_log(db, state["task_id"], step_name, step_index, "running")

        if not strategy._should_execute_step(context, step_name):
            reason = "Skipped by intent routing"
            strategy._complete_step_log(db, log, {"skipped": True, "reason": reason}, 0)
            steps.append(_agent_result(step_name, "skipped", {"reason": reason}))
            return {
                **state,
                "context": context,
                "steps": steps,
            }

        success = strategy._execute_step_with_retry(
            db,
            state["task_id"],
            log,
            step_func_name,
            context,
            step_name,
            critical,
        )
        if success:
            steps.append(_agent_result(step_name, "success", context.get(strategy._ctx_key(step_name))))
            return {
                **state,
                "context": context,
                "steps": steps,
            }

        error = log.error_msg or f"{step_name} failed"
        steps.append(_agent_result(step_name, "failed", error=error))
        return {
            **state,
            "context": context,
            "steps": steps,
            "failed_critical": state["failed_critical"] or critical,
            "error": error if critical else state["error"],
        }

    return _run


def _make_next_edge(next_node: str, failure_key: str):
    def _route(state: Dict[str, Any]) -> str:
        return END if state[failure_key] else next_node

    return _route


def _finalize_linear_run(
    strategy: "LangGraphLinearStrategy",
    db: Session,
    task: AgentTask,
    resume_id: int,
    jd_id: int,
    user_id: Optional[int],
    state: LinearGraphState,
) -> Dict[str, Any]:
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
    task.final_report = context.final_report
    task.analysis_record_id = record_id
    db.add(task)
    db.commit()

    return _orchestrator_result(
        status=task.status,
        task_id=task.id,
        record_id=record_id,
        steps=step_results,
        final_report=context.final_report or {},
        error=task.error_msg or "",
    )


def _finalize_layered_run(
    strategy: "LangGraphLayeredStrategy",
    db: Session,
    task: AgentTask,
    run: AgentRun,
    resume_id: int,
    jd_id: int,
    user_id: Optional[int],
    state: LayeredGraphState,
) -> Dict[str, Any]:
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


def _finalize_step_run(
    strategy: "LangGraphStepByStepStrategy",
    db: Session,
    task: AgentTask,
    resume_id: int,
    jd_id: int,
    user_id: Optional[int],
    state: StepGraphState,
) -> Dict[str, Any]:
    context = state["context"]
    step_results = state["steps"]

    if task.status == "cancelled":
        task.error_msg = "Cancelled by user"
        record_id = None
    elif state["failed_critical"]:
        task.status = "failed"
        task.error_msg = state["error"] or "Critical step failed"
        record_id = None
    else:
        record_id = strategy._save_analysis_record(db, resume_id, jd_id, user_id, context)
        task.status = "completed"
        task.error_msg = None
        task.analysis_record_id = record_id

    task.end_time = utc_now()
    task.intent = context.intent
    task.intent_detail = context.intent_detail
    task.plan = context.plan
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


def _task_not_found(task_id: int) -> Dict[str, Any]:
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
