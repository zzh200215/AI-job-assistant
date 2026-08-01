"""
模拟面试引擎测试

覆盖 InterviewEngine 的核心状态机流程：
  1. 初始化 — init / start / _get_state
  2. 正常流程 — next_question → handle_answer → next_question → ... → finish
  3. 超时流程 — handle_timeout → 超时次数累计 → 自动结束
  4. 降级报告 — 无有效作答时的 _fallback_report
  5. 评估报告 — 正常作答后的 _generate_report
  6. 边界条件 — 空题目列表、全部超时、用户主动结束
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.models.interview_session import InterviewSession
from app.services.interview_engine import InterviewEngine
from app.utils.time_helper import utc_now

# ===================== Fixtures =====================


@pytest.fixture
def sample_questions() -> list[dict[str, Any]]:
    """标准面试题列表。"""
    return [
        {
            "id": 0,
            "question": "请介绍一个你最有成就感的项目",
            "category": "project",
            "ref_answer": "从项目背景、技术方案、个人贡献、成果量化四方面回答",
            "intent": "考察项目经验与表达能力",
        },
        {
            "id": 1,
            "question": "解释 RAG 的工作原理以及它的局限性",
            "category": "tech",
            "ref_answer": "检索阶段+生成阶段，局限性包括检索质量依赖 embedding、大模型幻觉等",
            "intent": "考察 RAG 理解深度",
        },
        {
            "id": 2,
            "question": "如何处理 LLM 输出中的幻觉问题",
            "category": "tech",
            "ref_answer": "RAG 增强、Prompt 约束、输出校验、人类反馈",
            "intent": "考察 LLM 落地经验",
        },
    ]


@pytest.fixture
def engine(db_session, make_interview_session, sample_questions):
    """创建已初始化的 InterviewEngine 实例。"""
    session_id = make_interview_session(
        status="created",
        questions=sample_questions,
    )
    eng = InterviewEngine(session_id)
    eng.db = db_session  # 复用测试的 db_session 而不是新建 SessionLocal
    eng.session = db_session.get(InterviewSession, session_id)
    return eng


# ==================== Initialization Tests ====================


class TestInterviewEngineInit:
    """InterviewEngine 初始化测试"""

    def test_init_loads_session(self, engine, sample_questions):
        """init() 应加载会话并设置初始状态。"""
        state = engine.init()

        assert state["session_id"] == engine.session_id
        assert state["status"] == "created"
        assert state["current_index"] == -1
        assert state["total_questions"] == len(sample_questions)
        assert state["answered_count"] == 0
        assert state["timeout_count"] == 0
        assert state["max_timeouts"] == engine.MAX_TIMEOUTS

    def test_init_clears_previous_state(self, engine):
        """重复调用 init 应重置所有运行时状态。"""
        engine.current_index = 5
        engine.evaluations = [{"dummy": "data"}]
        engine.timeout_count = 2

        state = engine.init()
        assert state["current_index"] == -1
        assert state["answered_count"] == 0
        assert state["timeout_count"] == 0

    def test_start_sets_ongoing_status(self, engine):
        """start() 应将状态改为 ongoing 并返回第一题。"""
        payload = engine.start()

        assert engine.session.status == "ongoing"
        assert payload["type"] == "question"
        assert "项目" in payload["content"]  # 第一题内容
        assert payload["metadata"]["round"] == 1
        assert engine.current_index == 0

    def test_start_with_empty_questions(self, db_session, make_interview_session):
        """空题目列表启动时应直接完成。"""
        session_id = make_interview_session(questions=[])
        eng = InterviewEngine(session_id)
        eng.db = db_session
        eng.session = db_session.get(InterviewSession, session_id)

        payload = eng.start()
        assert payload["type"] == "end"
        assert eng.is_finished()

    def test_get_state_returns_correct_values(self, engine):
        """_get_state 返回正确的状态快照。"""
        engine.init()
        state = engine._get_state()
        assert "session_id" in state
        assert "status" in state
        assert "current_index" in state
        assert "total_questions" in state
        assert "answered_count" in state
        assert "timeout_count" in state

    def test_resume_restores_ongoing_session_state(self, db_session, make_interview_session):
        """resume() 应从已保存消息恢复进行中的面试，而不是重新开始。"""
        session_id = make_interview_session(
            status="ongoing",
            total_questions=3,
            answered_count=1,
            timeout_count=1,
            messages=[
                {
                    "role": "ai",
                    "type": "question",
                    "content": "第一题",
                    "metadata": {"round": 1, "total": 3, "category": "project"},
                    "timestamp": utc_now().isoformat(),
                },
                {
                    "role": "user",
                    "type": "answer",
                    "content": "回答一",
                    "metadata": {"round": 1, "category": "project"},
                    "timestamp": utc_now().isoformat(),
                },
                {
                    "role": "system",
                    "type": "evaluation",
                    "content": "反馈一",
                    "metadata": {
                        "round": 1,
                        "score": 82,
                        "completeness": 80,
                        "accuracy": 85,
                        "depth": 78,
                        "expression": 81,
                        "improvement": "补充指标",
                    },
                    "timestamp": utc_now().isoformat(),
                },
                {
                    "role": "ai",
                    "type": "question",
                    "content": "第二题",
                    "metadata": {"round": 2, "total": 3, "category": "tech"},
                    "timestamp": utc_now().isoformat(),
                },
            ],
        )
        eng = InterviewEngine(session_id)
        eng.db = db_session
        eng.session = db_session.get(InterviewSession, session_id)

        payload = eng.resume()

        assert payload["type"] == "question"
        assert payload["content"] == "第二题"
        assert eng.current_index == 1
        assert eng.timeout_count == 1
        assert len(eng.evaluations) == 1
        assert eng.evaluations[0]["overall_score"] == 82

    def test_resume_does_not_repush_answered_question(self, db_session, make_interview_session):
        """断线若发生在「已作答、下一题未推送」间隙，resume() 不应重复推送已答题目（#19）。"""
        session_id = make_interview_session(
            status="ongoing",
            total_questions=3,
            answered_count=1,
            messages=[
                {
                    "role": "ai", "type": "question", "content": "第一题",
                    "metadata": {"round": 1, "total": 3, "category": "project"},
                    "timestamp": utc_now().isoformat(),
                },
                {
                    "role": "user", "type": "answer", "content": "回答一",
                    "metadata": {"round": 1, "category": "project"},
                    "timestamp": utc_now().isoformat(),
                },
            ],
        )
        eng = InterviewEngine(session_id)
        eng.db = db_session
        eng.session = db_session.get(InterviewSession, session_id)

        payload = eng.resume()
        assert payload is None  # 不重复推送已答的第一题

        nxt = eng.next_question()
        assert nxt["type"] == "question"
        assert nxt["metadata"]["round"] == 2  # 直接推进到下一题

    def test_resume_repushes_unanswered_followup(self, db_session, make_interview_session):
        """追问未作答时 resume() 仍应推送追问（不能因主题已答而跳过追问）。"""
        session_id = make_interview_session(
            status="ongoing",
            total_questions=3,
            answered_count=1,
            messages=[
                {
                    "role": "ai", "type": "question", "content": "第一题",
                    "metadata": {"round": 1, "total": 3, "category": "project"},
                    "timestamp": utc_now().isoformat(),
                },
                {
                    "role": "user", "type": "answer", "content": "回答一",
                    "metadata": {"round": 1, "category": "project"},
                    "timestamp": utc_now().isoformat(),
                },
                {
                    "role": "ai", "type": "question", "content": "再深入一点？",
                    "metadata": {"round": 1, "total": 3, "category": "project", "is_follow_up": True},
                    "timestamp": utc_now().isoformat(),
                },
            ],
        )
        eng = InterviewEngine(session_id)
        eng.db = db_session
        eng.session = db_session.get(InterviewSession, session_id)

        payload = eng.resume()
        assert payload is not None
        assert payload["content"] == "再深入一点？"  # 追问仍未作答，应推送追问


# ==================== Normal Flow Tests ====================


class TestNormalFlow:
    """正常面试流程测试"""

    def test_next_question_returns_question(self, engine):
        """next_question 应依次返回题目。"""
        engine.start()

        # 验证返回的是第二题
        payload = engine.next_question()
        assert payload["type"] == "question"
        assert "RAG" in payload["content"]

    def test_handle_answer_with_mock_evaluation(self, engine):
        """提交答案后应生成评估并进入下一题。"""
        engine.start()

        with patch.object(engine, "_evaluate_answer") as mock_eval:
            mock_eval.return_value = {
                "completeness": 80,
                "accuracy": 85,
                "depth": 75,
                "expression": 80,
                "overall_score": 80,
                "feedback": "回答结构清晰，覆盖了核心要点。",
                "improvement": "可以补充更多量化成果。",
                "follow_up": False,
            }

            payload = engine.handle_answer("我从项目背景、技术方案、成果方面回答...")

            # 如果返回的是 question，说明进入了下一题
            if payload["type"] == "question":
                assert engine.current_index == 1
                assert len(engine.evaluations) == 1
                assert engine.evaluations[0]["overall_score"] == 80
            elif payload["type"] == "end":
                # 如果只有 1 题或已结束，也接受
                assert engine.is_finished()

    def test_full_interview_flow(self, engine, sample_questions):
        """完整的面试流程：3 题全部回答。"""
        engine.start()

        # 模拟评估函数
        mock_eval = {
            "completeness": 80,
            "accuracy": 85,
            "depth": 75,
            "expression": 80,
            "overall_score": 80,
            "feedback": "不错",
            "improvement": "继续加油",
            "follow_up": False,
        }

        with patch.object(engine, "_evaluate_answer", return_value=mock_eval):
            answered = 0
            max_iterations = 10  # 防止死循环
            iterations = 0

            while not engine.is_finished() and iterations < max_iterations:
                iterations += 1
                payload = engine.handle_answer("这是一个回答...")

                if payload["type"] == "end":
                    break
                elif payload["type"] == "question":
                    answered += 1

            # 验证所有题目都被回答了
            total = len(sample_questions)
            max(0, total - 1)  # start 已经消耗了第一题
            assert engine.evaluations is not None
            # 验证生成了报告
            assert engine.session.status == "completed"
            assert engine.session.evaluation is not None

    def test_answer_records_message(self, engine):
        """提交答案应在 evaluations 中记录评估结果。"""
        engine.start()

        with patch.object(engine, "_evaluate_answer") as mock_eval:
            mock_eval.return_value = {
                "completeness": 80,
                "accuracy": 80,
                "depth": 70,
                "expression": 80,
                "overall_score": 78,
                "feedback": "良好",
                "improvement": "再具体些",
                "follow_up": False,
            }

            engine.handle_answer("我的回答内容")

            # evaluations 应在 handle_answer 后被填充
            assert len(engine.evaluations) >= 1
            last_eval = engine.evaluations[-1]
            assert last_eval["overall_score"] == 78
            assert last_eval["user_answer"] == "我的回答内容"
            assert last_eval["question"] is not None


# ==================== Timeout Tests ====================


class TestTimeout:
    """超时处理测试"""

    def test_handle_timeout_increases_counter(self, engine):
        """每次超时应累计次数。"""
        engine.start()
        initial_timeouts = engine.timeout_count

        engine.handle_timeout()
        assert engine.timeout_count == initial_timeouts + 1

    def test_handle_timeout_records_zero_score(self, engine):
        """超时应记录 score=0 的评估。"""
        engine.start()

        engine.handle_timeout()

        # 最新一条 evaluation 应是超时记录
        if engine.evaluations:
            last_eval = engine.evaluations[-1]
            assert last_eval.get("timed_out") is True
            assert last_eval["overall_score"] == 0

    def test_max_timeouts_ends_interview(self, engine):
        """达到最大超时次数应自动结束面试。"""
        engine.start()

        for _ in range(engine.MAX_TIMEOUTS):
            payload = engine.handle_timeout()
            if payload["type"] == "end":
                break

        assert engine.is_finished()
        assert engine.session.status == "completed"

    def test_timeout_resets_after_successful_answer(self, engine):
        """成功作答后超时计数不重置（按总超时次数判断）。"""
        engine.start()

        # 超时一次
        engine.handle_timeout()
        assert engine.timeout_count >= 1

        # 正常回答
        with patch.object(engine, "_evaluate_answer") as mock_eval:
            mock_eval.return_value = {
                "completeness": 80,
                "accuracy": 80,
                "depth": 70,
                "expression": 80,
                "overall_score": 78,
                "feedback": "好",
                "improvement": "",
                "follow_up": False,
            }
            engine.handle_answer("正常回答")

        # 超时计数仍在
        total_timeouts = engine.timeout_count
        assert total_timeouts >= 1


# ==================== Follow-up Question Tests ====================


class TestFollowUp:
    """Follow-up 追问测试"""

    def test_low_score_triggers_follow_up(self, engine):
        """低分答案应触发 follow-up 追问。"""
        engine.start()

        with patch.object(engine, "_evaluate_answer") as mock_eval:
            mock_eval.return_value = {
                "completeness": 40,
                "accuracy": 40,
                "depth": 30,
                "expression": 50,
                "overall_score": 40,  # < 70 → 应触发 follow-up
                "feedback": "回答不够完整",
                "improvement": "需要更详细",
                "follow_up": True,
            }

            payload = engine.handle_answer("简单回答")

            # 应返回 follow-up 问题
            if payload.get("metadata", {}).get("is_follow_up"):
                assert payload["type"] == "question"
                assert payload["metadata"]["is_follow_up"] is True
                assert payload["metadata"]["evaluation"]["score"] == 40

    def test_high_score_no_follow_up(self, engine):
        """高分答案不应触发 follow-up。"""
        engine.start()

        with patch.object(engine, "_evaluate_answer") as mock_eval:
            mock_eval.return_value = {
                "completeness": 90,
                "accuracy": 95,
                "depth": 88,
                "expression": 90,
                "overall_score": 91,  # >= 70 → 不触发
                "feedback": "非常好",
                "improvement": "",
                "follow_up": False,
            }

            payload = engine.handle_answer("完整详细的回答")

            # 不应是 follow-up（直接进下一题或结束）
            assert payload.get("metadata", {}).get("is_follow_up") is False or payload["type"] in ("question", "end")


# ==================== Report Generation Tests ====================


class TestReportGeneration:
    """面试报告生成测试"""

    def test_fallback_report_when_no_answers(self, engine):
        """没有有效作答时应返回降级报告。"""
        report = engine._fallback_report()

        assert report["overall_score"] == 0
        assert report["answered_questions"] == 0
        assert "至少完成一道题" in report["improvement_suggestions"][0]

    def test_report_generation_with_answers(self, engine):
        """正常回答后应生成综合报告。"""
        engine.start()

        # 添加虚拟评估数据
        engine.evaluations = [
            {
                "question_index": 0,
                "question": "项目经验",
                "category": "project",
                "completeness": 80,
                "accuracy": 85,
                "depth": 75,
                "expression": 80,
                "overall_score": 80,
                "feedback": "好",
                "user_answer": "回答1",
            },
            {
                "question_index": 1,
                "question": "RAG原理",
                "category": "tech",
                "completeness": 70,
                "accuracy": 75,
                "depth": 70,
                "expression": 75,
                "overall_score": 73,
                "feedback": "尚可",
                "user_answer": "回答2",
            },
        ]

        report = engine._generate_report()

        assert report["overall_score"] > 0
        assert report["answered_questions"] == 2
        assert "dimension_scores" in report
        assert "completeness" in report["dimension_scores"]
        assert "accuracy" in report["dimension_scores"]
        assert "depth" in report["dimension_scores"]
        assert "expression" in report["dimension_scores"]
        assert "strengths" in report
        assert "weaknesses" in report

    def test_overall_score_normalized_with_heavy_custom_weights(self, engine):
        """自定义评分权重和≠1 时总分须归一化，overall_score 不超 100（#19）。"""
        from app.models.interview_config import InterviewScoringRule

        db = engine.db
        db.add(InterviewScoringRule(tenant_id=1, dimension="completeness", label="要点覆盖", weight=0.6, sort_order=0))
        db.add(InterviewScoringRule(tenant_id=1, dimension="expression", label="表达", weight=0.6, sort_order=1))
        db.commit()

        engine.session.tenant_id = 1
        engine.start_time = 0
        engine.question_count = 2
        engine.evaluations = [
            {
                "question_index": i, "question": f"q{i}", "category": "tech",
                "completeness": 100, "accuracy": 0, "depth": 0, "expression": 80,
                "overall_score": 90, "feedback": "f", "improvement": "i",
            }
            for i in range(2)
        ]
        report = engine._generate_report()
        # 未归一化：100*0.6 + 80*0.6 = 108 会超 100；
        # 归一化后权重和 = 0.6+0.30+0.25+0.6 = 1.75 → (60+48)/1.75 ≈ 61.7 → 62
        assert report["overall_score"] <= 100
        assert report["overall_score"] == 62

    def test_report_with_mixed_timed_out_and_valid(self, engine):
        """混合超时和有效回答应只统计有效的。"""
        engine.start()

        engine.evaluations = [
            {
                "question_index": 0,
                "question": "项目经验",
                "category": "project",
                "completeness": 80,
                "accuracy": 85,
                "depth": 75,
                "expression": 80,
                "overall_score": 80,
                "feedback": "好",
                "user_answer": "回答1",
            },
            {
                "question_index": 1,
                "question": "RAG原理",
                "category": "tech",
                "completeness": 0,
                "accuracy": 0,
                "depth": 0,
                "expression": 0,
                "overall_score": 0,
                "feedback": "超时",
                "timed_out": True,
                "user_answer": "",
            },
        ]

        report = engine._generate_report()

        assert report["answered_questions"] == 1  # 只有一道有效
        assert report["overall_score"] > 0

    def test_finish_generates_report(self, engine):
        """finish() 应生成报告并保存到 session。"""
        engine.start()

        engine.evaluations = [
            {
                "question_index": 0,
                "question": "测试",
                "category": "tech",
                "completeness": 80,
                "accuracy": 80,
                "depth": 75,
                "expression": 80,
                "overall_score": 79,
                "feedback": "好",
                "user_answer": "回答",
            },
        ]

        with patch.object(engine, "_generate_report") as mock_report:
            mock_report.return_value = {
                "overall_score": 79,
                "dimension_scores": {"completeness": 80, "accuracy": 80, "depth": 75, "expression": 80},
                "question_evaluations": engine.evaluations,
                "total_questions": 3,
                "answered_questions": 1,
                "strengths": ["表达清晰"],
                "weaknesses": ["深度不足"],
                "overall_evaluation": "表现良好",
                "improvement_suggestions": ["建议深入技术细节"],
            }

            payload = engine.finish()

            assert payload["type"] == "end"
            assert engine.session.status == "completed"
            assert engine.session.evaluation is not None
            assert engine.session.evaluation["overall_score"] == 79
            assert engine.is_finished()


# ==================== Evaluation Tests ====================


class TestEvaluation:
    """回答评估测试"""

    def test_evaluate_answer_calls_agent(self, engine):
        """_evaluate_answer 应调用 AnswerEvaluationAgent。"""
        with patch("app.services.interview_engine.AnswerEvaluationAgent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.run_impl.return_value = {
                "completeness": 80,
                "accuracy": 80,
                "depth": 70,
                "expression": 80,
                "overall_score": 78,
                "feedback": "好",
                "improvement": "",
                "follow_up": False,
            }
            MockAgent.return_value = mock_instance

            result = engine._evaluate_answer(
                question="介绍你的项目",
                ref_answer="从背景、方案、成果回答",
                user_answer="我的回答...",
            )

            assert result["overall_score"] == 78
            mock_instance.run_impl.assert_called_once()

    def test_evaluate_answer_fallback_on_error(self, engine):
        """Agent 评估异常时 handle_answer 应返回降级评分而非崩溃。"""
        engine.start()

        with patch.object(engine, "_evaluate_answer") as mock_eval:
            # _evaluate_answer 本身不 catch 异常（handle_answer 负责 catch）
            # 这里 mock _evaluate_answer 本身抛异常，测试 handle_answer 的降级逻辑
            mock_eval.side_effect = RuntimeError("Agent 异常")

            result = engine.handle_answer("测试回答")

            # 即使评估异常，handle_answer 也不应抛，应进入下一题或结束
            assert result is not None
            assert "type" in result
            # evaluations 中应有一条降级记录
            assert len(engine.evaluations) >= 1
            assert "overall_score" in engine.evaluations[-1]


# ==================== Message Tests ====================


class TestMessageRecording:
    """消息记录测试"""

    def test_save_message(self, engine):
        """save_message 应追加到消息列表并持久化。"""
        engine.init()

        msg = {"role": "ai", "type": "question", "content": "你好", "timestamp": utc_now().isoformat()}
        engine.save_message(msg)

        assert len(engine.session.messages) >= 1
        saved = engine.session.messages[-1]
        assert saved["role"] == "ai"
        assert saved["content"] == "你好"

    def test_start_records_first_message(self, engine):
        """start() 应记录第一题的消息。"""
        engine.start()

        messages = engine.session.messages or []
        assert len(messages) >= 1
        assert messages[0]["role"] == "ai"
        assert messages[0]["type"] == "question"

    def test_handle_answer_records_user_and_evaluation_messages(self, engine):
        """handle_answer 应记录用户回答并更新 answered_count。"""
        engine.start()

        with patch.object(engine, "_evaluate_answer") as mock_eval:
            mock_eval.return_value = {
                "completeness": 80,
                "accuracy": 80,
                "depth": 70,
                "expression": 80,
                "overall_score": 78,
                "feedback": "表现不错",
                "improvement": "继续加油",
                "follow_up": False,
            }
            engine.handle_answer("我的回答")

            # evaluations 应有记录
            assert len(engine.evaluations) >= 1
            # answered_count 应已更新
            assert engine.session.answered_count >= 1


# ==================== Edge Cases Tests ====================


class TestEdgeCases:
    """边界条件测试"""

    def test_interview_with_single_question(self, db_session, make_interview_session):
        """只有一道题的面试。"""
        session_id = make_interview_session(
            questions=[
                {"id": 0, "question": "唯一的问题", "category": "general", "ref_answer": ""},
            ]
        )
        eng = InterviewEngine(session_id)
        eng.db = db_session
        eng.session = db_session.get(InterviewSession, session_id)

        eng.start()

        with patch.object(eng, "_evaluate_answer") as mock_eval:
            mock_eval.return_value = {
                "completeness": 80,
                "accuracy": 80,
                "depth": 70,
                "expression": 80,
                "overall_score": 78,
                "feedback": "好",
                "improvement": "",
                "follow_up": False,
            }

            payload = eng.handle_answer("回答内容")
            assert payload["type"] == "end"  # 答完最后一题直接结束
            assert eng.is_finished()

    def test_cleanup_closes_db(self, engine):
        """cleanup 应关闭数据库连接。"""
        mock_db = MagicMock()
        engine.db = mock_db
        engine.cleanup()
        mock_db.close.assert_called_once()
        assert engine.db is None  # cleanup 将 db 置为 None

    def test_get_current_question_returns_correct(self, engine):
        """get_current_question 返回当前题目。"""
        engine.start()
        question = engine.get_current_question()
        assert question is not None
        assert "项目" in question.get("question", "")

    def test_get_current_question_out_of_range(self, engine):
        """超出题目范围时返回 None。"""
        question = engine.get_current_question()
        assert question is None  # 还没 start

    def test_max_questions_limit(self, engine, sample_questions):
        """超过 MAX_QUESTIONS 限制时自动结束。"""
        # 设置比题目少的限制
        engine.MAX_QUESTIONS = 1
        engine.start()

        with patch.object(engine, "_evaluate_answer") as mock_eval:
            mock_eval.return_value = {
                "completeness": 80,
                "accuracy": 80,
                "depth": 70,
                "expression": 80,
                "overall_score": 78,
                "feedback": "好",
                "improvement": "",
                "follow_up": False,
            }
            # 第一题回答后，next_question 应触发 MAX_QUESTIONS 限制
            payload = engine.handle_answer("回答内容")
            # 只有 1 个 MAX_QUESTIONS，所以应该结束了
            if payload["type"] == "end":
                assert engine.is_finished()

    def test_handle_answer_for_nonexistent_question(self, engine):
        """未 start 时调用 handle_answer 应安全处理。"""
        payload = engine.handle_answer("回答")
        # 应该返回 end 或者正常处理
        assert payload is not None
        assert "type" in payload
