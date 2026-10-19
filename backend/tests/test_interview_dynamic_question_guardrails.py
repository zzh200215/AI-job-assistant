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
from app.models.interview_evaluation import InterviewTurnEvaluation
from app.models.interview_session import InterviewSession
from app.services.interview_engine import InterviewEngine
from app.services.interview_evaluation_service import build_memory_snapshot


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


def test_followup_round_satisfies_the_answer_mapping_equation(engine, monkeypatch) -> None:
    """追问消息的 `round` 必须等于 `current_index + 1`。

    这条等式不是审美：`handle_answer` 判"这条答案是追问的回答"用的就是它
    （`interview_engine.py:266-270`）——`is_follow_up = 最新消息带追问标记 且 round == current_index + 1`。
    等式一旦不成立，那条答案会被当成**主题那一题**的答案、拿主题的 `turn_id` 去写评分行，
    于是主题的评分被覆盖。这条钉等式本身，下一条钉它的后果。
    """
    _stub(
        engine,
        monkeypatch,
        _evaluations({"overall_score": 40, "evidence": ["没有结论"], "user_answer": "还行吧", "follow_up": False}),
    )
    payload = engine.next_question()
    assert payload["metadata"].get("is_follow_up") is True, payload["metadata"]
    assert payload["metadata"]["round"] == engine.current_index + 1, payload["metadata"]


def test_answering_a_followup_writes_its_own_turn(engine, monkeypatch) -> None:
    """评分链按 turn 关联：追问的答案必须落在 `q-N-followup` 那一行上，不许借用主题的 turn_id。

    这一条是上一那条等式的**后果验证**——等式成立但 turn_id 拼错，同样是覆盖主题评分。
    """
    _stub(
        engine,
        monkeypatch,
        _evaluations({"overall_score": 40, "evidence": ["没有结论"], "user_answer": "还行吧", "follow_up": False}),
    )
    payload = engine.next_question()
    followup_turn = payload["metadata"]["turn_id"]
    assert followup_turn == "q-1-followup", payload["metadata"]

    engine.handle_answer("补充：我把召回率从 62% 提到 88%，方式是重排 + 去噪")

    answers = [msg for msg in engine.session.messages if msg.get("type") == "answer"]
    metadata = answers[-1]["metadata"]
    assert metadata["is_follow_up"] is True, metadata
    assert metadata["turn_id"] == followup_turn, metadata
    assert metadata["turn_id"] != "q-1", "追问的答案被记成主题那一轮的 turn_id ⇒ 主题评分会被覆盖"

    rows = engine.db.query(InterviewTurnEvaluation).filter_by(session_id=engine.session_id).all()
    rows = [row for row in rows if row.question_index == engine.current_index]
    turns = {(row.turn_id, bool(row.is_follow_up)) for row in rows}
    assert (followup_turn, True) in turns, f"评分行里没有独立的追问那一行：{turns}"


def _stub_from_messages(engine, monkeypatch, *, score: int = 40) -> None:
    """按**已保存的答案消息**重建评估。真实实现也是从消息/评分表重建的；这样在"答完追问"之后，
    状态会如实变成 `follow_up=True`——用一份静态的评估列表去测重连，测的就不是真实状态。"""

    def rebuild() -> list[dict]:
        rows = []
        for msg in engine.session.messages:
            if msg.get("type") != "answer":
                continue
            meta = msg.get("metadata") or {}
            rows.append(
                {
                    "question_index": len(rows),
                    "question": msg.get("content", ""),
                    "category": meta.get("category", "tech"),
                    "user_answer": msg.get("content", ""),
                    "completeness": 60,
                    "accuracy": 60,
                    "depth": 60,
                    "expression": 60,
                    "overall_score": score,
                    "feedback": "反馈",
                    "improvement": "改进",
                    "follow_up": bool(meta.get("is_follow_up")),
                    "evidence": ["没有结论"],
                    "turn_id": meta.get("turn_id"),
                }
            )
        return rows

    monkeypatch.setattr(engine, "_rebuild_evaluations", rebuild)


def test_reconnect_and_answer_chain_on_a_followup(engine, monkeypatch) -> None:
    """重连那条链上的三条语义，一次量完：

    ① 追问已发出、还没答时断线 ⇒ 重连**把同一条追问再推一次**（不能丢）；
    ② 追问答过之后 ⇒ 状态必须记成"这题已追过"，`next_question` 不许再追同一题；
    ③ 追问不占题号 ⇒ 推进时出的是下一道主题（round 2）。

    这条链原来会出两套追问（handle_answer 里的 I3 模板追问 + 决策器追问），2026-10-18 实测到
    同一轮被追两次；现在开关打开时由决策器独占，模板那套只在开关关掉时启用。
    """
    engine.current_index = -1  # 全新会话，第一题还没发
    _stub_from_messages(engine, monkeypatch, score=40)

    q1 = engine.next_question()
    assert "最有成就感的项目" in q1["content"], q1

    emitted = engine.handle_answer("我做过一个检索增强的项目")  # 评分 40 ⇒ 决策器追一句
    assert emitted["metadata"].get("is_follow_up") is True, emitted["metadata"]
    followup_turn = emitted["metadata"]["turn_id"]

    midway = InterviewEngine(engine.session_id)
    midway.db = engine.db
    midway.session = engine.db.get(InterviewSession, engine.session_id)
    re_pushed = midway.resume()
    assert re_pushed is not None, "追问还没答，重连把它丢了"
    assert re_pushed["metadata"].get("turn_id") == followup_turn, re_pushed["metadata"]

    midway.handle_answer("补充：召回率从 62% 提到 88%，做法是重排 + 去噪")

    after = InterviewEngine(engine.session_id)
    after.db = engine.db
    after.session = engine.db.get(InterviewSession, engine.session_id)
    resumed = after.resume()
    trail = [
        (m.get("type"), (m.get("metadata") or {}).get("round"), (m.get("metadata") or {}).get("turn_id"))
        for m in after.session.messages
    ]
    assert resumed is not None, f"追问答完之后重连应该接着推下一道主题；消息轨迹={trail}"
    assert resumed["metadata"].get("is_follow_up") is not True, f"重连后又追同一题：{resumed['metadata']}"
    assert "RAG 的工作原理" in resumed["content"], resumed["content"]


def test_llm_composed_followup_is_used(engine, monkeypatch) -> None:
    """LLM 愿意组织追问时，用它的题面，并如实标 `source=llm`。

    这一条是"追问升级"的落点：启发式那句是模板，LLM 那句才是针对回答内容的。
    """
    engine.current_index = -1
    _stub_from_messages(engine, monkeypatch, score=40)
    monkeypatch.setattr(
        engine,
        "_decision_chat",
        lambda: (lambda prompt: {"action": "deepen", "question": "你提到的召回率提升，具体是怎么测的？"}),
    )

    engine.next_question()
    emitted = engine.handle_answer("我做过一个检索增强的项目")

    assert emitted["metadata"]["decision"]["source"] == "llm", emitted["metadata"]
    assert "召回率" in emitted["content"], emitted["content"]


def test_llm_failure_degrades_and_still_asks(engine, monkeypatch) -> None:
    """LLM 炸了 ⇒ 降级成启发式那句，题面不许空，且 `degraded=true` 供对内可查。

    产品口径：降级对候选人静默（屏幕上不出现"AI 不可用"），这个标志只给内用。
    """

    def boom(prompt: str) -> dict:
        raise RuntimeError("provider down")

    engine.current_index = -1
    _stub_from_messages(engine, monkeypatch, score=40)
    monkeypatch.setattr(engine, "_decision_chat", lambda: boom)

    engine.next_question()
    emitted = engine.handle_answer("我做过一个检索增强的项目")

    assert emitted["metadata"]["decision"]["degraded"] is True, emitted["metadata"]
    assert emitted["metadata"]["decision"]["source"] == "heuristic", emitted["metadata"]
    assert emitted["content"].strip(), "降级之后连题面都没了"


def test_advance_never_calls_the_llm(engine, monkeypatch) -> None:
    """推进那一档零 LLM 调用——混合动态那条"至少 75% 题目零额外等待"的前提。"""
    calls: list[str] = []

    def spy(prompt: str) -> dict:
        calls.append(prompt)
        return {"action": "deepen", "question": "不该用到这句"}

    engine.current_index = -1
    _stub_from_messages(engine, monkeypatch, score=90)
    monkeypatch.setattr(engine, "_decision_chat", lambda: spy)

    engine.next_question()
    emitted = engine.handle_answer("答得很完整，有数据有取舍")

    assert calls == [], f"高分推进这一档发了 {len(calls)} 次 LLM 调用"
    assert emitted["metadata"].get("is_follow_up") is not True, emitted["metadata"]


def test_llm_composition_has_a_hard_deadline(
    engine,
    monkeypatch,
) -> None:
    """LLM 迟迟不回 ⇒ 到点就走降级，候选人不能为一句追问等两分钟。

    这条把预算调到 0.1 秒、让假 chat 睡 0.5 秒：不设硬截止的话这一发会把测试拖到 0.5 秒以上，
    而设了就该在 0.4 秒以内带着"启发式那句"回来。
    """
    import time

    monkeypatch.setattr(settings, "INTERVIEW_DECISION_TIMEOUT_SECONDS", 0.1)

    def slow(prompt: str) -> dict:
        time.sleep(0.5)
        return {"action": "deepen", "question": "慢到的题面"}

    engine.current_index = -1
    _stub_from_messages(engine, monkeypatch, score=40)
    monkeypatch.setattr(engine, "_decision_chat", lambda: engine._bounded_chat(slow))

    engine.next_question()
    started = time.monotonic()
    emitted = engine.handle_answer("我做过一个检索增强的项目")
    elapsed = time.monotonic() - started

    assert elapsed < 0.4, f"没被硬截止拦住，等了 {elapsed:.2f}s"
    assert emitted["metadata"]["decision"]["degraded"] is True, emitted["metadata"]
    assert emitted["content"].strip(), emitted["content"]


# ---------------------------------------------------------------------------
# P3.2 的前置：JD 必考技能池要活到每一轮
# ---------------------------------------------------------------------------
# 文档要的"弱点命中率"没有数据源：建会话时没人写弱点，`build_memory_snapshot()` 每轮又**整份覆盖**
# 快照。所以决策器读的 `memory_snapshot["weaknesses"]` 今天永远为空——追问的弱点分支是死代码。
# 口径按他 2026-10-19 点的：用 **JD 必考技能**当弱点池（不是"候选人不会的"，是"岗位必考、还没考到"）。


def test_memory_snapshot_keeps_the_skill_pool_between_turns(engine) -> None:
    """每轮的快照重建不许把建会话时落的必考技能池抹掉。"""
    engine.session.memory_snapshot = {
        "question_generation": {"status": "pending"},
        "jd_required_skills": ["分布式事务", "向量检索"],
    }
    engine.db.commit()

    snapshot = build_memory_snapshot(engine.db, engine.session_id)

    assert snapshot["jd_required_skills"] == ["分布式事务", "向量检索"], snapshot
    assert snapshot["completed_turns"] == 0, snapshot


def test_decision_state_carries_the_jd_skill_pool(engine) -> None:
    """决策器拿到的弱点池 = 快照里的必考技能。"""
    engine.session.memory_snapshot = {"jd_required_skills": ["向量检索"]}
    engine.db.commit()

    state = engine._decision_state(engine.session.questions, [])

    assert state["weaknesses"] == ["向量检索"], state


def test_followup_names_a_required_skill_when_evidence_is_empty(engine, monkeypatch) -> None:
    """答得差、又没抓到具体证据 ⇒ 追问要落在某个**必考技能**上，而不是空泛的"再说具体点"。"""
    engine.session.memory_snapshot = {"jd_required_skills": ["分布式事务"]}
    engine.db.commit()
    _stub(
        engine,
        monkeypatch,
        _evaluations({"overall_score": 40, "evidence": [], "user_answer": "还行吧", "follow_up": False}),
    )

    followup = engine.next_question()

    assert "分布式事务" in followup["content"], followup["content"]
