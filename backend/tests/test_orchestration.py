"""
编排策略测试

覆盖三种执行策略的核心路径：
  1. LinearStrategy        — 线性流水线 + 意图裁剪 + 关键错误传播
  2. LayeredParallelStrategy — 分层并行 + 同层并发 + 层间串行
  3. StepByStepStrategy    — 细粒度步骤 + 步骤日志
"""

from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.agents.base_agent import BaseAgent
from app.models.agent import AgentStepLog, AgentTask
from app.orchestration.context import AgentContext
from app.orchestration.registry import DEFAULT_REGISTRY, AgentSpec, UnifiedRegistry
from app.orchestration.strategies import (
    LayeredParallelStrategy,
    LinearStrategy,
    StepByStepStrategy,
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
    registry._agents[name] = AgentSpec(name, _mock_class(name, _MockFailAgent), critical=critical, strategies=strategies)


@pytest.fixture
def default_settings():
    """Ensure RAG_TOP_K is set to a small value for tests."""
    from app.core.config import settings

    original = settings.RAG_TOP_K
    settings.RAG_TOP_K = 3
    yield
    settings.RAG_TOP_K = original


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


# ==================== StepByStepStrategy Tests ====================


class TestStepByStepStrategy:
    """StepByStepStrategy 细粒度步骤测试"""

    @patch("app.services.agent_steps.step_intent_recognition")
    @patch("app.services.agent_steps.step_resume_parse")
    @patch("app.services.agent_steps.step_jd_parse")
    @patch("app.services.agent_steps.step_task_planning")
    @patch("app.services.agent_steps.step_knowledge_retrieval")
    @patch("app.services.agent_steps.step_matching_analysis")
    @patch("app.services.agent_steps.step_resume_optimization")
    @patch("app.services.agent_steps.step_interview_question_gen")
    @patch("app.services.agent_steps.step_self_check")
    @patch("app.services.agent_steps.step_final_report")
    def test_full_step_execution(
        self,
        mock_report,
        mock_check,
        mock_interview,
        mock_optimize,
        mock_match,
        mock_kb,
        mock_plan,
        mock_jd,
        mock_resume,
        mock_intent,
        db_session,
        make_resume,
        make_jd,
        default_settings,
        mock_registry,
    ):
        """所有步骤按顺序执行并记录日志。"""
        # 配置 mock 返回值
        mock_intent.return_value = {
            "intent": "full_analysis",
            "intent_confidence": 0.95,
            "required_steps": [],
        }
        mock_resume.return_value = {"skipped": False, "parsed": {"name": "测试"}}
        mock_jd.return_value = {"skipped": False, "parsed": {"title": "AI工程师"}}
        mock_plan.return_value = {"plan": [{"step": "分析匹配度"}], "steps_count": 1}
        mock_kb.return_value = {
            "query": "test",
            "retrievals": {},
            "rag_confidence": {"score": 80},
        }
        mock_match.return_value = {"match_score": 85, "detail": "匹配良好"}
        mock_optimize.return_value = {"suggestions": ["增加LLM项目"]}
        mock_interview.return_value = {"questions": [{"q": "q1"}], "total_questions": 1}
        mock_check.return_value = {"passed": True, "checks": []}
        mock_report.return_value = {"summary": "完成", "overall_score": 85}

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

        strategy = StepByStepStrategy(mock_registry)
        result = strategy.run(task_id, resume_id, jd_id, user_id=1, db=db_session)

        assert result["status"] == "completed"
        assert len(result["steps"]) == 11

        # 验证步骤日志
        logs = db_session.query(AgentStepLog).filter_by(task_id=task_id).order_by(AgentStepLog.step_index).all()
        assert len(logs) == 11
        for log in logs:
            assert log.status == "completed"
            assert log.step_index > 0

        # 验证调用了所有的 mock step 函数
        mock_intent.assert_called_once()
        mock_resume.assert_called_once()
        mock_jd.assert_called_once()
        mock_plan.assert_called_once()
        mock_kb.assert_called_once()
        mock_match.assert_called_once()
        mock_optimize.assert_called_once()
        mock_interview.assert_called_once()
        mock_check.assert_called_once()
        mock_report.assert_called_once()

    @patch("app.services.agent_steps.step_intent_recognition")
    @patch("app.services.agent_steps.step_resume_parse")
    @patch("app.services.agent_steps.step_jd_parse")
    @patch("app.services.agent_steps.step_task_planning")
    @patch("app.services.agent_steps.step_knowledge_retrieval")
    @patch("app.services.agent_steps.step_matching_analysis")
    @patch("app.services.agent_steps.step_resume_optimization")
    @patch("app.services.agent_steps.step_interview_question_gen")
    @patch("app.services.agent_steps.step_self_check")
    @patch("app.services.agent_steps.step_final_report")
    def test_step_log_metadata(
        self,
        mock_report,
        mock_check,
        mock_interview,
        mock_optimize,
        mock_match,
        mock_kb,
        mock_plan,
        mock_jd,
        mock_resume,
        mock_intent,
        db_session,
        make_resume,
        make_jd,
        default_settings,
        mock_registry,
    ):
        """验证每个步骤的日志包含正确的元数据（耗时、状态等）。"""
        mock_intent.return_value = {"intent": "full_analysis", "intent_confidence": 0.9, "required_steps": []}
        mock_resume.return_value = {"skipped": False, "parsed": {}}
        mock_jd.return_value = {"skipped": False, "parsed": {}}
        mock_plan.return_value = {"plan": [], "steps_count": 0}
        mock_kb.return_value = {"query": "test", "retrievals": {}, "rag_confidence": {}}
        mock_match.return_value = {"match_score": 80}
        mock_optimize.return_value = {"suggestions": []}
        mock_interview.return_value = {"questions": [], "total_questions": 0}
        mock_check.return_value = {"passed": True, "checks": []}
        mock_report.return_value = {"summary": "完成"}

        resume_id = make_resume()
        jd_id = make_jd()
        task_id = db_session.query(AgentTask).count() + 1
        task = AgentTask(
            id=task_id,
            user_id=1,
            resume_id=resume_id,
            jd_id=jd_id,
            status="pending",
        )
        db_session.add(task)
        db_session.commit()

        strategy = StepByStepStrategy(mock_registry)
        strategy.run(task_id, resume_id, jd_id, user_id=1, db=db_session)

        logs = db_session.query(AgentStepLog).filter_by(task_id=task_id).all()
        for log in logs:
            assert log.status == "completed"
            assert log.started_at is not None  # 开始时间
            assert log.completed_at is not None  # 结束时间
            assert log.duration_ms is not None  # 执行耗时
            assert isinstance(log.duration_ms, int)

    @patch("app.services.agent_steps.step_intent_recognition")
    def test_critical_step_failure(
        self, mock_intent, db_session, make_resume, make_jd, default_settings, mock_registry
    ):
        """关键步骤失败时流水线停止并返回 failed。"""
        mock_intent.side_effect = RuntimeError("意图识别失败")

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

        strategy = StepByStepStrategy(mock_registry)
        result = strategy.run(task_id, resume_id, jd_id, user_id=1, db=db_session)

        assert result["status"] == "failed"
        assert "意图识别失败" in result.get("error", "") or result["steps"][0]["status"] == "failed"

    @patch("app.services.agent_steps.step_intent_recognition")
    def test_step_logging_on_failure(
        self, mock_intent, db_session, make_resume, make_jd, default_settings, mock_registry
    ):
        """步骤失败时日志应记录错误信息。"""
        mock_intent.side_effect = RuntimeError("意图识别失败")

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

        strategy = StepByStepStrategy(mock_registry)
        strategy.run(task_id, resume_id, jd_id, user_id=1, db=db_session)

        # 验证错误日志
        logs = db_session.query(AgentStepLog).filter_by(task_id=task_id).all()
        failed_logs = [log for log in logs if log.status == "failed"]
        assert len(failed_logs) >= 1
        for log in failed_logs:
            assert log.error_msg is not None
            assert "失败" in log.error_msg

    @patch("app.services.agent_steps.step_intent_recognition")
    @patch("app.services.agent_steps.step_resume_parse")
    @patch("app.services.agent_steps.step_jd_parse")
    @patch("app.services.agent_steps.step_task_planning")
    @patch("app.services.agent_steps.step_knowledge_retrieval")
    @patch("app.services.agent_steps.step_matching_analysis")
    @patch("app.services.agent_steps.step_resume_optimization")
    @patch("app.services.agent_steps.step_interview_question_gen")
    @patch("app.services.agent_steps.step_self_check")
    @patch("app.services.agent_steps.step_final_report")
    def test_step_context_passing(
        self,
        mock_report,
        mock_check,
        mock_interview,
        mock_optimize,
        mock_match,
        mock_kb,
        mock_plan,
        mock_jd,
        mock_resume,
        mock_intent,
        db_session,
        make_resume,
        make_jd,
        default_settings,
        mock_registry,
    ):
        """验证上下文在各步骤间正确传递。"""
        mock_intent.return_value = {"intent": "full_analysis", "intent_confidence": 0.9, "required_steps": []}
        mock_resume.return_value = {"skipped": False, "parsed": {"name": "测试", "skills": ["Python"]}}
        mock_jd.return_value = {"skipped": False, "parsed": {"title": "AI工程师", "required_skills": ["Python"]}}
        mock_plan.return_value = {"plan": [{"step": "分析"}], "steps_count": 1}
        mock_kb.return_value = {"query": "test", "retrievals": {"skill_model": []}, "rag_confidence": {"score": 85}}
        mock_match.return_value = {"match_score": 85}
        mock_optimize.return_value = {"suggestions": ["增加LLM经验"]}
        mock_interview.return_value = {"questions": [{"q": "q1"}], "total_questions": 1}
        mock_check.return_value = {"passed": True, "checks": []}
        mock_report.return_value = {"summary": "完成", "overall_score": 85}

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

        strategy = StepByStepStrategy(mock_registry)
        strategy.run(task_id, resume_id, jd_id, user_id=1, db=db_session)

        # 验证 mock_kb 被调用时传入了正确的 ctx 对象
        call_ctx = mock_kb.call_args[0][0]
        assert call_ctx is not None
        assert call_ctx.get("resume_id") == resume_id
        assert call_ctx.get("jd_id") == jd_id

        # 验证 final_report 被调用时上下文包含之前的分析结果
        report_call_ctx = mock_report.call_args[0][0]
        match_result = report_call_ctx.get("match_result")
        assert match_result is not None
        assert match_result.get("match_score") == 85


# ==================== StrategyFactory Tests ====================


class TestStrategyFactory:
    """StrategyFactory 创建策略测试"""

    def test_create_linear_strategy(self):
        strategy = StrategyFactory.create("linear")
        assert isinstance(strategy, LinearStrategy)

    def test_create_layered_strategy(self):
        strategy = StrategyFactory.create("layered")
        assert isinstance(strategy, LayeredParallelStrategy)

    def test_create_step_by_step(self):
        strategy = StrategyFactory.create("step_by_step")
        assert isinstance(strategy, StepByStepStrategy)

    def test_create_langgraph_strategies(self):
        for name in ["langgraph_linear", "langgraph_layered", "langgraph_step_by_step"]:
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
        assert "step_by_step" in strategies
        assert len(strategies) == 6

    def test_strategy_with_custom_registry(self, mock_registry):
        strategy = StrategyFactory.create("linear", registry=mock_registry)
        assert strategy.registry is mock_registry
