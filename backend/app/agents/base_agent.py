"""BaseAgent：所有智能体的基类，也是编排层唯一的节点入口。

一个节点分两半，是为了让"写库"只发生在一个地方：

  - run_node(): 跑 run_impl + 统一重试 + 归集 token 用量，**不写库**，
    所以可以安全地在工作线程里执行（分层并行策略的每个 agent 一个 session）；
  - record_node_outcome(): AgentMessage / AgentResult 只从这里写，
    由持有主 session 的调用方在同一线程里落库；
  - execute(): 上面两步的组合，单线程策略直接用。

AgentMessage 只有终态（completed/failed），没有 running —— 实时进度由
AgentStepLog 承担（它在节点开始前就以 running 落库，且始终用主 session 写）。
"""

import contextlib
import json
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent import RetrievalLog
from app.models.agent_run import AgentMessage, AgentResult
from app.orchestration.context import AgentContext
from app.services import retrieval_log
from app.services.llm_service import (
    get_llm_usage,
    reset_llm_provenance,
    reset_llm_usage,
    set_llm_trace_context,
)
from app.utils.retry import retry_call
from app.utils.time_helper import utc_now

MAX_RETRIES = 2
# 节点级退避。LLM 调用在 llm_service 内部已经退避重试过一轮，这里再叠上去是为了
# 兜住非 LLM 的瞬时失败（事务、外部服务）。测试里置 0，不必真的等。
RETRY_BACKOFF_SECONDS = 1.5

_USAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens", "cost_cents")


def _zero_usage() -> dict[str, float]:
    return {key: 0.0 for key in _USAGE_KEYS}


@dataclass
class NodeOutcome:
    """一次节点执行的完整结果。"""

    agent_name: str
    status: str  # success / failed
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    usage: dict[str, float] = field(default_factory=_zero_usage)
    retrievals: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    attempts: int = 1
    started_at: datetime | None = None
    message_id: int | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success"


class BaseAgent(ABC):
    """智能体基类

    子类需实现:
      - name: str                    # 智能体名称
      - description: str             # 描述
      - depends_on: List[str]        # 依赖的智能体名称
      - result_type: str             # 结果类型标识
      - run_impl(context) → dict     # 核心执行逻辑
    """

    name: str = ""
    description: str = ""
    depends_on: list[str] = []
    result_type: str = ""

    def __init__(self, db: Session = None):
        self._db = db

    @abstractmethod
    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        """子类实现具体的智能体逻辑"""
        raise NotImplementedError

    def execute(self, run_id: int, context: AgentContext) -> NodeOutcome:
        """节点入口：执行 + 落库。调用方必须给出 context.db（分层并行策略在工作线程里只调 run_node，
        再由主线程用同一个 run_id 落库）。"""
        outcome = self.run_node(context)
        return record_node_outcome(context.db, run_id, self, context, outcome)

    def run_node(self, context: AgentContext) -> NodeOutcome:
        """执行本节点：统一重试与用量归集，不写库，失败以 status 返回而不抛出。"""
        if self._db is not None:
            context = context.with_db(self._db)

        usage_total = _zero_usage()
        retrievals: list[dict[str, Any]] = []
        attempts = 0
        started_at = utc_now()
        t0 = time.time()

        def _attempt():
            nonlocal attempts
            attempts += 1
            # 每次尝试都重置用量与来源，再让节点内的 LLM 调用累加进去
            reset_llm_usage()
            reset_llm_provenance()
            retrieval_log.begin()
            _seed_trace_context(self.name, context)
            try:
                return self.run_impl(context)
            finally:
                # 失败的尝试同样花掉了 token、同样查过知识库：先归集，再向上抛
                _accumulate(usage_total, get_llm_usage())
                retrievals.extend(retrieval_log.finish())

        def _on_retry(exc, attempt, max_retries):
            traceback.print_exc()
            # 回滚失败的事务，避免共享 session 进入 PendingRollbackError 连环失败
            with contextlib.suppress(Exception):
                context.db.rollback()

        try:
            result = retry_call(
                _attempt,
                max_retries=MAX_RETRIES,
                backoff_factor=RETRY_BACKOFF_SECONDS,
                on_retry=_on_retry,
                log_prefix=f"Agent[{self.name}]",
            )
            return NodeOutcome(
                agent_name=self.name,
                status="success",
                result=result if isinstance(result, dict) else {},
                usage=usage_total,
                retrievals=retrievals,
                duration_ms=int((time.time() - t0) * 1000),
                attempts=attempts,
                started_at=started_at,
            )
        except Exception as exc:
            # retry_call 用尽后抛 RuntimeError；不可重试的异常原样冒到这里。
            # 两者都必须变成 failed 节点，否则编排层会被一个裸异常打穿。
            traceback.print_exc()
            return NodeOutcome(
                agent_name=self.name,
                status="failed",
                error=str(exc)[:500] or exc.__class__.__name__,
                usage=usage_total,
                retrievals=retrievals,
                duration_ms=int((time.time() - t0) * 1000),
                attempts=max(1, attempts),
                started_at=started_at,
            )

    def _make_summary(self, result: dict[str, Any]) -> str:
        """生成结果摘要，子类可覆盖"""
        return json.dumps(result, ensure_ascii=False, default=str)[:100]

    def get_prompt_context(self, context: AgentContext) -> dict[str, Any]:
        """从输入中提取上下文，子类可覆盖"""
        return context.to_log_dict()


def _seed_trace_context(agent_name: str, context: AgentContext) -> None:
    """给节点内的 LLM 调用打上归属：哪个任务、哪个节点。

    ``chat_json`` 取用一次后会清空该上下文，所以这里覆盖的是节点的首个 LLM 调用；
    自行 set_llm_trace_context 的 agent 会覆盖这份更具体的信息。
    """
    set_llm_trace_context(
        {
            "source": f"agent.{agent_name}",
            "task_id": context.task_id,
            "user_id": context.user_id,
            "resume_id": context.resume_id or None,
            "jd_id": context.jd_id or None,
            "db": context.db,
            "agent_name": agent_name,
            "run_id": context.run_id,
        }
    )


def _accumulate(total: dict[str, float], part: dict[str, float]) -> None:
    for key in _USAGE_KEYS:
        total[key] += float(part.get(key) or 0.0)


def record_node_outcome(
    db: Session,
    run_id: int,
    agent: BaseAgent,
    context: AgentContext,
    outcome: NodeOutcome,
    input_data: dict[str, Any] | None = None,
) -> NodeOutcome:
    """把一次节点执行写成 AgentMessage；成功时再写 AgentResult。

    `input_data` 给分层并行用：节点在工作线程里跑，它看到的上下文由那边快照，
    主线程只负责写行。
    """
    msg = AgentMessage(
        run_id=run_id,
        agent_name=outcome.agent_name,
        status="completed" if outcome.succeeded else "failed",
        depends_on=list(agent.depends_on),
        input_data=input_data if input_data is not None else context.to_log_dict(),
        output_data=outcome.result,
        error_msg=outcome.error or None,
        started_at=outcome.started_at,
        completed_at=utc_now(),
        duration_ms=outcome.duration_ms,
        tokens_used=int(outcome.usage.get("total_tokens") or 0),
        cost_cents=float(outcome.usage.get("cost_cents") or 0.0),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    outcome.message_id = msg.id

    if outcome.succeeded:
        res = AgentResult(
            run_id=run_id,
            message_id=msg.id,
            agent_name=agent.name,
            result_type=agent.result_type or agent.name,
            result_json=outcome.result or {},
            summary=agent._make_summary(outcome.result or {}),
        )
        db.add(res)
        db.commit()

    _record_retrieval_logs(db, context, outcome)

    return outcome


def _record_retrieval_logs(db: Session, context: AgentContext, outcome: NodeOutcome) -> None:
    """节点在期间发起的每一次知识库读取落成一行 `retrieval_log`（取证）。

    0 命中也写行——"查了 5 次、次次空手而归"是结论而不是缺数据。
    没有 task 归属（不在编排里跑）时无处可挂，直接跳过。
    """
    if context.task_id is None or not outcome.retrievals:
        return

    for call in outcome.retrievals:
        db.add(
            RetrievalLog(
                task_id=context.task_id,
                query_text=call.get("query_text") or "",
                doc_type_filter=call.get("doc_type_filter"),
                top_k=call.get("top_k") or 0,
                result_count=call.get("result_count") or 0,
                results=call.get("results") or [],
                duration_ms=call.get("duration_ms") or 0,
            )
        )
    db.commit()
