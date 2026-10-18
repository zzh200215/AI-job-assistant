"""P3.1 第二格：把引擎的题源接到决策器（护栏先落，2026-10-17）。

上一格落了决策器本体（`interviewer_decision.py`，护栏 14 条全绿），这一格接 `next_question`。
接之前先在库里量到一件事，它决定了这份护栏的形状：

**超时那一题不许触发深挖。** `_rebuild_evaluations()` 对超时写的是 `overall_score = 0` 且带
`timed_out: True`（`app/services/interview_engine.py:664-681`）。决策器的启发式只看分数，
0 < 70 ⇒ 判 deepen——于是候选人**一个字都没答**的那题，面试官会追一句"你刚才提到的成果怎么量化的"。
那不是深挖，那是幻觉。所以题面为空/超时这一档必须在进决策器之前就被排除，这条要钉死。

另外六条断言全部围绕"接线不许改变今天的顺序行为"：原稿护栏第 4 条写的是**现有面试测试全绿**，
所以深挖只允许在"答了、分低、有 evidence、且这题还没追问过"这一种输入下发生，其余一律走原来
那条按下标取题的路。

测试用 monkeypatch 把 `_rebuild_evaluations()` 换成造好的评估列表：这一格要证的是**接线**
（决策结果怎么变成消息、指针动不动、metadata 长什么样），不是评估怎么落库——那是
`test_interview_async_evaluation.py` 那一族的事。
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.interview_session import InterviewSession
from app.services.interview_engine import InterviewEngine


def _question(index: int, text: str, category: str = "tech") -> dict:
    return {"id": index, "question": text, "category": category, "ref_answer": "参考答案", "intent": "考察"}


@pytest.fixture
def engine(db_session, make_interview_session):
    questions = [
        _question(0, "请介绍一个你最有成就感的项目", "project"),
        _question(1, "解释 RAG 的工作原理以及它的局限性"),
        _question(2, "如何处理 LLM 输出中的幻觉问题"),
    ]
    session_id = make_interview_session(status="ongoing", questions=questions)
    eng = InterviewEngine(session_id)
    eng.db = db_session
    eng.session = db_session.get(InterviewSession, session_id)
    eng.current_index = 0
    return eng


def _evaluations(*items: dict) -> list[dict]:
    """造评估行。补齐引擎后续路径要读的字段（`_fallback_report` 会逐条读四维分），
    不然测的就不是接线而是夹具缺键的 KeyError。"""
    base = {
        "completeness": 60,
        "accuracy": 60,
        "depth": 60,
        "expression": 60,
        "feedback": "反馈",
        "improvement": "改进建议",
        "evidence": [],
        "user_answer": "答了",
        "follow_up": False,
    }
    return [
        {"question_index": i, "question": f"q{i}", "category": "tech", **base, **item} for i, item in enumerate(items)
    ]


def _stub(eng: InterviewEngine, monkeypatch, evaluations: list[dict]) -> None:
    monkeypatch.setattr(eng, "_rebuild_evaluations", lambda: evaluations)


def test_timeout_is_not_a_followup_trigger(engine, monkeypatch) -> None:
    """超时那题得分是 0，但候选人没说过任何东西 ⇒ 不许深挖，下一题照旧按顺序出。"""
    _stub(
        engine,
        monkeypatch,
        _evaluations({"overall_score": 0, "timed_out": True, "evidence": [], "user_answer": "", "follow_up": False}),
    )
    payload = engine.next_question()
    assert engine.current_index == 1, "超时之后指针被追问占了位"
    assert "RAG 的工作原理" in payload["content"], payload["content"]
    assert payload["metadata"].get("decision", {}).get("action") != "deepen", payload["metadata"]


def test_low_score_answer_triggers_one_followup_without_moving_the_pointer(engine, monkeypatch) -> None:
    """答了、45 分、有证据 ⇒ 出一条单点追问，且**不推进 current_index**（追问不是新的一题）。"""
    _stub(
        engine,
        monkeypatch,
        _evaluations(
            {"overall_score": 88, "evidence": ["量化不足"], "user_answer": "我做了个 RAG", "follow_up": False}
        ),
    )
    first = engine.next_question()  # index 语义：current_index 是"已发出的最后一题"下标，先自增再取
    _stub(
        engine,
        monkeypatch,
        _evaluations(
            {"overall_score": 88, "evidence": ["量化不足"], "user_answer": "我做了个 RAG", "follow_up": False},
            {"overall_score": 45, "evidence": ["成果没有量化"], "user_answer": "大致提效不少", "follow_up": False},
        ),
    )
    followup = engine.next_question()
    assert first["metadata"]["round"] == 2, first["metadata"]
    assert followup["metadata"].get("is_follow_up") is True, followup["metadata"]
    assert followup["metadata"]["decision"]["action"] == "deepen", followup["metadata"]
    assert engine.current_index == 1, f"追问把指针推到了 {engine.current_index}"
    assert "成果" in followup["content"] or "量化" in followup["content"], followup["content"]


def test_followup_is_not_counted_in_total_or_round(engine, monkeypatch) -> None:
    """追问不算新题号、不改 total——前端的进度条分母是 total，指针一多一少就会画歪。"""
    _stub(
        engine,
        monkeypatch,
        _evaluations({"overall_score": 40, "evidence": ["没有结论"], "user_answer": "还行吧", "follow_up": False}),
    )
    payload = engine.next_question()
    assert payload["metadata"]["round"] == 1, payload["metadata"]
    assert payload["metadata"]["total"] == 3, payload["metadata"]


def test_only_one_followup_per_question(engine, monkeypatch) -> None:
    """已经追问过一次的题不许再追（同一条短板不能问到底）。"""
    _stub(
        engine,
        monkeypatch,
        _evaluations(
            {"overall_score": 40, "evidence": ["没有结论"], "user_answer": "还行吧", "follow_up": True},
        ),
    )
    payload = engine.next_question()
    assert payload["metadata"].get("is_follow_up") is not True, payload["metadata"]
    assert engine.current_index == 1, payload["metadata"]


def test_six_existing_metadata_keys_survive_the_wiring(engine, monkeypatch) -> None:
    """接了决策器之后，既有六个 metadata 键一个都不许少（协议文档那条同步断言的反面腿）。"""
    _stub(
        engine,
        monkeypatch,
        _evaluations({"overall_score": 50, "evidence": ["太浅"], "user_answer": "答了", "follow_up": False}),
    )
    metadata = engine.next_question()["metadata"]
    for key in ("round", "total", "category", "timeout_seconds", "question_id", "turn_id"):
        assert key in metadata, f"接线后 metadata 少了既有键 {key}：{metadata}"


def test_flag_off_reproduces_todays_sequence_exactly(engine, monkeypatch) -> None:
    """关掉 `INTERVIEW_USE_DECIDER` ⇒ 行为与今天逐字相同：三题按顺序出、永不追问。

    这一条是原稿第 4 条护栏（现有面试测试不回退）的可执行版本：万一动态那一档在生产上
    出了意料外的行为，关一个开关就能回到今天这条链，而不是回滚代码。
    """
    monkeypatch.setattr(settings, "INTERVIEW_USE_DECIDER", False)
    _stub(
        engine,
        monkeypatch,
        _evaluations({"overall_score": 30, "evidence": ["很模糊"], "user_answer": "随便说的", "follow_up": False}),
    )
    payloads = [engine.next_question() for _ in range(3)]
    texts = [p["content"] for p in payloads]
    # 夹具里 current_index=0 表示"第 1 题已发出"，所以顺序是后两题 + 收尾。
    assert "RAG 的工作原理" in texts[0], texts
    assert "幻觉问题" in texts[1], texts
    assert payloads[2]["type"] == "finished" or "完成" in texts[2], texts
    assert all(not p["metadata"].get("is_follow_up") for p in payloads[:2]), "开关关着还出追问"
    assert engine.current_index == 3, engine.current_index
