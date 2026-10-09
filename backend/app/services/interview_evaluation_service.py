"""Background evaluation, evidence persistence, and memory snapshots for interview turns."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Lock
from typing import Any

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


def _claim_status(db: Session, row_id: int, expected: str) -> int:
    """把一行挪出**这次扫描看见它时**的那个状态，用 rowcount 当"我抢到了"的凭证。

    MySQL 的 UPDATE rowcount 数的是**被改动**的行，不是被匹配的行（驱动默认不带
    CLIENT_FOUND_ROWS）。所以"同值写回"是一种假认领：WHERE 命中了、值没变、rowcount=0，
    两个进程各自以为对方抢到了——或者反过来都以为是自己抢到的，于是同一道题付两遍 qwen 调用。
    认领必须改变 status：`pending → running`（从没起跑）、`running → pending`（起跑过、
    进程已不在）。两种落点都还在 `STALE_STATUSES` 里，所以重投期间报告不会提前定稿。
    """
    target = "running" if expected == "pending" else "pending"
    return (
        db.query(InterviewTurnEvaluation)
        .filter(InterviewTurnEvaluation.id == row_id, InterviewTurnEvaluation.status == expected)
        .update({InterviewTurnEvaluation.status: target}, synchronize_session=False)
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
            # rowcount 0 = 别的进程先改了这一行的 status，不重复付费，也不报错。
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

        _append_evaluation_message(session, record)
        # 这一句 flush 是必须的，不是卫生代码：`SessionLocal` 的 `autoflush=False`
        # （`core/database.py:38`），而下面两处都是"读自己刚写的东西"——不 flush 就看不见。
        # 后果有两个，2026-10-09 由 D170 那台 mock 仪器在真 MySQL 上抓到：
        #   · `build_memory_snapshot` 少算刚刚这一题（它的 `completed_turns` 恒比实际少 1）；
        #   · `_evaluation_status` 数到"还有一题没跑完"，于是把 `processing` 写回去，
        #     `should_refresh_report` 因此永远不成立，**面试终报永远不会齐**。
        # 测试里看不见这件事，是因为 conftest 那个 sessionmaker 的 autoflush 是**开**的。
        db.flush()
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


def _append_evaluation_message(session: InterviewSession, record: InterviewTurnEvaluation) -> None:
    messages = list(session.messages or [])
    if any(
        (item.get("metadata") or {}).get("turn_id") == record.turn_id and item.get("type") == "evaluation"
        for item in messages
    ):
        return
    messages.append(
        {
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
            "timestamp": utc_now().isoformat(),
        }
    )
    session.messages = messages


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
    return {
        "version": 1,
        "generated_at": utc_now().isoformat(),
        "completed_turns": len(completed),
        "pending_turns": pending_count,
        "covered_categories": categories,
        "strengths": strengths,
        "risks": risks,
        "summary": summary,
    }


def _evaluation_status(db: Session, session_id: int, session_status: str) -> str:
    pending = pending_evaluation_count(db, session_id)
    if pending:
        return "processing"
    if session_status == "completed":
        return "completed"
    return "idle"


def refresh_completed_report(session_id: int) -> None:
    """Regenerate the final report only after every deferred score has been persisted."""
    from app.services.interview_engine import InterviewEngine

    engine = InterviewEngine(session_id)
    try:
        engine._load_session()
        if not engine.session or engine.session.status != "completed":
            return
        engine.question_count = len(engine.session.questions or [])
        engine.evaluations = engine._rebuild_evaluations()
        engine.start_time = engine._infer_start_time()
        report = engine._generate_report()
        report["evaluation_status"] = "completed"
        report["interview_memory"] = engine.session.memory_snapshot or {}
        engine.session.evaluation = report
        engine.session.evaluation_status = "completed"
        engine.db.commit()
    except Exception:
        logger.exception("Failed to refresh completed interview report session_id=%s", session_id)
    finally:
        engine.cleanup()


def _score(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0
