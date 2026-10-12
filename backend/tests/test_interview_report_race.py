"""D225：面试逐题点评从 JSON 列搬进表之后，钉住三件事——不丢、不双、不被过期写覆盖。

背景（D224 现场）：真跑一场面试时 10 个评分 worker 各自"读整列-改-写整列"同一个 JSON 列，
后提交的把先提交的抹掉，10 条点评只剩 6 条；而收尾那次 40 秒的报告调用又用它早已过期的内存视图
写回了一遍，于是会话 `status=completed` 却 `evaluation_status=processing`、报告 0 分。
测试里从来红不了，是因为 mock 评分是瞬时的、这些写入根本不会重叠。

这里的复现不需要线程：把 D224 的**顺序**原样重放（评分全部落地 → 报告 worker 最后写），
就能确定性地撞到同一个形状。
"""

from __future__ import annotations

from app.models.interview_evaluation import InterviewTurnEvaluation
from app.models.interview_session import InterviewSession
from app.services import interview_evaluation_service as ies
from app.services.interview_engine import InterviewEngine

QUESTIONS = [
    {
        "id": 1,
        "question": "介绍一个你主导的技术项目。",
        "category": "project",
        "ref_answer": "说明背景、方案、个人贡献和量化结果。",
    },
    {
        "id": 2,
        "question": "如何设计可观测的异步任务系统？",
        "category": "tech",
        "ref_answer": "说明队列、重试、指标和告警。",
    },
]


def _engine(db_session, make_interview_session, *, status="completed"):
    session_id = make_interview_session(status=status, questions=QUESTIONS)
    engine = InterviewEngine(session_id)
    engine.db = db_session
    engine.session = db_session.get(InterviewSession, session_id)
    return engine


def _answer_and_question_messages(rounds=(1, 2)):
    messages = []
    for r in rounds:
        messages.append(
            {
                "role": "ai",
                "type": "question",
                "content": f"第 {r} 问题干",
                "metadata": {"round": r, "turn_id": f"q-{r}"},
            }
        )
        messages.append(
            {
                "role": "user",
                "type": "answer",
                "content": f"第 {r} 题回答",
                "metadata": {"round": r, "turn_id": f"q-{r}"},
            }
        )
    return messages


def _seed_rows(db_session, session_id, *, count=2, status="completed"):
    rows = []
    for index in range(count):
        row = InterviewTurnEvaluation(
            session_id=session_id,
            turn_id=f"q-{index + 1}",
            question_index=index,
            question=QUESTIONS[index % len(QUESTIONS)]["question"],
            category="project",
            user_answer=f"回答 {index + 1}",
            status=status,
            completeness=80,
            accuracy=80,
            depth=75,
            expression=80,
            overall_score=79,
            feedback="好",
            improvement="补数据",
            evidence={"source": "answer_evaluation_agent"},
        )
        db_session.add(row)
        rows.append(row)
    db_session.commit()
    return rows


def test_a_stale_finish_cannot_empty_a_report_that_is_already_complete(db_session, make_interview_session):
    """D224 的原样重放：评分全部先落地，报告 worker 最后才写它那份**过期**的内存视图。

    旧代码在这一步会把终报盖成"0 题、0 分"并停在 processing；现在锁内会先按表重建，
    所以落库的必须是那 2 条真实点评。
    """
    engine = _engine(db_session, make_interview_session)
    engine.session.messages = _answer_and_question_messages()
    _seed_rows(db_session, engine.session_id, count=2)
    db_session.commit()

    engine.evaluations = []  # ← 报告 worker 手上那份过期的东西（它是在评分落地之前 resume 的）
    payload = engine.finish()

    session = db_session.get(InterviewSession, engine.session_id)
    assert payload["type"] == "end"
    assert session.evaluation_status == "completed", session.evaluation_status
    assert len(session.evaluation["question_evaluations"]) == 2, session.evaluation
    assert session.evaluation["overall_score"] > 0, session.evaluation


def test_the_async_worker_no_longer_writes_the_messages_column(db_session, make_interview_session, monkeypatch):
    """竞争源必须是"没了"，不是"变小了"：后台评分不再整列赋值 `session.messages`。"""
    engine = _engine(db_session, make_interview_session, status="ongoing")
    engine.session.messages = _answer_and_question_messages(rounds=(1,))
    db_session.commit()
    record = _seed_rows(db_session, engine.session_id, count=1, status="pending")[0]

    monkeypatch.setattr(ies, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    class FakeAgent:
        def run_impl(self, _context):
            return {
                "completeness": 84,
                "accuracy": 82,
                "depth": 80,
                "expression": 78,
                "overall_score": 82,
                "feedback": "项目表达清楚。",
                "improvement": "补充业务收益。",
            }

    monkeypatch.setattr(ies, "AnswerEvaluationAgent", FakeAgent)
    before = list(engine.session.messages)
    ies.process_turn_evaluation(engine.session_id, record.id)
    db_session.refresh(engine.session)

    assert engine.session.messages == before, "后台 worker 还在往 JSON 列里写点评——那正是互相覆盖的地方"
    frames = [m for m in ies.build_conversation(db_session, engine.session) if m.get("type") == "evaluation"]
    assert len(frames) == 1 and frames[0]["metadata"]["turn_id"] == "q-1", frames


def test_a_session_without_rows_still_shows_the_evaluations_stored_in_json(db_session, make_interview_session):
    """兼容：表建成之前的那些会话，点评只在 JSON 里 —— 一个都不许少。"""
    engine = _engine(db_session, make_interview_session)
    engine.session.messages = _answer_and_question_messages() + [
        {
            "role": "system",
            "type": "evaluation",
            "content": "历史点评",
            "metadata": {"round": 1, "turn_id": "q-1", "score": 71},
        }
    ]
    db_session.commit()

    frames = [m for m in ies.build_conversation(db_session, engine.session) if m.get("type") == "evaluation"]
    assert len(frames) == 1 and frames[0]["content"] == "历史点评", frames


def test_a_row_and_its_stale_json_copy_are_not_rendered_twice(db_session, make_interview_session):
    """表接管之后，JSON 里那份同 turn_id 的旧副本要被丢掉，不能显示两遍。"""
    engine = _engine(db_session, make_interview_session)
    engine.session.messages = _answer_and_question_messages(rounds=(1,)) + [
        {
            "role": "system",
            "type": "evaluation",
            "content": "旧副本",
            "metadata": {"round": 1, "turn_id": "q-1", "score": 50},
        }
    ]
    _seed_rows(db_session, engine.session_id, count=1)
    db_session.commit()

    frames = [m for m in ies.build_conversation(db_session, engine.session) if m.get("type") == "evaluation"]
    assert len(frames) == 1, frames
    assert frames[0]["content"] == "好", frames


def test_the_snapshot_carries_the_derived_transcript_in_the_old_shape(db_session, make_interview_session):
    """前端零改动的前提：快照里的 messages 仍是老形状（点评紧跟在该题答案之后）。"""
    from app.api.interview_rest import _serialize_session

    engine = _engine(db_session, make_interview_session)
    engine.session.messages = _answer_and_question_messages(rounds=(1,))
    _seed_rows(db_session, engine.session_id, count=1)
    db_session.commit()

    payload = _serialize_session(engine.session, db_session)
    types = [m.get("type") for m in payload["messages"]]
    assert types == ["question", "answer", "evaluation"], types
    assert payload["turn_evaluations"][0]["turn_id"] == "q-1"
