"""BaseAgent：所有智能体的基类"""

import contextlib
import json
import time
import traceback
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.agent_run import AgentMessage, AgentResult
from app.orchestration.context import AgentContext
from app.services.llm_service import get_llm_usage, reset_llm_usage
from app.utils.retry import retry_call
from app.utils.time_helper import utc_now

MAX_RETRIES = 2


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

    def execute(self, run_id: int, context: AgentContext) -> dict[str, Any]:
        """执行智能体，带重试和日志记录"""
        close_db = False
        context = context.with_db(self._db) if self._db is not None else context
        if context.db is None:
            self._db = SessionLocal()
            context = context.with_db(self._db)
            close_db = True
        else:
            self._db = context.db

        try:
            safe_inputs = context.to_log_dict()
            msg = AgentMessage(
                run_id=run_id,
                agent_name=self.name,
                status="running",
                depends_on=self.depends_on,
                input_data=safe_inputs,
                started_at=utc_now(),
            )
            self._db.add(msg)
            self._db.commit()
            self._db.refresh(msg)

            # 执行（带统一重试）
            result = None
            last_error = None

            def _do_run():
                reset_llm_usage()
                t0 = time.time()
                r = self.run_impl(context)
                elapsed_ms = int((time.time() - t0) * 1000)
                usage = get_llm_usage()
                return r, elapsed_ms, usage

            def _on_retry(exc, attempt, max_retries):
                nonlocal last_error
                last_error = str(exc)
                traceback.print_exc()
                # 回滚失败的事务，避免共享 session 进入 PendingRollbackError 连环失败
                with contextlib.suppress(Exception):
                    self._db.rollback()

            try:
                result, elapsed_ms, usage = retry_call(
                    _do_run,
                    max_retries=MAX_RETRIES,
                    on_retry=_on_retry,
                    log_prefix=f"Agent[{self.name}]",
                )
                msg.status = "completed"
                msg.output_data = result
                msg.completed_at = utc_now()
                msg.duration_ms = elapsed_ms
                msg.tokens_used = int(usage.get("total_tokens") or 0)
                msg.cost_cents = float(usage.get("cost_cents") or 0.0)
                self._db.add(msg)
                self._db.commit()
            except RuntimeError:
                msg.status = "failed"
                msg.error_msg = f"重试 {MAX_RETRIES} 次后仍失败: {last_error}"
                msg.completed_at = utc_now()
                self._db.add(msg)
                self._db.commit()

            # 保存结果
            if result is not None:
                res = AgentResult(
                    run_id=run_id,
                    message_id=msg.id,
                    agent_name=self.name,
                    result_type=self.result_type,
                    result_json=result,
                    summary=self._make_summary(result),
                )
                self._db.add(res)
                self._db.commit()
                self._db.refresh(res)

            return result or {"error": last_error, "status": "failed"}

        finally:
            if close_db:
                self._db.close()

    def _make_summary(self, result: dict[str, Any]) -> str:
        """生成结果摘要，子类可覆盖"""
        return json.dumps(result, ensure_ascii=False)[:100]

    def get_prompt_context(self, context: AgentContext) -> dict[str, Any]:
        """从输入中提取上下文，子类可覆盖"""
        return context.to_log_dict()
