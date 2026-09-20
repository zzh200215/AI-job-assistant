"""执行策略抽象与两种具体实现

- LinearStrategy:          线性流水线（smart_orchestrator 主线，`/api/analysis/full`）
- LayeredParallelStrategy: 分层并行（legacy `/api/multi-agent/*`）

每种流水线各有一个 LangGraph 孪生实现（`langgraph_flow.py`），由
`ORCHESTRATION_ENGINE` 切换；曾经还有第三条 `step_by_step`（11 个绕过 agent 类的
裸步骤），它与前两条重复且是 `RetrievalLog`/`SelfCheckLog` 唯一的（空）写入点，
已删除。

两种策略共用 orchestration.registry.UnifiedRegistry 中的 Agent 注册表，
并继承 ExecutionStrategy 提供的通用辅助方法（日志、落库、保存记录等）。

Agent 节点只有一个入口：BaseAgent.execute()（内部 = run_node + 落 AgentMessage）。
分层并行策略因为工作线程不能共用 session，改走同一条路径的两个半段：
线程里 run_node()，主线程 record_node_outcome()。
"""

import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent, NodeOutcome, record_node_outcome
from app.core.database import SessionLocal
from app.models.agent import AgentStepLog, AgentTask
from app.models.agent_run import AgentRun
from app.models.history import AnalysisRecord
from app.orchestration.context import AgentContext
from app.orchestration.plan import as_plan_rows, plan_from_intent
from app.orchestration.registry import DEFAULT_REGISTRY, UnifiedRegistry
from app.utils.time_helper import utc_now

logger = logging.getLogger(__name__)

# ===================== 通用辅助 =====================


def _agent_result(agent_name: str, status: str, result: Any = None, error: str = "") -> dict[str, Any]:
    return {
        "agent_name": agent_name,
        "status": status,
        "result": result or {},
        "error": error,
    }


def _result_from_outcome(agent_name: str, outcome: NodeOutcome) -> dict[str, Any]:
    return _agent_result(
        agent_name,
        "success" if outcome.succeeded else "failed",
        outcome.result,
        outcome.error,
    )


def _orchestrator_result(
    status: str,
    task_id: int,
    record_id: int | None = None,
    steps: list[dict] = None,
    final_report: dict = None,
    error: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "task_id": task_id,
        "record_id": record_id,
        "steps": steps or [],
        "final_report": final_report or {},
        "error": error,
    }


class ExecutionStrategy(ABC):
    """执行策略抽象基类

    子类只需实现 `name` 属性和 `run()` 方法，
    通用能力（Agent 执行、日志、重试、保存记录、意图裁剪）由基类提供。
    """

    def __init__(self, registry: UnifiedRegistry):
        self.registry = registry

    @property
    @abstractmethod
    def name(self) -> str:
        """策略标识名（如 'linear' / 'langgraph_linear' / 'layered'）"""
        pass

    @abstractmethod
    def run(
        self,
        task_id: int,
        resume_id: int,
        jd_id: int,
        user_id: int,
        db: Session,
        run_id: int | None = None,
    ) -> dict[str, Any]:
        """执行完整编排流程，返回统一格式结果。run_id 给出时复用该 agent_run 行。"""
        pass

    # -------------------- 通用 Agent 执行 --------------------

    def _make_agent(self, agent_name: str, db: Session) -> BaseAgent:
        spec = self.registry.get(agent_name)
        return spec.agent_class(db=db)

    def _execute_agent_node(
        self, db: Session, log: AgentStepLog, agent_name: str, context: AgentContext
    ) -> dict[str, Any]:
        """跑一个节点：入口只有 BaseAgent.execute()，重试也在它里面。

        返回统一格式给上层判断 critical 与否；AgentMessage 由 execute() 落库。
        """
        if self._is_task_cancelled(db, log.task_id):
            self._fail_step_log(db, log, "Cancelled before agent execution")
            return _agent_result(agent_name, "failed", error="Cancelled by user")

        agent = self._make_agent(agent_name, db)
        outcome = agent.execute(context.run_id, context.with_db(db))
        self._update_step_log(db, log, outcome)
        return _result_from_outcome(agent_name, outcome)

    def _update_step_log(self, db: Session, log: AgentStepLog, outcome: NodeOutcome) -> None:
        """把节点终态同步到步骤日志（前端轮询看的是这条，AgentMessage 是节点流水）。"""
        log.status = "completed" if outcome.succeeded else "failed"
        log.output_data = outcome.result
        log.error_msg = outcome.error or None
        log.retry_count = max(0, outcome.attempts - 1)
        log.started_at = log.started_at or outcome.started_at
        log.completed_at = utc_now()
        log.duration_ms = outcome.duration_ms
        db.add(log)
        db.commit()

    def _fail_step_log(self, db: Session, log: AgentStepLog, error_msg: str) -> None:
        log.status = "failed"
        log.error_msg = error_msg
        log.completed_at = utc_now()
        db.add(log)
        db.commit()

    # -------------------- 运行记录 --------------------

    def _new_context(
        self, task_id: int, run_id: int | None, resume_id: int, jd_id: int, user_id: int | None, db: Session
    ) -> AgentContext:
        """每次编排出发的上下文：带 task/run 归属，节点内的 LLM 调用才能被反查。"""
        context = AgentContext.for_analysis(
            resume_id,
            jd_id,
            user_id=user_id,
            db=db,
            task_id=task_id,
            run_id=run_id,
        )
        return context

    def _ensure_run(
        self,
        db: Session,
        task_id: int,
        resume_id: int,
        jd_id: int,
        run_id: int | None = None,
    ) -> AgentRun:
        """一个编排任务对应一条 agent_run，节点消息挂在它下面。

        调用方（legacy /api/multi-agent 入口）已经建好 run 时复用同一行：否则前端
        轮询的 run 与真正写消息的 run 是两行，明细永远是空的。
        """
        if run_id:
            existing = db.get(AgentRun, run_id)
            if existing:
                if existing.task_id is None:
                    existing.task_id = task_id
                    db.add(existing)
                    db.commit()
                return existing

        run = AgentRun(
            resume_id=resume_id or 0,
            jd_id=jd_id or 0,
            task_id=task_id,
            status="running",
            dispatch_reason=f"strategy={self.name}",
            start_time=utc_now(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def _finish_run(self, db: Session, run: AgentRun, status: str, error: str | None = None) -> None:
        run.status = status
        run.error_msg = error
        run.end_time = utc_now()
        db.add(run)
        db.commit()

    # -------------------- 日志 & 记录 --------------------

    def _create_step_log(
        self,
        db: Session,
        task_id: int,
        step_name: str,
        step_index: int,
        status: str = "pending",
        output_data: dict = None,
        context: AgentContext | None = None,
    ) -> AgentStepLog:
        log = AgentStepLog(
            task_id=task_id,
            step_name=step_name,
            step_index=step_index,
            status=status,
            input_data=(
                {"resume_id": context.resume_id, "jd_id": context.jd_id, "user_id": context.user_id} if context else {}
            ),
            output_data=output_data,
            started_at=utc_now() if status == "running" else None,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    def _save_analysis_record(
        self,
        db: Session,
        resume_id: int,
        jd_id: int,
        user_id: int,
        context: AgentContext,
    ) -> int:
        """将编排结果写入 AnalysisRecord，返回 record_id"""
        match_result = context.match_result or {}
        optimize_result = context.optimize_result or {}
        interview_result = context.interview_result or {}

        record = AnalysisRecord(
            user_id=user_id,
            resume_id=resume_id,
            jd_id=jd_id,
            match_score=int(match_result.get("match_score", 0)),
            match_report=match_result,
            optimize_suggestions=optimize_result,
            interview_questions=interview_result,
            remark=f"{self.name} 策略分析",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.id

    # -------------------- 意图裁剪 --------------------

    def _apply_plan(self, context: AgentContext, agent_order: list[str]) -> dict[str, Any]:
        """意图识别一出结果就把计划定下来：后面跑哪些节点由它决定，不再各处猜。

        模型写了系统里不存在的节点名会被丢掉并计数——这份名单在 C2 之前还留着
        C4 删掉的步骤，静默丢弃等于让坏词汇表一直活着。
        """
        info = plan_from_intent(context.intent_detail, available_agents=agent_order)
        context.plan = as_plan_rows(info["steps"], info["agents"])
        context.required_steps = info["steps"]
        if info["dropped"]:
            logger.warning(
                "plan dropped unknown steps=%s (source=%s, intent=%s)",
                info["dropped"],
                info["source"],
                info["intent"],
            )
        return info

    def _should_execute(self, context: AgentContext, agent_name: str) -> bool:
        """计划里有的节点才跑；没有计划时退回意图硬编码表（C2 之前的行为）。

        `context.plan` 是 `plan_from_intent()` 规约出来的结果，已经是"本次真能执行"
        的节点集合，所以这里不再做二次猜测。
        """
        planned = {row.get("agent") for row in (context.plan or []) if isinstance(row, dict)}
        if planned:
            return agent_name in planned

        intent_data = context.intent_detail or {}
        intent = intent_data.get("intent", "full_analysis")

        # 意图识别和解析步骤始终执行
        if agent_name in ("IntentAgent", "ResumeParseAgent", "JDParseAgent", "ResumeAgent", "JobAgent"):
            return True

        # 全量分析：全部执行
        if not intent or intent == "full_analysis":
            return True

        # 按意图裁剪
        if intent == "resume_match_only" and agent_name in ("MatchAnalysisAgent", "MatchAgent", "SummaryAgent"):
            return True
        if intent == "optimize_only" and agent_name in ("ResumeOptimizeAgent", "SummaryAgent"):
            return True
        if intent == "interview_only" and agent_name in ("InterviewQuestionAgent", "InterviewAgent", "SummaryAgent"):
            return True

        # SummaryAgent 在有其他结果时始终执行
        if agent_name == "SummaryAgent":
            return any(
                (
                    context.match_result,
                    context.optimize_result,
                    context.interview_result,
                    context.career_result,
                )
            )

        return False

    def _is_task_cancelled(self, db: Session, task_id: int) -> bool:
        task = db.get(AgentTask, task_id)
        return bool(task and task.status == "cancelled")

    def _mark_task_cancelled(self, db: Session, task: AgentTask, message: str = "Cancelled by user") -> None:
        task.status = "cancelled"
        task.error_msg = message
        task.end_time = utc_now()
        db.add(task)
        db.commit()

    def _cancelled_result(
        self,
        task_id: int,
        step_results: list[dict[str, Any]],
        context: AgentContext | None = None,
        record_id: int | None = None,
    ) -> dict[str, Any]:
        return _orchestrator_result(
            status="cancelled",
            task_id=task_id,
            record_id=record_id,
            steps=step_results,
            final_report=(context.final_report if context else {}) or {},
            error="Cancelled by user",
        )


# ===================== 1) 线性策略 =====================


class LinearStrategy(ExecutionStrategy):
    """线性流水线策略

    按注册表顺序串行执行每个 Agent，支持意图裁剪跳过非必要步骤。
    对应原 smart_orchestrator 的实现。
    """

    AGENT_ORDER: list[str] = [
        "IntentAgent",
        "ResumeParseAgent",
        "JDParseAgent",
        "MatchAnalysisAgent",
        "ResumeOptimizeAgent",
        "InterviewQuestionAgent",
        "SummaryAgent",
    ]

    @property
    def name(self) -> str:
        return "linear"

    def run(
        self,
        task_id: int,
        resume_id: int,
        jd_id: int,
        user_id: int,
        db: Session,
        run_id: int | None = None,
    ) -> dict[str, Any]:
        task = db.get(AgentTask, task_id)
        if not task:
            return _orchestrator_result("failed", task_id, error="任务不存在")

        run = self._ensure_run(db, task_id, resume_id, jd_id, run_id)
        context = self._new_context(task_id, run.id, resume_id, jd_id, user_id, db)
        step_results: list[dict[str, Any]] = []
        failed_critical = False

        for step_index, agent_name in enumerate(self.AGENT_ORDER, start=1):
            if self._is_task_cancelled(db, task_id):
                self._mark_task_cancelled(db, task)
                self._finish_run(db, run, "failed", "Cancelled by user")
                return self._cancelled_result(task_id, step_results, context)

            if not self._should_execute(context, agent_name):
                reason = "不在本次计划里" if context.plan else "根据意图识别结果跳过"
                step_results.append(_agent_result(agent_name, "skipped", {"reason": reason}))
                self._create_step_log(db, task_id, agent_name, step_index, "skipped", {"skipped": True}, context)
                continue

            log = self._create_step_log(db, task_id, agent_name, step_index, "running", context=context)
            critical = self.registry.is_critical(agent_name)
            agent_result = self._execute_agent_node(db, log, agent_name, context)
            step_results.append(agent_result)

            if self._is_task_cancelled(db, task_id):
                self._mark_task_cancelled(db, task)
                self._finish_run(db, run, "failed", "Cancelled by user")
                return self._cancelled_result(task_id, step_results, context)

            if agent_result["status"] == "success":
                context.record_agent_output(agent_name, agent_result["result"])
                if agent_name == "IntentAgent":
                    self._apply_plan(context, self.AGENT_ORDER)
            else:
                if critical:
                    failed_critical = True
                    break

        record_id = None
        if not failed_critical:
            record_id = self._save_analysis_record(db, resume_id, jd_id, user_id, context)

        if failed_critical:
            task.status = "failed"
            task.error_msg = "关键步骤执行失败"
        else:
            failed_steps = [s for s in step_results if s["status"] == "failed"]
            task.status = "partial" if failed_steps else "completed"

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
        self._finish_run(
            db,
            run,
            "failed" if (failed_critical or task.status == "cancelled") else "completed",
            task.error_msg,
        )

        return _orchestrator_result(
            status=task.status,
            task_id=task_id,
            record_id=record_id,
            steps=step_results,
            final_report=context.final_report or {},
        )


class LangGraphLinearStrategy(LinearStrategy):
    """LangGraph-backed linear orchestration.

    复用现有 Agent 与日志逻辑，仅将流程控制切换为 StateGraph。
    """

    @property
    def name(self) -> str:
        return "langgraph_linear"

    def run(
        self,
        task_id: int,
        resume_id: int,
        jd_id: int,
        user_id: int,
        db: Session,
        run_id: int | None = None,
    ) -> dict[str, Any]:
        from app.orchestration.langgraph_flow import run_linear_graph

        return run_linear_graph(self, task_id, resume_id, jd_id, user_id, db, run_id)


# ===================== 2) 分层并行策略 =====================


class LayeredParallelStrategy(ExecutionStrategy):
    """分层并行策略

    按层级定义并行组，同层 Agent 并发执行，层间串行。
    对应原 agent_orchestrator 的实现。
    """

    # 执行层级 — 同一层可并行，不同层串行
    EXECUTION_LEVELS: list[list[str]] = [
        ["ResumeAgent", "JobAgent"],  # Level 0: 简历诊断 + 岗位分析
        ["MatchAgent"],  # Level 1: 匹配度评估
        ["InterviewAgent", "CareerAgent"],  # Level 2: 面试辅导 + 职业规划（并行）
        ["SummaryAgent"],  # Level 3: 结果汇总
    ]

    @property
    def name(self) -> str:
        return "layered"

    def run(
        self,
        task_id: int,
        resume_id: int,
        jd_id: int,
        user_id: int,
        db: Session,
        run_id: int | None = None,
    ) -> dict[str, Any]:
        task = db.get(AgentTask, task_id)
        if not task:
            return _orchestrator_result("failed", task_id, error="任务不存在")

        run = self._ensure_run(db, task_id, resume_id, jd_id, run_id)
        context = self._new_context(task_id, run.id, resume_id, jd_id, user_id, db)
        step_results: list[dict[str, Any]] = []
        step_index = 0

        for agent_names in self.EXECUTION_LEVELS:
            if self._is_task_cancelled(db, task_id):
                self._finish_run(db, run, "failed", "Cancelled by user")
                return self._cancelled_result(task_id, step_results, context)

            # 先给整层建 running 日志，再并发跑：否则并行时只看得见先完成的那一条
            logs = [
                (name, self._create_step_log(db, task_id, name, step_index + i + 1, "running", context=context))
                for i, name in enumerate(agent_names)
            ]
            step_index += len(agent_names)

            for name, outcome_rec in self._run_level(agent_names, context, db).items():
                agent, node_context, outcome = outcome_rec
                record_node_outcome(db, run.id, agent, node_context, outcome)
                log = next(log for log_name, log in logs if log_name == name)
                self._update_step_log(db, log, outcome)
                step_results.append(_result_from_outcome(name, outcome))
                if outcome.succeeded:
                    context.record_agent_output(name, outcome.result)

            failed = next(
                (item for item in step_results if item["agent_name"] in agent_names and item["status"] == "failed"),
                None,
            )
            if failed:
                error = f"{failed['agent_name']} 执行失败: {failed['error'] or '未知错误'}"
                self._finish_run(db, run, "failed", error)
                return _orchestrator_result("failed", task_id, steps=step_results, error=error)

        run.summary_report = context.final_report or {}
        db.add(run)
        db.commit()

        record_id = self._save_analysis_record(db, resume_id, jd_id, user_id, context)

        # 同步更新 AgentTask（供前端轮询）
        task.status = "completed"
        task.end_time = utc_now()
        task.final_report = context.final_report
        task.analysis_record_id = record_id
        db.add(task)
        db.commit()
        self._finish_run(db, run, "completed")

        return _orchestrator_result(
            "completed",
            task_id,
            record_id=record_id,
            steps=step_results,
            final_report=context.final_report or {},
        )

    def _run_level(
        self, agent_names: list[str], context: AgentContext, db: Session
    ) -> dict[str, tuple[BaseAgent, AgentContext, NodeOutcome]]:
        """同层并发执行：工作线程只跑 run_node（各自独立 session），落库留给主线程。"""
        prior = context.fork()
        if len(agent_names) == 1:
            return {agent_names[0]: self._run_one_agent(agent_names[0], prior)}

        results: dict[str, tuple[BaseAgent, AgentContext, NodeOutcome]] = {}
        with ThreadPoolExecutor(max_workers=len(agent_names)) as ex:
            futures = {ex.submit(self._run_one_agent, name, prior.fork()): name for name in agent_names}
            for fut in as_completed(futures):
                results[futures[fut]] = fut.result()
        return results

    def _run_one_agent(self, agent_name: str, context: AgentContext) -> tuple[BaseAgent, AgentContext, NodeOutcome]:
        """在独立 DB Session 中执行单个 Agent 节点（不写库，线程安全）"""
        db = SessionLocal()
        try:
            agent = self._make_agent(agent_name, db)
            node_context = context.with_db(db)
            return agent, node_context, agent.run_node(node_context)
        finally:
            db.close()


class LangGraphLayeredStrategy(LayeredParallelStrategy):
    """LangGraph-backed layered orchestration."""

    @property
    def name(self) -> str:
        return "langgraph_layered"

    def run(
        self,
        task_id: int,
        resume_id: int,
        jd_id: int,
        user_id: int,
        db: Session,
        run_id: int | None = None,
    ) -> dict[str, Any]:
        from app.orchestration.langgraph_flow import run_layered_graph

        return run_layered_graph(self, task_id, resume_id, jd_id, user_id, db, run_id)


# ===================== 策略工厂 =====================


class StrategyFactory:
    """策略工厂 — 根据配置名返回对应策略实例"""

    _STRATEGIES: dict[str, type] = {
        "linear": LinearStrategy,
        "langgraph_linear": LangGraphLinearStrategy,
        "layered": LayeredParallelStrategy,
        "langgraph_layered": LangGraphLayeredStrategy,
    }

    @classmethod
    def create(cls, name: str, registry: UnifiedRegistry = None) -> ExecutionStrategy:
        registry = registry or DEFAULT_REGISTRY
        if name not in cls._STRATEGIES:
            raise ValueError(f"未知策略 '{name}'，可用: {list(cls._STRATEGIES.keys())}")
        return cls._STRATEGIES[name](registry)

    @classmethod
    def list_strategies(cls) -> list[str]:
        return list(cls._STRATEGIES.keys())
