"""Background evaluation, evidence persistence, and memory snapshots for interview turns."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any

from sqlalchemy.orm import Session

from app.agents.answer_evaluation_agent import AnswerEvaluationAgent
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.interview_evaluation import InterviewTurnEvaluation
from app.models.interview_session import InterviewSession
from app.orchestration.context import AgentContext
from app.utils.time_helper import utc_now

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
    """Schedule a best-effort evaluation. The durable row remains recoverable after a restart."""
    _get_executor().submit(process_turn_evaluation, session_id, evaluation_id)


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
