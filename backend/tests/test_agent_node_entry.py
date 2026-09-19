"""C1 — 节点入口回归：`BaseAgent.execute()` 是编排层唯一的 Agent 执行入口。

修之前的状态（都在这里被钉住，防止再退回去）：

1. `execute()` 全项目零调用，而且**一调用就 TypeError** —— 它给 `retry_call` 传了
   `on_retry`，而 `retry_call` 没有这个参数（只有那个零调用的 `with_retry` 装饰器有）。
   策略层直打 `run_impl`，于是 `AgentMessage`/`AgentResult` 没有任何写入方：
   `/api/multi-agent/run/{id}/detail` 的 messages/results 恒为空数组。
2. `execute()` 只捕 `RuntimeError`。非 RuntimeError 的失败会把消息行永久留在
   status="running"，并把裸异常抛进编排层。
3. 用量按"最后一次尝试"记录，重试花掉的 token 直接丢掉。
4. 任务中心按 `AgentRun.user_request == f"task:{id}"` 关联用量，而没有任何写入方
   产出这个字符串 —— 那个汇总恒命中 0 行。
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.base_agent import BaseAgent
from app.api.auth import router as auth_router
from app.api.multi_agent import router as multi_agent_router
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.agent import AgentStepLog, AgentTask
from app.models.agent_run import AgentMessage, AgentResult, AgentRun
from app.models.history import Resume
from app.models.user import User
from app.orchestration.context import AgentContext
from app.orchestration.registry import AgentSpec, UnifiedRegistry
from app.orchestration.strategies import LayeredParallelStrategy, LinearStrategy, StrategyFactory
from app.services.llm_service import _record_usage, get_llm_trace_context
from app.services.orchestration_backend import TaskPayload

# ===================== 被测节点 =====================


class _OkAgent(BaseAgent):
    name = "OkAgent"
    result_type = "ok_report"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        return {"answer": "ok"}


class _BoomAgent(BaseAgent):
    """非 RuntimeError：老实现会让消息行卡在 running，并把异常抛给编排层。"""

    name = "BoomAgent"
    result_type = "boom_report"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        raise ValueError("非 RuntimeError 的失败")


class _FlakyAgent(BaseAgent):
    """前两次尝试各花掉 15 token 后失败，第三次成功——成本必须全部计入本节点。"""

    name = "FlakyAgent"
    result_type = "flaky_report"
    calls = 0

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        type(self).calls += 1
        _record_usage({"prompt_tokens": 10, "completion_tokens": 5})
        if type(self).calls < 3:
            raise RuntimeError("瞬时故障")
        return {"calls": type(self).calls}


class _TraceReaderAgent(BaseAgent):
    name = "TraceReaderAgent"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        return {key: value for key, value in get_llm_trace_context().items() if key != "db"}


def _mock_class(name: str, base: type[BaseAgent] = _OkAgent, **attrs) -> type[BaseAgent]:
    return type(f"Mock{name}", (base,), {"name": name, "result_type": name.lower(), **attrs})


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    import app.agents.base_agent as base_agent

    monkeypatch.setattr(base_agent, "RETRY_BACKOFF_SECONDS", 0)


@pytest.fixture
def registry() -> UnifiedRegistry:
    reg = UnifiedRegistry()
    linear = ["linear", "langgraph_linear"]
    for name in (
        "IntentAgent",
        "ResumeParseAgent",
        "JDParseAgent",
        "MatchAnalysisAgent",
        "ResumeOptimizeAgent",
        "InterviewQuestionAgent",
        "SummaryAgent",
    ):
        reg.register(AgentSpec(name, _mock_class(name), strategies=linear))
    layered = ["layered", "langgraph_layered"]
    for name in ("ResumeAgent", "JobAgent", "MatchAgent", "InterviewAgent", "CareerAgent"):
        reg.register(AgentSpec(name, _mock_class(name), strategies=layered))
    reg._agents["SummaryAgent"].strategies = [*linear, *layered]
    return reg


@pytest.fixture
def task(db_session: Any, make_resume, make_jd) -> dict[str, int]:
    resume_id = make_resume()
    jd_id = make_jd()
    obj = AgentTask(user_id=1, resume_id=resume_id, jd_id=jd_id, status="pending")
    db_session.add(obj)
    db_session.commit()
    return {"task_id": obj.id, "resume_id": resume_id, "jd_id": jd_id}


@pytest.fixture
def run(db_session: Any, task) -> AgentRun:
    obj = AgentRun(resume_id=task["resume_id"], jd_id=task["jd_id"], task_id=task["task_id"], status="running")
    db_session.add(obj)
    db_session.commit()
    return obj


def _context(db_session: Any, task: dict, run_id: int | None = None) -> AgentContext:
    return AgentContext.for_analysis(
        task["resume_id"],
        task["jd_id"],
        user_id=1,
        db=db_session,
        task_id=task["task_id"],
        run_id=run_id,
    )


# ===================== 节点入口本身 =====================


def test_execute_writes_message_and_result(db_session, task, run):
    """节点跑完要有 AgentMessage + AgentResult —— C1 之前一条都没有。"""
    outcome = _OkAgent(db=db_session).execute(run.id, _context(db_session, task, run.id))

    assert outcome.succeeded
    msg = db_session.query(AgentMessage).filter_by(run_id=run.id).one()
    assert msg.agent_name == "OkAgent"
    assert msg.status == "completed"
    assert msg.output_data == {"answer": "ok"}
    assert msg.error_msg is None
    assert msg.duration_ms >= 0

    res = db_session.query(AgentResult).filter_by(run_id=run.id).one()
    assert res.result_type == "ok_report"
    assert res.message_id == msg.id
    assert outcome.message_id == msg.id


def test_failed_node_is_recorded_and_does_not_raise(db_session, task, run):
    """失败要成为一条 failed 消息，而不是穿过编排层的裸异常。"""
    outcome = _BoomAgent(db=db_session).execute(run.id, _context(db_session, task, run.id))

    assert not outcome.succeeded
    assert outcome.attempts == 3  # 1 + MAX_RETRIES
    msg = db_session.query(AgentMessage).filter_by(run_id=run.id).one()
    assert msg.status == "failed"
    assert "非 RuntimeError" in msg.error_msg
    assert db_session.query(AgentResult).filter_by(run_id=run.id).count() == 0


def test_message_never_stays_running(db_session, task, run):
    """running 中间态不再存在：消息行要么 completed 要么 failed。"""
    assert db_session.query(AgentMessage).filter_by(status="running").count() == 0
    _BoomAgent(db=db_session).execute(run.id, _context(db_session, task, run.id))
    _OkAgent(db=db_session).execute(run.id, _context(db_session, task, run.id))
    statuses = {m.status for m in db_session.query(AgentMessage).filter_by(run_id=run.id).all()}
    assert statuses == {"completed", "failed"}


def test_retried_attempts_keep_their_cost(db_session, task, run, monkeypatch):
    """重试花掉的 token 不能丢：3 次尝试 × 15 = 45。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_INPUT_COST_PER_1K_CENTS", 0.5)
    monkeypatch.setattr(settings, "LLM_OUTPUT_COST_PER_1K_CENTS", 1.0)
    _FlakyAgent.calls = 0

    outcome = _FlakyAgent(db=db_session).execute(run.id, _context(db_session, task, run.id))

    assert outcome.succeeded and outcome.attempts == 3
    assert outcome.usage["total_tokens"] == 45
    # 每次尝试 10/1000*0.5 + 5/1000*1.0 = 0.01 分
    assert outcome.usage["cost_cents"] == pytest.approx(0.03)
    msg = db_session.query(AgentMessage).filter_by(run_id=run.id).one()
    assert (msg.tokens_used, round(msg.cost_cents, 6)) == (45, 0.03)


def test_node_seeds_llm_trace_attribution(db_session, task, run):
    """节点内的 LLM 调用要知道自己属于哪个任务/节点，prompt_trace 才能反查。"""
    outcome = _TraceReaderAgent(db=db_session).execute(run.id, _context(db_session, task, run.id))

    assert outcome.result["source"] == "agent.TraceReaderAgent"
    assert outcome.result["task_id"] == task["task_id"]
    assert outcome.result["agent_name"] == "TraceReaderAgent"
    assert outcome.result["run_id"] == run.id


# ===================== 编排层只能走这个入口 =====================


def test_linear_run_produces_one_message_per_node(db_session, task, registry):
    result = LinearStrategy(registry).run(task["task_id"], task["resume_id"], task["jd_id"], 1, db_session)

    assert result["status"] == "completed"
    messages = db_session.query(AgentMessage).order_by(AgentMessage.id).all()
    assert [m.agent_name for m in messages] == registry.list_names("linear")
    assert all(m.status == "completed" for m in messages)
    assert db_session.query(AgentResult).count() == 7

    # 每个任务一条 run，且用 task_id 关联
    single = db_session.query(AgentRun).one()
    assert single.task_id == task["task_id"]
    assert single.status == "completed"


def test_step_log_and_message_agree(db_session, task, registry):
    """步骤日志（进度）与节点消息（流水）必须是同一份事实。"""
    LinearStrategy(registry).run(task["task_id"], task["resume_id"], task["jd_id"], 1, db_session)

    logs = db_session.query(AgentStepLog).order_by(AgentStepLog.step_index).all()
    by_name = {m.agent_name: m for m in db_session.query(AgentMessage).all()}
    assert len(logs) == len(by_name) == 7
    for log in logs:
        msg = by_name[log.step_name]
        assert log.output_data == msg.output_data
        assert log.duration_ms == msg.duration_ms
        # 用量不再被塞进结果体里随 output_data 到处流
        assert "_usage" not in log.output_data


def test_failed_node_marks_step_log_with_retry_count(db_session, task, registry):
    registry._agents["MatchAnalysisAgent"] = AgentSpec(
        "MatchAnalysisAgent",
        _mock_class("MatchAnalysisAgent", _BoomAgent),
        critical=True,
        strategies=["linear", "langgraph_linear"],
    )

    result = LinearStrategy(registry).run(task["task_id"], task["resume_id"], task["jd_id"], 1, db_session)

    assert result["status"] == "failed"
    log = db_session.query(AgentStepLog).filter_by(step_name="MatchAnalysisAgent").one()
    assert log.status == "failed"
    assert log.retry_count == 2
    assert "非 RuntimeError" in log.error_msg
    msg = db_session.query(AgentMessage).filter_by(agent_name="MatchAnalysisAgent").one()
    assert msg.status == "failed"


def test_layered_reuses_the_callers_run(db_session, task, registry):
    """分层策略过去自己再造一条 run：前端轮询的那行永远没有消息。"""
    run_a = AgentRun(resume_id=task["resume_id"], jd_id=task["jd_id"], task_id=task["task_id"], status="running")
    db_session.add(run_a)
    db_session.commit()

    result = LayeredParallelStrategy(registry).run(
        task["task_id"],
        task["resume_id"],
        task["jd_id"],
        1,
        db_session,
        run_id=run_a.id,
    )

    assert result["status"] == "completed"
    assert db_session.query(AgentRun).count() == 1
    names = {m.agent_name for m in db_session.query(AgentMessage).filter_by(run_id=run_a.id).all()}
    assert names == {"ResumeAgent", "JobAgent", "MatchAgent", "InterviewAgent", "CareerAgent", "SummaryAgent"}


# ===================== 两条编排实现给出同一份事实 =====================
# 在此之前 langgraph_* 在测试里只被 `create()` 过一次，从未真正跑过节点。


@pytest.mark.parametrize("strategy_name", ["linear", "langgraph_linear"])
def test_both_linear_implementations_record_the_same_nodes(strategy_name, db_session, task, registry):
    result = StrategyFactory.create(strategy_name, registry).run(
        task["task_id"], task["resume_id"], task["jd_id"], 1, db_session
    )

    assert result["status"] == "completed"
    messages = db_session.query(AgentMessage).order_by(AgentMessage.id).all()
    assert [m.agent_name for m in messages] == LinearStrategy.AGENT_ORDER
    assert {m.status for m in messages} == {"completed"}
    run_row = db_session.query(AgentRun).one()
    assert (run_row.task_id, run_row.status) == (task["task_id"], "completed")


@pytest.mark.parametrize("strategy_name", ["layered", "langgraph_layered"])
def test_both_layered_implementations_record_the_same_nodes(strategy_name, db_session, task, registry):
    result = StrategyFactory.create(strategy_name, registry).run(
        task["task_id"], task["resume_id"], task["jd_id"], 1, db_session
    )

    assert result["status"] == "completed"
    by_name = {m.agent_name: m for m in db_session.query(AgentMessage).all()}
    assert set(by_name) == {"ResumeAgent", "JobAgent", "MatchAgent", "InterviewAgent", "CareerAgent", "SummaryAgent"}
    assert {m.status for m in by_name.values()} == {"completed"}
    # 层级日志在并发前就整组建好，否则并行时只看得见先完成的那一条
    logs = db_session.query(AgentStepLog).order_by(AgentStepLog.step_index).all()
    assert [log.step_name for log in logs][:2] == ["ResumeAgent", "JobAgent"]


# ===================== 任务中心与对外明细 =====================


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    app.include_router(multi_agent_router, prefix="/multi-agent")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _headers(db_session) -> dict:
    user = User(username="node_owner", email="node_owner@example.com", password=hash_password("abc12345"))
    db_session.add(user)
    db_session.commit()
    token = create_access_token({"sub": str(user.id), "email": user.email, "username": user.username})
    return {"Authorization": f"Bearer {token}"}, user


def test_run_detail_endpoint_returns_the_message_sequence(client, db_session, task, registry, run):
    """验收项：`/api/multi-agent` 返回真实消息序列（曾经是恒空数组）。"""
    _auth_headers, owner = _headers(db_session)
    resume = db_session.get(Resume, task["resume_id"])
    resume.user_id = owner.id
    db_session.commit()

    LayeredParallelStrategy(registry).run(
        task["task_id"],
        task["resume_id"],
        task["jd_id"],
        owner.id,
        db_session,
        run_id=run.id,
    )

    body = client.get(f"/multi-agent/run/{run.id}/detail", headers=_auth_headers).json()["data"]
    assert [m["agent_name"] for m in body["messages"]] == [
        "ResumeAgent",
        "JobAgent",
        "MatchAgent",
        "InterviewAgent",
        "CareerAgent",
        "SummaryAgent",
    ]
    assert all(m["status"] == "completed" for m in body["messages"])
    assert len(body["results"]) == 6


def test_task_center_reports_node_usage(db_session, task, monkeypatch):
    from app.services.task_center_service import get_task_with_progress

    monkeypatch.setattr(settings, "LLM_INPUT_COST_PER_1K_CENTS", 0.5)
    monkeypatch.setattr(settings, "LLM_OUTPUT_COST_PER_1K_CENTS", 1.0)

    class _SpendingAgent(_OkAgent):
        def run_impl(self, context):
            _record_usage({"prompt_tokens": 100, "completion_tokens": 20})
            return {"answer": "ok"}

    reg = UnifiedRegistry()
    for name in LinearStrategy.AGENT_ORDER:
        reg.register(AgentSpec(name, _mock_class(name, _SpendingAgent), strategies=["linear", "langgraph_linear"]))

    LinearStrategy(reg).run(task["task_id"], task["resume_id"], task["jd_id"], 1, db_session)

    _, payload = get_task_with_progress(db_session, task_id=task["task_id"], user_id=1)
    # 7 节点 × (100/1000*0.5 + 20/1000*1.0) = 7 × 0.07
    assert payload["usage"] == {"tokens_used": 840, "cost_cents": pytest.approx(0.49)}


# ===================== 跨进程投递必须带上 run_id =====================


def test_payload_round_trips_the_run_id():
    """Redis 后端只搬运 payload，闭包会被丢掉：run_id 必须是 payload 的一部分。

    现场复现过：`/api/multi-agent/auto` 返回 run A，worker 却把节点写在自建的
    run B 上，A 永远停在 running、明细为空。
    """
    payload = TaskPayload(
        strategy_name="layered",
        task_id=7,
        resume_id=1,
        jd_id=2,
        user_id=3,
        run_id=42,
    )
    restored = TaskPayload.from_json(payload.to_json())

    assert restored == payload
    assert restored.run_id == 42


def test_worker_entry_passes_run_id_into_the_strategy(db_session, task, monkeypatch):
    import app.services.orchestration_runner as runner_mod

    seen: dict[str, Any] = {}

    class _SpyStrategy(LinearStrategy):
        def run(self, task_id, resume_id, jd_id, user_id, db, run_id=None):
            seen["run_id"] = run_id
            return {"status": "completed", "error": ""}

    monkeypatch.setattr(runner_mod, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(runner_mod.StrategyFactory, "create", lambda name, registry=None: _SpyStrategy(registry))

    runner_mod._run_task_payload(
        TaskPayload(
            strategy_name="linear",
            task_id=task["task_id"],
            resume_id=task["resume_id"],
            jd_id=task["jd_id"],
            user_id=1,
            run_id=42,
        )
    )

    assert seen["run_id"] == 42
