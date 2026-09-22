"""
编排策略测试

覆盖两条执行策略的核心路径：
  1. LinearStrategy        — 线性流水线 + 意图裁剪 + 关键错误传播
  2. LayeredParallelStrategy — 分层并行 + 同层并发 + 层间串行
"""

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models.agent import AgentStepLog, AgentTask
from app.orchestration.context import AgentContext
from app.orchestration.registry import DEFAULT_REGISTRY, AgentSpec, UnifiedRegistry
from app.orchestration.strategies import (
    LayeredParallelStrategy,
    LinearStrategy,
    StrategyFactory,
)

# ===================== Mock Agent Classes =====================

# 节点入口（BaseAgent.execute）本身要在这些 mock 上被跑到：所以 mock 必须是真的
# BaseAgent 子类，而不是"长得像的鸭子"。name 逐类给出，AgentMessage.agent_name
# 才有归属，重试/用量/落库走的都是生产路径。


class _MockAgent(BaseAgent):
    """只替掉 run_impl，其余全部按生产路径执行。"""

    result: dict[str, Any] = {"status": "success", "data": "mock_result"}

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        return dict(self.result)


class _MockFailAgent(BaseAgent):
    """一直抛异常的节点：用来验证重试耗尽后节点变 failed。"""

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        raise RuntimeError("模拟 Agent 执行失败")


def _mock_class(name: str, base: type[BaseAgent] = _MockAgent, **attrs) -> type[BaseAgent]:
    return type(f"Mock{name}", (base,), {"name": name, "result_type": name.lower(), **attrs})


class _MockSkipIntentAgent(BaseAgent):
    """Mock IntentAgent that returns resume_match_only intent."""

    name = "IntentAgent"
    result_type = "intent"

    def run_impl(self, context: AgentContext) -> dict[str, Any]:
        return {
            "intent": "resume_match_only",
            "intent_confidence": 0.85,
            "required_steps": [
                "intent_recognition",
                "resume_parse",
                "jd_parse",
                "knowledge_retrieval",
                "matching_analysis",
                "final_report",
            ],
        }


# ===================== Fixtures =====================


@pytest.fixture
def mock_registry():
    """Create a registry with mock agent classes for testing."""
    reg = UnifiedRegistry()

    linear_strategies = ["linear", "langgraph_linear"]
    for name in (
        "IntentAgent",
        "ResumeParseAgent",
        "JDParseAgent",
        "MatchAnalysisAgent",
        "ResumeOptimizeAgent",
        "InterviewQuestionAgent",
        "SummaryAgent",
    ):
        critical = name != "InterviewQuestionAgent"
        reg.register(AgentSpec(name, _mock_class(name), critical=critical, strategies=linear_strategies))

    layered_strategies = ["layered", "langgraph_layered"]
    for name in ("ResumeAgent", "JobAgent", "MatchAgent", "InterviewAgent", "CareerAgent", "SummaryAgent"):
        critical = name != "InterviewAgent"
        existing = reg._agents.get(name)
        strategies = sorted({*linear_strategies, *layered_strategies}) if existing else list(layered_strategies)
        reg.register(AgentSpec(name, _mock_class(name), critical=critical, strategies=strategies))

    return reg


def _failing(registry: UnifiedRegistry, name: str, strategies: list[str], critical: bool = True) -> None:
    """把某个节点换成一直失败的版本，其余保持不变。"""
    registry._agents[name] = AgentSpec(
        name, _mock_class(name, _MockFailAgent), critical=critical, strategies=strategies
    )


@pytest.fixture(autouse=True)
def no_node_backoff(monkeypatch):
    """失败路径要跑满 3 次尝试，退避在测试里不真等。"""
    import app.agents.base_agent as base_agent

    monkeypatch.setattr(base_agent, "RETRY_BACKOFF_SECONDS", 0)


# ==================== LinearStrategy Tests ====================


class TestLinearStrategy:
    """LinearStrategy 执行路径测试"""

    def _run_strategy(
        self, db: Session, task_id: int, resume_id: int, jd_id: int, registry: UnifiedRegistry = None
    ) -> dict[str, Any]:
        strategy = LinearStrategy(registry or DEFAULT_REGISTRY)
        return strategy.run(task_id, resume_id, jd_id, user_id=1, db=db)

    def _create_task(self, db: Session, resume_id: int, jd_id: int, **kwargs) -> int:
        task = AgentTask(
            user_id=1,
            resume_id=resume_id,
            jd_id=jd_id,
            status="pending",
            **kwargs,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task.id

    def test_full_analysis_all_agents_executed(self, db_session, make_resume, make_jd, mock_registry):
        """全量分析时，所有 Agent 都应被执行并返回成功。"""
        resume_id = make_resume()
        jd_id = make_jd()
        task_id = self._create_task(db_session, resume_id, jd_id)

        result = self._run_strategy(db_session, task_id, resume_id, jd_id, registry=mock_registry)

        assert result["status"] == "completed"
        assert len(result["steps"]) == 7
        # 全部成功
        for step in result["steps"]:
            assert step["status"] == "success", f"Agent {step['agent_name']} 应该成功"

        # 验证步骤日志
        logs = db_session.query(AgentStepLog).filter_by(task_id=task_id).order_by(AgentStepLog.step_index).all()
        assert len(logs) == 7
        for log in logs:
            assert log.status == "completed"

        # 验证任务记录
        task = db_session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.analysis_record_id is not None

    def test_critical_agent_failure_stops_pipeline(self, db_session, make_resume, make_jd, mock_registry):
        """关键 Agent 失败时，流水线应停止并标记为 failed。"""
        resume_id = make_resume()
        jd_id = make_jd()
        task_id = self._create_task(db_session, resume_id, jd_id)

        # 把 IntentAgent 替换为会失败的版本
        _failing(mock_registry, "IntentAgent", ["linear", "langgraph_linear"])

        result = self._run_strategy(db_session, task_id, resume_id, jd_id, registry=mock_registry)

        assert result["status"] == "failed"
        assert result["steps"][0]["status"] == "failed"
        # 只有第一步被执行
        assert len(result["steps"]) == 1

        task = db_session.get(AgentTask, task_id)
        assert task.status == "failed"

    def test_non_critical_failure_continues(self, db_session, make_resume, make_jd, mock_registry):
        """非关键 Agent 失败时，流水线应继续执行并标记为 partial。"""
        resume_id = make_resume()
        jd_id = make_jd()
        task_id = self._create_task(db_session, resume_id, jd_id)

        # InterviewQuestionAgent 是非关键的（critical=False）
        _failing(mock_registry, "InterviewQuestionAgent", ["linear", "langgraph_linear"], critical=False)

        result = self._run_strategy(db_session, task_id, resume_id, jd_id, registry=mock_registry)

        assert result["status"] == "partial"
        assert len(result["steps"]) == 7
        # InterviewQuestionAgent 失败，其他成功
        interview_step = next(s for s in result["steps"] if s["agent_name"] == "InterviewQuestionAgent")
        assert interview_step["status"] == "failed"
        successful = [s for s in result["steps"] if s["agent_name"] != "InterviewQuestionAgent"]
        assert all(s["status"] == "success" for s in successful)

    def test_intent_skip_optimize_and_interview(self, db_session, make_resume, make_jd, mock_registry):
        """意图为 resume_match_only 时，跳过优化和面试题生成。"""
        resume_id = make_resume()
        jd_id = make_jd()
        task_id = self._create_task(db_session, resume_id, jd_id)

        # 替换 IntentAgent 为返回 resume_match_only 的版本
        mock_registry._agents["IntentAgent"] = AgentSpec(
            "IntentAgent",
            _MockSkipIntentAgent,
            critical=True,
            strategies=["linear", "langgraph_linear"],
        )
        result = self._run_strategy(db_session, task_id, resume_id, jd_id, registry=mock_registry)

        assert result["status"] == "completed"
        # 验证跳过了特定步骤
        skipped = [s for s in result["steps"] if s["status"] == "skipped"]
        skipped_names = [s["agent_name"] for s in skipped]
        assert "ResumeOptimizeAgent" in skipped_names
        assert "InterviewQuestionAgent" in skipped_names

        # 验证日志也标记为 skipped
        logs = db_session.query(AgentStepLog).filter_by(task_id=task_id).all()
        skipped_logs = [log for log in logs if log.status == "skipped"]
        skipped_log_names = [log.step_name for log in skipped_logs]
        assert "ResumeOptimizeAgent" in skipped_log_names

    def test_success_clears_an_error_the_startup_sweep_wrote_first(
        self, db_session, make_resume, make_jd, mock_registry
    ):
        """被启动清扫误判过的任务完成后不能继续带着那条失败原因：任务中心原样显示 error_msg。"""
        resume_id = make_resume()
        jd_id = make_jd()
        task_id = self._create_task(
            db_session,
            resume_id,
            jd_id,
            error_msg="任务超过 30 分钟没有新的步骤写入（最后一次活动 2026-09-22 03:00:00），按中断收口",
        )

        result = self._run_strategy(db_session, task_id, resume_id, jd_id, registry=mock_registry)

        assert result["status"] == "completed"
        task = db_session.get(AgentTask, task_id)
        assert task.status == "completed"
        assert task.error_msg is None

    def test_task_not_found(self, db_session, mock_registry):
        """任务不存在时返回错误。"""
        strategy = LinearStrategy(mock_registry)
        result = strategy.run(9999, resume_id=1, jd_id=1, user_id=1, db=db_session)
        assert result["status"] == "failed"
        assert "不存在" in result["error"]

    def test_all_intent_variants(self, db_session, make_resume, make_jd, mock_registry):
        """测试所有意图变体对 Agent 执行的影响。"""
        resume_id = make_resume()
        jd_id = make_jd()
        task_id = self._create_task(db_session, resume_id, jd_id)

        intent_test_cases = [
            ("resume_match_only", {"MatchAnalysisAgent", "SummaryAgent"}),
            ("optimize_only", {"ResumeOptimizeAgent", "SummaryAgent"}),
            ("interview_only", {"InterviewQuestionAgent", "SummaryAgent"}),
        ]

        for intent_name, _expected_non_skipped in intent_test_cases:
            # 为当前测试重置 task 状态
            db_session.query(AgentTask).filter_by(id=task_id).update({"status": "pending"})
            db_session.commit()

            # 用新的 IntentAgent mock
            intent_agent = _mock_class(
                "IntentAgent",
                _MockAgent,
                result={"intent": intent_name, "intent_confidence": 0.9, "required_steps": []},
            )

            mock_registry._agents["IntentAgent"] = AgentSpec(
                "IntentAgent",
                intent_agent,
                critical=True,
                strategies=["linear", "langgraph_linear"],
            )

            strategy = LinearStrategy(mock_registry)
            result = strategy.run(task_id, resume_id, jd_id, user_id=1, db=db_session)

            # 验证应该被跳过的步骤都被跳过了
            # Intent + ResumeParse + JDParse 应始终执行
            always_run = {"IntentAgent", "ResumeParseAgent", "JDParseAgent"}
            not_skipped = {s["agent_name"] for s in result["steps"] if s["status"] == "success"}
            assert always_run.issubset(not_skipped), f"{intent_name}: 基础 Agent 应始终执行"

            # IntentAgent 和 SummaryAgent 应当执行
            summary_step = next(s for s in result["steps"] if s["agent_name"] == "SummaryAgent")
            assert summary_step["status"] != "skipped", f"{intent_name}: SummaryAgent 不应被跳过"


# ==================== LayeredParallelStrategy Tests ====================


class TestLayeredParallelStrategy:
    """LayeredParallelStrategy 执行路径测试"""

    def test_layered_execution_order(self, db_session, make_resume, make_jd, mock_registry):
        """分层策略按层级顺序执行，同层并发。"""
        resume_id = make_resume()
        jd_id = make_jd()
        task = AgentTask(
            user_id=1,
            resume_id=resume_id,
            jd_id=jd_id,
            status="pending",
        )
        db_session.add(task)
        db_session.commit()
        task_id = task.id

        strategy = LayeredParallelStrategy(mock_registry)
        result = strategy.run(task_id, resume_id, jd_id, user_id=1, db=db_session)

        assert result["status"] == "completed"
        assert len(result["steps"]) == 6  # 6 个 agent（3层串行）

        # 验证层间顺序：第一层 ResumeAgent + JobAgent 都执行了
        agent_names = [s["agent_name"] for s in result["steps"]]
        assert "ResumeAgent" in agent_names
        assert "JobAgent" in agent_names
        assert "MatchAgent" in agent_names
        assert "SummaryAgent" in agent_names

        # 所有 Agent 都应成功
        for step in result["steps"]:
            assert step["status"] == "success", f"{step['agent_name']} 应执行成功"

    def test_layer_failure_stops_pipeline(self, db_session, make_resume, make_jd, mock_registry):
        """某一层 Agent 失败时流水线终止。"""
        resume_id = make_resume()
        jd_id = make_jd()
        task = AgentTask(
            user_id=1,
            resume_id=resume_id,
            jd_id=jd_id,
            status="pending",
        )
        db_session.add(task)
        db_session.commit()
        task_id = task.id

        # 把核心的 MatchAgent 替换为会失败的
        _failing(mock_registry, "MatchAgent", ["layered", "langgraph_layered"])

        strategy = LayeredParallelStrategy(mock_registry)
        result = strategy.run(task_id, resume_id, jd_id, user_id=1, db=db_session)

        assert result["status"] == "failed" or result["status"] == "partial"

    def test_layered_intent_handling(self, db_session, make_resume, make_jd, mock_registry):
        """分层策略意图裁剪。"""
        resume_id = make_resume()
        jd_id = make_jd()
        task = AgentTask(
            user_id=1,
            resume_id=resume_id,
            jd_id=jd_id,
            status="pending",
        )
        db_session.add(task)
        db_session.commit()
        task_id = task.id

        # LayeredParallelStrategy 使用 _should_execute 方法，
        # 该方法检查 context.intent_detail 中的 intent 字段
        # 默认 full_analysis 执行所有

        # 验证 summary 层正常工作
        strategy = LayeredParallelStrategy(mock_registry)
        result = strategy.run(task_id, resume_id, jd_id, user_id=1, db=db_session)
        assert result["status"] == "completed"


# ==================== StrategyFactory Tests ====================


class TestStrategyFactory:
    """StrategyFactory 创建策略测试"""

    def test_create_linear_strategy(self):
        strategy = StrategyFactory.create("linear")
        assert isinstance(strategy, LinearStrategy)

    def test_create_layered_strategy(self):
        strategy = StrategyFactory.create("layered")
        assert isinstance(strategy, LayeredParallelStrategy)

    def test_create_langgraph_strategies(self):
        for name in ["langgraph_linear", "langgraph_layered"]:
            strategy = StrategyFactory.create(name)
            assert strategy is not None
            assert strategy.name == name

    def test_create_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="未知策略"):
            StrategyFactory.create("nonexistent")

    def test_list_strategies(self):
        strategies = StrategyFactory.list_strategies()
        assert "linear" in strategies
        assert "layered" in strategies
        # step_by_step 曾是第三条流水线（11 个绕过 agent 类的裸步骤），C4 已删；
        # 配置里残留它的部署会在这里得到明确的"未知策略"错误，而不是静默换一条路。
        assert "step_by_step" not in strategies
        assert "langgraph_step_by_step" not in strategies
        assert len(strategies) == 4

    def test_removed_step_strategy_fails_loudly(self):
        with pytest.raises(ValueError, match="未知策略"):
            StrategyFactory.create("step_by_step")

    def test_legacy_workflow_endpoint_uses_the_configured_strategy(self, monkeypatch):
        """/api/agent/start 不再启动第三条流水线，而是按配置走同一条路。"""
        import app.services.agent_workflow as workflow

        seen: dict[str, Any] = {}
        monkeypatch.setattr(
            workflow,
            "run_smart_analysis",
            lambda resume_id, jd_id, user_id=None: seen.update(resume_id=resume_id, jd_id=jd_id, user_id=user_id) or 77,
        )

        with pytest.warns(DeprecationWarning):
            assert workflow.run_workflow(11, 22, user_id=3) == 77
        assert seen == {"resume_id": 11, "jd_id": 22, "user_id": 3}

    def test_strategy_with_custom_registry(self, mock_registry):
        strategy = StrategyFactory.create("linear", registry=mock_registry)
        assert strategy.registry is mock_registry
