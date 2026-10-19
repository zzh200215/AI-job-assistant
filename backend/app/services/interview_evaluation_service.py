"""Background evaluation, evidence persistence, and memory snapshots for interview turns."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Lock
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.agents.answer_evaluation_agent import AnswerEvaluationAgent
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.interview_evaluation import InterviewTurnEvaluation
from app.models.interview_session import InterviewSession
from app.orchestration.context import AgentContext
from app.utils.time_helper import utc_now, utc_now_naive

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_executor_lock = Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, settings.INTERVIEW_EVALUATION_MAX_WORKERS),
                thread_name_prefix="interview-evaluation",
            )
        return _executor


def shutdown_interview_evaluation_executor() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def create_pending_turn_evaluation(
    db: Session,
    *,
    session_id: int,
    turn_id: str,
    question_index: int,
    question: str,
    category: str,
    user_answer: str,
    is_follow_up: bool,
) -> InterviewTurnEvaluation:
    # 重复作答（如断线重连后重提同一题、双击提交）会撞 (session_id, turn_id) 唯一约束，
    # 抛 IntegrityError 直接卡死会话。复用同一行并重置为 pending，保证会话可继续。
    existing = (
        db.query(InterviewTurnEvaluation)
        .filter(
            InterviewTurnEvaluation.session_id == session_id,
            InterviewTurnEvaluation.turn_id == turn_id,
        )
        .first()
    )
    if existing is not None:
        existing.question_index = question_index
        existing.question = question
        existing.category = category
        existing.user_answer = user_answer
        existing.is_follow_up = 1 if is_follow_up else 0
        existing.status = "pending"
        existing.overall_score = 0
        existing.feedback = ""
        existing.improvement = ""
        existing.evidence = None
        existing.error_msg = ""
        existing.completed_at = None
        # 重新作答的题要立刻可被认领，不能背着上一轮的租约（D178）。
        existing.claimed_at = None
        db.flush()
        return existing

    record = InterviewTurnEvaluation(
        session_id=session_id,
        turn_id=turn_id,
        question_index=question_index,
        question=question,
        category=category,
        user_answer=user_answer,
        is_follow_up=1 if is_follow_up else 0,
        status="pending",
    )
    db.add(record)
    db.flush()
    return record


def submit_turn_evaluation(session_id: int, evaluation_id: int) -> None:
    """Schedule a best-effort evaluation on **this process's** executor.

    The durable row is the source of truth, but nothing here survives the process: a shutdown
    cancels the queued future (`cancel_futures=True`), and a crash mid-call leaves the row in
    `running`. Recovery is `requeue_stale_turn_evaluations`, which startup and the scheduler run.
    """
    _get_executor().submit(process_turn_evaluation, session_id, evaluation_id)


# 这两种状态都算"还没出分"：`pending` = 投了但没起跑（关在闸里的线程池被 shutdown 取消），
# `running` = 起了跑但主人死了。`pending_evaluation_count` 认的就是这两个，口径不能错。
STALE_STATUSES = ("pending", "running")


def _claim_status(db: Session, row_id: int, expected: str, *, lease_minutes: int | None = None) -> int:
    """把一行挪出**这次扫描看见它时**的那个状态，用 rowcount 当"我抢到了"的凭证。

    MySQL 的 UPDATE rowcount 数的是**被改动**的行，不是被匹配的行（驱动默认不带
    CLIENT_FOUND_ROWS）。所以"同值写回"是一种假认领：WHERE 命中了、值没变、rowcount=0，
    谁都以为自己没抢到。认领必须改变 status：`pending → running`（从没起跑）、
    `running → pending`（起跑过、进程已不在）。两种落点都还在 `STALE_STATUSES` 里，
    所以重投期间报告不会提前定稿。

    **光改 status 只做到 per-transition 单飞**（D177 真 8 进程 + 真 MySQL 现量：八个 rc 是
    `1 0 0 1 0 0 0 0`，两个赢家各领了一条 transition，因为 B 扫到时看到的是 A 刚写上的 `running`）。
    D178 补的是第二半把凭证：`claimed_at` 租约。它让"这一行在租约内已经被任何人领过"成为
    WHERE 的一部分，于是同一行只有一个赢家——不管对方按哪个 observed status 来抢。
    租约下界 = 单题最坏 364.5s（`INTERVIEW_EVALUATION_CLAIM_LEASE_MINUTES` 那条注释里的推导，
    它跟着 `LLM_TIMEOUT` 走：120s × 3 次尝试 + 退避 4.5s），
    取 `lease_minutes=0` 等于关掉租约，测试用它复现旧的 per-transition 形状。
    """
    target = "running" if expected == "pending" else "pending"
    minutes = settings.INTERVIEW_EVALUATION_CLAIM_LEASE_MINUTES if lease_minutes is None else lease_minutes
    stamp = utc_now_naive()
    cutoff = stamp - timedelta(minutes=max(0, int(minutes or 0)))
    return (
        db.query(InterviewTurnEvaluation)
        .filter(
            InterviewTurnEvaluation.id == row_id,
            InterviewTurnEvaluation.status == expected,
            or_(InterviewTurnEvaluation.claimed_at.is_(None), InterviewTurnEvaluation.claimed_at < cutoff),
        )
        .update(
            {InterviewTurnEvaluation.status: target, InterviewTurnEvaluation.claimed_at: stamp},
            synchronize_session=False,
        )
    )


def requeue_stale_turn_evaluations(
    *, older_than_minutes: int | None = None, limit: int = 50, db: Session | None = None
) -> int:
    """重新投递"提交它的进程已经不在了"的那些逐题评分，返回重投行数。

    这条之前 `submit_turn_evaluation` 的文档串承诺的是假东西：行确实没丢（答案在库里），
    但**没有任何人会来捡它**——启动钩子只收口 AgentTask，`GET /sessions/{id}/evaluations`
    只读不投。于是进程一死（发布、崩溃、扩副本都算），那一行永远停在 pending/running，
    `pending_evaluation_count` 恒大于 0，`evaluation_status` 卡在 processing，
    面试终报永远不会补齐。多副本时同理：谁持有连接谁投递，别的副本看不见那份队列。
    """
    minutes = older_than_minutes if older_than_minutes is not None else settings.INTERVIEW_EVALUATION_REQUEUE_MINUTES
    cutoff = utc_now_naive() - timedelta(minutes=max(1, int(minutes or 15)))
    session = db or SessionLocal()
    owns_session = db is None
    claimed: list[tuple[int, int]] = []
    try:
        stale = (
            session.query(InterviewTurnEvaluation)
            .filter(
                InterviewTurnEvaluation.status.in_(STALE_STATUSES),
                InterviewTurnEvaluation.created_at < cutoff,
            )
            .order_by(InterviewTurnEvaluation.id.asc())
            .limit(max(1, int(limit)))
            .all()
        )
        for row in stale:
            if _claim_status(session, row.id, row.status) == 1:
                claimed.append((row.session_id, row.id))
            # rowcount 0 = 这一行在租约内已经被**某个**进程领走了（不管它按哪个 observed
            # status 来抢），我不重复投递。D178 之前这里只挡同一 transition，于是会双付。
        session.commit()
    finally:
        if owns_session:
            session.close()

    # 认领先落库、再投递：顺序反过来会让第二个进程在"已经起跑"和"还是旧 status"之间读到窗口。
    for session_id, evaluation_id in claimed:
        submit_turn_evaluation(session_id, evaluation_id)
    if claimed:
        logger.info("重投滞留的逐题评分 %d 行（阈值 %d 分钟）", len(claimed), minutes)
    return len(claimed)


def complete_turn_evaluation(
    record: InterviewTurnEvaluation,
    result: dict[str, Any],
    *,
    source: str = "synchronous_evaluation",
) -> None:
    """Persist a completed score for synchronous callers that retain legacy behavior."""
    _complete_record(record, result, source=source)


def process_turn_evaluation(session_id: int, evaluation_id: int) -> None:
    db = SessionLocal()
    should_refresh_report = False
    try:
        record = db.get(InterviewTurnEvaluation, evaluation_id)
        session = db.get(InterviewSession, session_id)
        if not record or not session or record.session_id != session_id or record.status == "completed":
            return

        record.status = "running"
        db.commit()

        try:
            context = AgentContext()
            context.set_extra("question", record.question)
            context.set_extra("ref_answer", _reference_answer(session, record.question_index))
            context.set_extra("user_answer", record.user_answer)
            result = AnswerEvaluationAgent().run_impl(context)
            _complete_record(record, result, source="answer_evaluation_agent")
        except Exception as exc:
            logger.exception(
                "Interview turn evaluation failed session_id=%s evaluation_id=%s", session_id, evaluation_id
            )
            _complete_record(
                record, _fallback_evaluation(), source="deterministic_fallback", error_type=type(exc).__name__
            )

        # D225：这里**不再**往 `session.messages` 里追加点评（那正是 10 个 worker 互相覆盖
        # 丢消息的地方）。点评只留在 `interview_turn_evaluation` 的行上，出口由
        # `build_conversation` 现派生。下面这次 flush/commit 因此只写行与状态。
        db.flush()  # D170：生产会话 autoflush=False，下面"读自己刚写的"两处不 flush 就看不见
        with session_write_lock(session_id):
            # 锁内重读再判定：pending 与状态列都是"别人可能刚改过"的东西，用 worker 自己
            # 那份内存里的旧值判定，就会把已经齐了的会话又写回 processing（D224 现场）。
            db.refresh(session)
            session.memory_snapshot = build_memory_snapshot(db, session_id)
            session.evaluation_status = _evaluation_status(db, session_id, session.status)
            db.commit()
            should_refresh_report = session.status == "completed" and session.evaluation_status == "completed"
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to persist interview evaluation session_id=%s evaluation_id=%s", session_id, evaluation_id
        )
    finally:
        db.close()

    if should_refresh_report:
        refresh_completed_report(session_id)


def _complete_record(
    record: InterviewTurnEvaluation,
    result: dict[str, Any],
    *,
    source: str,
    error_type: str = "",
) -> None:
    for field in ("completeness", "accuracy", "depth", "expression", "overall_score"):
        setattr(record, field, _score(result.get(field)))
    record.feedback = str(result.get("feedback") or "评分已完成，请结合维度分数复盘。")
    record.improvement = str(result.get("improvement") or "补充事实、结果和具体取舍，让回答更有说服力。")
    record.status = "completed"
    record.error_msg = error_type
    record.completed_at = utc_now()
    record.evidence = {
        "source": source,
        "question_excerpt": record.question[:180],
        "answer_excerpt": record.user_answer[:240],
        "dimensions": {
            "completeness": record.completeness,
            "accuracy": record.accuracy,
            "depth": record.depth,
            "expression": record.expression,
        },
    }


def _fallback_evaluation() -> dict[str, Any]:
    return {
        "completeness": 60,
        "accuracy": 60,
        "depth": 50,
        "expression": 60,
        "overall_score": 58,
        "feedback": "自动评分暂不可用，已保留本题回答和基础复盘口径。",
        "improvement": "请覆盖问题核心点，并补充具体案例、数据或技术取舍。",
    }


def _reference_answer(session: InterviewSession, question_index: int) -> str:
    questions = session.questions or []
    if 0 <= question_index < len(questions):
        question = questions[question_index] or {}
        return str(question.get("ref_answer") or question.get("expected_answer") or "")
    return ""


def evaluation_frame(record: InterviewTurnEvaluation) -> dict[str, Any]:
    """一条逐题点评在客户端里的样子。

    D225：这形状**原来**是被 `_append_evaluation_message` 塞进 `InterviewSession.messages`（一个
    JSON 列）的，10 个后台 worker 各自"读整列-改-写整列"，后提交的把先提交的抹掉——真跑一场面试
    （D224）10 条点评只剩 6 条就是这么丢的。现在它是快照出口按 `interview_turn_evaluation` 的行
    **现派生**出来的，字段与从前逐字相同，所以前端不需要跟着改。
    """
    return {
        "role": "system",
        "type": "evaluation",
        "content": record.feedback,
        "metadata": {
            "turn_id": record.turn_id,
            "round": record.question_index + 1,
            "score": record.overall_score,
            "completeness": record.completeness,
            "accuracy": record.accuracy,
            "depth": record.depth,
            "expression": record.expression,
            "improvement": record.improvement,
            "evidence": record.evidence or {},
            "async": True,
        },
        "timestamp": (record.completed_at or utc_now()).isoformat(),
    }


def build_conversation(db: Session, session: InterviewSession) -> list[dict[str, Any]]:
    """给客户端的消息列表：JSON 列里原有的条目 + 表里已完成的点评，按"那一题的答案之后"插回去。

    兼容是这里的重点：`interview_turn_evaluation` 是 D163/D170 之后才有的表，**它建成之前的会话**
    逐题点评只活在 `messages` 这个 JSON 列里。所以既不能"只读表"（老会话的点评会凭空消失），
    也不能"只读 JSON"（新会话的点评正是要从 JSON 里搬走的那件事）。规则是：
      * 表里有行 → 以表为准，并丢掉 JSON 里同 `turn_id` 的旧副本（否则同一题显示两遍）；
      * 表里没行、JSON 里有 → 原样留着（老会话照旧能看）；
      * 超时那类 `system` 消息不在搬动范围内（`_rebuild_evaluations` 仍靠它推断，见 L3）。
    """
    messages = list(session.messages or [])
    rows = [row for row in list_turn_evaluations(db, session.id) if row.status == "completed"]
    if not rows:
        return messages

    covered = {str(row.turn_id) for row in rows}
    kept: list[dict[str, Any]] = []
    for item in messages:
        meta = item.get("metadata") or {}
        if item.get("type") == "evaluation" and str(meta.get("turn_id") or "") in covered:
            continue
        kept.append(item)

    # 插回原位：紧跟在该题最后一条 answer 之后；找不到就接到尾部（表里有行但答案不在 JSON 里，
    # 例如中途换过进程），顺序仍以 round 为准。
    by_round: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_round.setdefault(row.question_index + 1, []).append(evaluation_frame(row))

    out: list[dict[str, Any]] = []
    placed: set[int] = set()
    for item in kept:
        out.append(item)
        meta = item.get("metadata") or {}
        if item.get("type") == "answer":
            round_num = int(meta.get("round") or 0)
            if round_num in by_round:
                out.extend(by_round[round_num])
                placed.add(round_num)
    leftovers = [frame for round_num, frames in sorted(by_round.items()) if round_num not in placed for frame in frames]
    out.extend(leftovers)
    return out


_SESSION_LOCK_CAP = 512
_session_locks: dict[int, Lock] = {}
_session_locks_guard = Lock()


def session_write_lock(session_id: int) -> Lock:
    """同一个会话的"改状态 / 写终报"必须串行（D225）。

    锁住在进程内：这些 worker 本来就是同进程的线程（逐题评分池 + WS 步骤），而 D220 刚量过
    "API 进程 = 全部 HTTP 流量"。**跨进程不是一把锁**——真要防住那个，得给会话行加
    `SELECT … FOR UPDATE`；本仓今天的形状是单进程，所以先不背那把复杂度，注释与账上都写明。
    """
    with _session_locks_guard:
        lock = _session_locks.get(session_id)
        if lock is None:
            if len(_session_locks) >= _SESSION_LOCK_CAP:
                # 只挡无界增长，不做引用计数：会话数以千计时会重建条目，代价是一次竞态窗口，
                # 而那窗口里的两个写者本来就不在锁的设计目标内（同一次终报）。
                _session_locks.clear()
            lock = _session_locks[session_id] = Lock()
        return lock


def list_turn_evaluations(db: Session, session_id: int) -> list[InterviewTurnEvaluation]:
    return (
        db.query(InterviewTurnEvaluation)
        .filter(InterviewTurnEvaluation.session_id == session_id)
        .order_by(InterviewTurnEvaluation.question_index, InterviewTurnEvaluation.id)
        .all()
    )


def evaluation_payloads(db: Session, session_id: int, *, completed_only: bool = False) -> list[dict[str, Any]]:
    rows = list_turn_evaluations(db, session_id)
    if completed_only:
        rows = [row for row in rows if row.status == "completed"]
    return [row.to_dict() for row in rows]


def completed_evaluation_payloads(db: Session, session_id: int) -> list[dict[str, Any]]:
    return [row.to_dict() for row in list_turn_evaluations(db, session_id) if row.status == "completed"]


def pending_evaluation_count(db: Session, session_id: int) -> int:
    return (
        db.query(InterviewTurnEvaluation)
        .filter(
            InterviewTurnEvaluation.session_id == session_id,
            InterviewTurnEvaluation.status.in_(["pending", "running"]),
        )
        .count()
    )


def build_memory_snapshot(db: Session, session_id: int) -> dict[str, Any]:
    completed = [row for row in list_turn_evaluations(db, session_id) if row.status == "completed"]
    pending_count = pending_evaluation_count(db, session_id)
    categories = sorted({row.category or "general" for row in completed})
    strengths = [
        {"turn_id": row.turn_id, "question": row.question[:120], "score": row.overall_score}
        for row in completed
        if (row.overall_score or 0) >= 80
    ][:3]
    risks = [
        {"turn_id": row.turn_id, "question": row.question[:120], "score": row.overall_score}
        for row in completed
        if (row.overall_score or 0) < 70
    ][:3]
    summary = (
        f"已完成 {len(completed)} 题评分，覆盖 {', '.join(categories) if categories else '待评分'}。"
        f"高分证据 {len(strengths)} 条，待补强证据 {len(risks)} 条，后台待处理 {pending_count} 题。"
    )
    snapshot = {
        "version": 1,
        "generated_at": utc_now().isoformat(),
        "completed_turns": len(completed),
        "pending_turns": pending_count,
        "covered_categories": categories,
        "strengths": strengths,
        "risks": risks,
        "summary": summary,
    }
    # 建会话那一刻写进快照的东西（比如 JD 必考技能池）不能被每轮的快照整份覆盖掉：
    # 决策器的"弱点池"就寄存在那里，覆盖一次就永远空了——而空掉的那一侧不报任何错。
    session = db.get(InterviewSession, session_id)
    previous = (session.memory_snapshot or {}) if session else {}
    for key, value in previous.items():
        snapshot.setdefault(key, value)
    return snapshot


def _evaluation_status(db: Session, session_id: int, session_status: str) -> str:
    pending = pending_evaluation_count(db, session_id)
    if pending:
        return "processing"
    if session_status == "completed":
        return "completed"
    return "idle"


def refresh_completed_report(session_id: int, *, db: Session | None = None) -> None:
    """Regenerate the final report only after every deferred score has been persisted.

    与 `_finish` 共用同一把会话写锁：终报的"谁最后写"必须和"谁看见 pending 为 0"是同一个判定，
    否则一条 40 秒的报告调用可以盖掉另一条已经算清楚的写入（D224 现场就是这个形状）。

    `db` 给的是"调用方已经有一条会话了，别再开一条"：生产上少一次无谓的连接，测试里这一点更要紧
    ——本仓有两块内存库，引擎自己 `SessionLocal()` 会连到另一块上去，然后报"会话不存在"。
    """
    from app.services.interview_engine import InterviewEngine

    engine = InterviewEngine(session_id)
    if db is not None:
        engine.db = db
    owns_db = db is None
    try:
        with session_write_lock(session_id):
            engine._load_session()
            if not engine.session or engine.session.status != "completed":
                return
            engine.question_count = len(engine.session.questions or [])
            engine.evaluations = engine._rebuild_evaluations()
            engine.start_time = engine._infer_start_time()
            if pending_evaluation_count(engine.db, session_id):
                # 拿到锁的一瞬间又有新的 pending（例如重投的那一发刚被领走）：这一趟不写终报，
                # 让真正最后一个完成评分的 worker 再叫一次。
                return
            report = engine._generate_report()
            report["evaluation_status"] = "completed"
            report["interview_memory"] = engine.session.memory_snapshot or {}
            engine.session.evaluation = report
            engine.session.evaluation_status = "completed"
            engine.db.commit()
    except Exception:
        logger.exception("Failed to refresh completed interview report session_id=%s", session_id)
    finally:
        if owns_db:
            engine.cleanup()


def _score(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0
