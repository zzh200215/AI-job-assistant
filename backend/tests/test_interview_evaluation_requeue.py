"""B1：逐题评分的"没人来捡"缺陷，以及那条乐观锁认领到底挡住了什么。

`submit_turn_evaluation` 把活投给**本进程**的线程池，而全树没有任何地方重扫留下的行——启动钩子只
收口 `AgentTask`，`GET /sessions/{id}/evaluations` 只读。于是进程一死（发布、崩溃、扩副本都算）：
行永远停在 pending/running → `pending_evaluation_count` 恒 >0 → `evaluation_status` 卡 processing
→ **面试终报永远补齐不了**。开发库现量 `interview_turn_evaluation` 是 0 行（这库里没跑完过一场带
异步评分的面试），所以这是一处形状缺陷，不是数据事故——正因为如此，它必须在还有数据之前修好。

认领（`_claim_status`）是这条修复里唯一需要证明的部分：它靠"必然改变 status 的条件 UPDATE"发凭证，
所以同一时刻两个扫描只有一个拿到活。注意这条证明是在 SQL 层面做的（内存 SQLite），MySQL 的行锁与
rowcount 语义只能靠注释里的理由保证，测试量不到。
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from app.models.interview_evaluation import InterviewTurnEvaluation
from app.models.interview_session import InterviewSession
from app.services import interview_evaluation_service as svc
from app.utils.time_helper import utc_now_naive

STALE = 20  # 比默认阈值（15 分钟）老
FRESH = 5  # 比阈值年轻：可能正被另一个副本跑着（单题最坏 ≈ 3.1 分钟，见阈值那条注释）


def _row(db, session_id: int, *, status: str, minutes_ago: int = STALE, turn_id: str = "q-1"):
    row = InterviewTurnEvaluation(
        session_id=session_id,
        turn_id=turn_id,
        question_index=0,
        question="项目题",
        category="project",
        user_answer="答过了，就等评分",
        status=status,
        created_at=utc_now_naive() - timedelta(minutes=minutes_ago),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def recorder(monkeypatch):
    """把"投递"换成记账：扫描的产物是"谁被投了"，不是真去打模型。"""
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        svc, "submit_turn_evaluation", lambda session_id, evaluation_id: calls.append((session_id, evaluation_id))
    )
    return calls


def test_each_kind_of_leftover_is_claimed_out_of_the_status_it_was_seen_in(
    db_session, make_interview_session, recorder
):
    """两种滞留的成因不同，认领的方向也不同——但都必须"挪开"，不然 rowcount 不能当凭证。"""
    session_id = make_interview_session(status="completed")
    never_started = _row(db_session, session_id, status="pending", turn_id="q-1")
    owner_died = _row(db_session, session_id, status="running", minutes_ago=STALE, turn_id="q-2")

    assert svc.requeue_stale_turn_evaluations(db=db_session) == 2
    assert sorted(recorder) == sorted([(session_id, never_started.id), (session_id, owner_died.id)])

    db_session.refresh(never_started)
    db_session.refresh(owner_died)
    # pending → running（它从没起跑过，现在有人起跑）；running → pending（主人死了，重新排队）。
    assert never_started.status == "running"
    assert owner_died.status == "pending"


def test_a_row_younger_than_the_threshold_is_left_for_whoever_is_running_it(
    db_session, make_interview_session, recorder
):
    """阈值不是官僚主义：单题最坏 = 60s × 3 次尝试 + 线性退避 4.5s = 184.5s ≈ 3.1 分钟。

    比这更年轻的 running 行完全可能正被**另一个副本**跑着，抢过来就是同一道题付两遍模型钱。
    """
    session_id = make_interview_session(status="completed")
    row = _row(db_session, session_id, status="running", minutes_ago=FRESH)

    assert svc.requeue_stale_turn_evaluations(db=db_session) == 0
    assert recorder == []
    db_session.refresh(row)
    assert row.status == "running"

    # 反证：同一行把阈值压到 0（= 不限龄）就必须被认走，否则上一条的绿是空转出来的。
    assert svc.requeue_stale_turn_evaluations(db=db_session, older_than_minutes=1) == 1


def test_completed_rows_are_never_touched(db_session, make_interview_session, recorder):
    """已经出分的行不在射程里——重投它们会把候选人的分数覆盖一遍。"""
    session_id = make_interview_session(status="completed")
    row = _row(db_session, session_id, status="completed")

    assert svc.requeue_stale_turn_evaluations(db=db_session) == 0
    db_session.refresh(row)
    assert row.status == "completed"


def test_a_claim_is_handed_out_once_per_observed_status(db_session, make_interview_session):
    """这就是那条乐观锁本身：同一个"看见的 status"只能中一次。"""
    session_id = make_interview_session(status="completed")
    row = _row(db_session, session_id, status="pending")

    assert svc._claim_status(db_session, row.id, "pending") == 1
    # 第二个扫描进程读的也是 pending，但它落 UPDATE 时那一行已经不是 pending 了。
    assert svc._claim_status(db_session, row.id, "pending") == 0
    db_session.refresh(row)
    assert row.status == "running"
    # 拿到凭证的人死了之后，下一轮扫描用**新的**观测值再认领一次——恢复就靠这个。
    assert svc._claim_status(db_session, row.id, "running") == 1
    assert svc._claim_status(db_session, row.id, "running") == 0


def test_a_later_sweep_can_take_back_a_row_whose_owner_died(db_session, make_interview_session, recorder):
    """认领不是一次性的：它只保证"同时"唯一，不保证"从此不再被重投"。

    这条区分很重要——写测试时我一度以为第二次扫描必须返回 0，那等于把恢复功能删掉：一个反复崩在
    同一题上的进程确实会被反复重投，上限是每轮 10 分钟、阈值 15 分钟，而正常单题最坏 3.1 分钟。
    """
    session_id = make_interview_session(status="completed")
    row = _row(db_session, session_id, status="pending")

    assert svc.requeue_stale_turn_evaluations(db=db_session) == 1
    db_session.refresh(row)
    assert row.status == "running"  # 被认领走，但那个进程没跑完

    assert svc.requeue_stale_turn_evaluations(db=db_session) == 1
    assert len(recorder) == 2


def test_the_claim_keeps_the_row_inside_the_pending_count(db_session, make_interview_session, recorder):
    """认领的落点必须还在 `pending_evaluation_count` 的口径里，否则报告会提前定稿。"""
    session_id = make_interview_session(status="completed")
    row = _row(db_session, session_id, status="running")

    before = svc.pending_evaluation_count(db_session, session_id)
    svc.requeue_stale_turn_evaluations(db=db_session)
    db_session.refresh(row)

    assert row.status == "pending"
    assert svc.pending_evaluation_count(db_session, session_id) == before == 1


def test_a_stalled_report_unblocks_once_the_leftover_is_picked_up(db_session, make_interview_session, monkeypatch):
    """整条链的落点：滞留行被捡回之后，`evaluation_status` 才出得了 processing。

    这里把"投递"直接接成同步执行（真线程池那一半由 `test_background_worker_persists_score_evidence_and_memory`
    钉），这样断言的是**恢复之后**的状态，而不是运气。
    """
    session_id = make_interview_session(status="completed", messages=[])
    row = _row(db_session, session_id, status="pending")
    session = db_session.get(InterviewSession, session_id)
    session.evaluation_status = "processing"
    db_session.commit()

    monkeypatch.setattr(svc, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)

    class FakeAgent:
        def run_impl(self, _context):
            return {
                "completeness": 80,
                "accuracy": 78,
                "depth": 74,
                "expression": 76,
                "overall_score": 77,
                "feedback": "回答有结果。",
                "improvement": "补一个量化数。",
            }

    monkeypatch.setattr(svc, "AnswerEvaluationAgent", FakeAgent)
    monkeypatch.setattr(svc, "submit_turn_evaluation", lambda sid, eid: svc.process_turn_evaluation(sid, eid))

    assert svc.requeue_stale_turn_evaluations(db=db_session) == 1

    db_session.refresh(row)
    db_session.refresh(session)
    assert row.status == "completed"
    assert session.evaluation_status != "processing", "评分补完了，状态却还卡在 processing"
    assert svc.pending_evaluation_count(db_session, session_id) == 0


def test_a_row_the_claim_refused_never_gets_submitted(db_session, make_interview_session, recorder, monkeypatch):
    """`rowcount == 1` 那个判断是本条唯一"不重复付模型钱"的闸门，必须单独钉。

    这里不去构造真并发（内存库上构造出来的并发是假的），而是直接把认领的结果换成"输了"：
    扫描读到了 stale 行、但凭证没拿到——这一行就绝不能被投递。
    """
    session_id = make_interview_session(status="completed")
    _row(db_session, session_id, status="pending")
    seen: list[tuple[int, str]] = []

    def _lost(db, row_id: int, expected: str) -> int:
        seen.append((row_id, expected))
        return 0

    monkeypatch.setattr(svc, "_claim_status", _lost)

    assert svc.requeue_stale_turn_evaluations(db=db_session) == 0
    assert recorder == [], "认领输了还投递 = 同一道题付两遍 qwen 调用"
    assert len(seen) == 1, "扫描压根没试着认领，那条 ==1 的判断根本没被执行到"
    # 观测值必须是这一行**被读到那一刻**的状态，否则 WHERE 条件对不上、凭证毫无意义。
    assert seen[0][1] == "pending"


def test_the_requeue_hands_work_to_the_real_executor_and_does_not_wait_for_it(
    db_session, make_interview_session, monkeypatch
):
    """扫描必须"投完就走"，而且投的是**真**线程池——这两件事以前没被任何东西钉住。

    写库那一半由 `test_background_worker_persists_score_evidence_and_memory` 管；这条管的是另外两种
    会悄悄坏掉的形状：① 启动钩子在调用线程里就地跑完一题评分（那等于让一次 LLM 调用堵住应用启动）；
    ② `submit_turn_evaluation` 被换成直接调 `process_turn_evaluation`，投递变成空话。
    """
    session_id = make_interview_session(status="completed")
    row = _row(db_session, session_id, status="pending")

    handed: list[tuple[int, int]] = []
    release = threading.Event()
    started = threading.Event()

    def _stub_process(sid: int, eid: int) -> None:
        handed.append((sid, eid))
        started.set()
        release.wait(5.0)

    monkeypatch.setattr(svc, "process_turn_evaluation", _stub_process)

    t0 = time.perf_counter()
    assert svc.requeue_stale_turn_evaluations(db=db_session) == 1
    elapsed = time.perf_counter() - t0

    assert started.wait(5.0), "线程池压根没执行这一题：投递是空的"
    assert handed == [(session_id, row.id)], "跑完的题号不是刚被认领的那一行"
    assert elapsed < 1.0, f"扫描在调用线程里等完了评分（{elapsed:.2f}s）：启动钩子会被一题 LLM 调用拖住"
    release.set()


def test_the_recovery_is_wired_at_both_call_sites():
    """两个调用点都得在场：只留一个的话，"重启之后就有人捡"这句话会悄悄失效。

    扫源码而不是跑 lifespan——起一次 app 会把内存库换成另一块（见 tests/conftest.py:12），
    测出来的"绿"和用户实际看到的不是同一件事。
    """
    root = Path(__file__).resolve().parents[1]
    main = (root / "app" / "main.py").read_text(encoding="utf-8")
    scheduler = (root / "app" / "core" / "scheduler.py").read_text(encoding="utf-8")

    assert "requeue_stale_turn_evaluations()" in main, "启动那一次扫描被删了：滞留行又没人捡了"
    # 启动那一次必须包在 try 里：恢复扫描是锦上添花，它坏了不能把应用启动变成硬失败。
    assert "逐题评分重投扫描失败" in main, "启动扫描没被包起来：一次库抖动就会把应用关在门外"
    assert "interview_evaluation_requeue" in scheduler, "定时扫描被删了：不重启就永远等不到恢复"
    assert "INTERVIEW_EVALUATION_REQUEUE_MINUTES" in (root / "app" / "core" / "config.py").read_text(encoding="utf-8")

    # 反证：判据不是空串——把两处调用逐字抹掉之后这条必须红（打在副本上，不动工作树）。
    assert "requeue_stale_turn_evaluations()" not in main.replace("requeue_stale_turn_evaluations()", "")
