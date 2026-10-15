"""组合分析的后台跑法：一条作业行、租约认领、读路径自愈。

形状抄 `project_report_job_service`（同一族问题：一次跑要几发模型调用，同步路由会把一根
anyio 线程和一条 DB 连接按住几分钟），这一族改的只有两件事：

* **去重键换成 `combo_key`**：同一 (人, 简历, 选中了哪几个项目) 上有未终态行就复用它，
  双击不该付两遍模型钱；
* **装配只有一条路**：`assemble_document` 是"这份组合分析"唯一的读法——父行的三大节
  加上**最新那一发完成的**子行的第四节。下载、轮询、前端都走它。

三条沿用不变的克制：不把 `error_msg` 放上轮询载荷；读路径自愈不另立调度任务；
落库那一刻就跑一次交付前机检，不合格的那一份不该等到下载时才暴露。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Lock

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.portfolio_report_job import STAGE_QUESTIONS, STAGE_REPORT, PortfolioReportJob
from app.services.portfolio_report_schema import PortfolioReport, report_from_dict
from app.services.portfolio_report_service import generate_portfolio_questions, generate_portfolio_report
from app.utils.time_helper import utc_now_naive

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "failed")

_executor: ThreadPoolExecutor | None = None
_executor_lock = Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, settings.REPORT_JOB_MAX_WORKERS),
                thread_name_prefix="portfolio-report-job",
            )
        return _executor


def shutdown_portfolio_report_job_executor() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _purge_expired(db, user_id: int) -> None:
    cutoff = utc_now_naive() - timedelta(days=max(1, int(settings.REPORT_JOB_RETENTION_DAYS)))
    (
        db.query(PortfolioReportJob)
        .filter(
            PortfolioReportJob.user_id == user_id,
            PortfolioReportJob.status.in_(TERMINAL_STATUSES),
            PortfolioReportJob.finished_at < cutoff,
        )
        .delete(synchronize_session=False)
    )


def create_portfolio_report_job(
    db,
    *,
    user_id: int,
    resume_id: int,
    combo_key: str,
    project_indices: list[int],
    project_names: list[str],
    jd_id: int | None,
    target_position: str,
) -> PortfolioReportJob:
    _purge_expired(db, user_id)
    existing = (
        db.query(PortfolioReportJob)
        .filter(
            PortfolioReportJob.user_id == user_id,
            PortfolioReportJob.resume_id == resume_id,
            PortfolioReportJob.combo_key == combo_key,
            PortfolioReportJob.stage == STAGE_REPORT,
            PortfolioReportJob.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(PortfolioReportJob.id.desc())
        .first()
    )
    if existing is not None:
        existing.status = "pending"
        existing.claimed_at = None
        existing.error = 0
        existing.error_msg = None
        existing.report_json = None
        existing.errors_json = None
        existing.provenance_json = None
        existing.lint_failures = 0
        existing.total_score = None
        existing.grade = None
        existing.difficulty = None
        existing.excluded = 0
        existing.finished_at = None
        existing.project_indices = list(project_indices)
        existing.project_count = len(project_indices)
        existing.project_names = list(project_names)
        existing.jd_id = jd_id
        existing.target_position = target_position or None
        db.commit()
        return existing

    job = PortfolioReportJob(
        user_id=user_id,
        resume_id=resume_id,
        combo_key=combo_key,
        project_indices=list(project_indices),
        project_count=len(project_indices),
        project_names=list(project_names),
        stage=STAGE_REPORT,
        jd_id=jd_id,
        target_position=target_position or None,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_portfolio_questions_job(db, *, parent: PortfolioReportJob) -> PortfolioReportJob:
    """在已完成的那一份前三节之上续跑第四节；已有未终态的子行就复用。"""
    existing = (
        db.query(PortfolioReportJob)
        .filter(
            PortfolioReportJob.user_id == parent.user_id,
            PortfolioReportJob.parent_job_id == parent.id,
            PortfolioReportJob.stage == STAGE_QUESTIONS,
            PortfolioReportJob.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(PortfolioReportJob.id.desc())
        .first()
    )
    if existing is not None:
        existing.status = "pending"
        existing.claimed_at = None
        existing.error = 0
        existing.error_msg = None
        existing.report_json = None
        existing.errors_json = None
        existing.provenance_json = None
        existing.finished_at = None
        db.commit()
        return existing

    job = PortfolioReportJob(
        user_id=parent.user_id,
        resume_id=parent.resume_id,
        combo_key=parent.combo_key,
        project_indices=list(parent.project_indices or []),
        project_count=parent.project_count,
        project_names=list(parent.project_names or []),
        stage=STAGE_QUESTIONS,
        parent_job_id=parent.id,
        jd_id=parent.jd_id,
        target_position=parent.target_position,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def submit_portfolio_report_job(job_id: int) -> None:
    _get_executor().submit(process_portfolio_report_job, job_id)


def claim_portfolio_report_job(db, job_id: int) -> int:
    stamp = utc_now_naive()
    cutoff = stamp - timedelta(minutes=max(1, int(settings.REPORT_JOB_LEASE_MINUTES)))
    return (
        db.query(PortfolioReportJob)
        .filter(
            PortfolioReportJob.id == job_id,
            PortfolioReportJob.status == "pending",
            (PortfolioReportJob.claimed_at.is_(None)) | (PortfolioReportJob.claimed_at < cutoff),
        )
        .update({PortfolioReportJob.status: "running", PortfolioReportJob.claimed_at: stamp}, synchronize_session=False)
    )


def _run_report_stage(db, job: PortfolioReportJob) -> None:
    report = generate_portfolio_report(
        db,
        job.resume_id,
        [int(i) for i in (job.project_indices or [])],
        jd_id=job.jd_id,
        target_position=job.target_position or "",
        user_id=job.user_id,
    )
    job.report_json = report.to_public_dict()
    job.errors_json = {
        "stage_errors": report.stage_errors,
        "red_line_rejected": report.red_line_rejected,
        "compare_rejected": report.compare_rejected,
        "capability_rejected": report.capability_rejected,
        "diagram_rejected": report.diagram_rejected,
        "advice_rejected": report.advice_rejected,
    }
    job.provenance_json = report.provenance
    # 出局那一份库里也不留总分与等级（与单项目那一族同一条口径，理由见那边的注释）。
    job.total_score = None if report.is_excluded() else report.total_score
    job.grade = None if report.is_excluded() else report.grade
    job.difficulty = report.difficulty.get("level") or None
    job.excluded = 1 if report.is_excluded() else 0
    _try_lint(db, job, report)


def _run_questions_stage(db, job: PortfolioReportJob) -> None:
    parent = db.get(PortfolioReportJob, job.parent_job_id or 0)
    if parent is None or not parent.report_json:
        raise ValueError("这一节要挂在一份已完成的前三节上")
    report = report_from_dict(parent.report_json)
    generate_portfolio_questions(db, report, user_id=job.user_id)
    payload = report.questions or {}
    job.report_json = {
        "questions": payload,
        "distribution": payload.get("distribution"),
        "practice": payload.get("practice") or {},
        "deferred": bool(payload.get("deferred")),
        "excluded": report.is_excluded(),
    }
    job.errors_json = {"stage_errors": report.stage_errors, "questions_rejected": report.questions_rejected}
    job.provenance_json = {"questions": report.provenance.get("questions")}
    _try_lint(db, job, report)


def _try_lint(db, job: PortfolioReportJob, report: PortfolioReport) -> None:
    """落库这一刻渲一次：不合格不拦这一发（文档已经在库里），只记 lint_failures。

    渲染器还没接上时这一发不该把作业带崩，所以整块包在 try 里——但**记在 errors_json 里**，
    不对静默：一条 lint_failures=1 的作业行就是这一份交付前机检没过。
    """
    try:
        from app.services.portfolio_report_html import render_portfolio_report_html

        render_portfolio_report_html(report)
    except RuntimeError as exc:
        job.lint_failures = 1
        logger.error("组合分析未通过交付前机检 job=%s\n%s", job.id, exc)
    except Exception as exc:  # noqa: BLE001 - 机检自身的失败不该让这一发变成"生成失败"
        logger.exception("组合分析交付前机检自身出错 job=%s", job.id)
        if isinstance(job.errors_json, dict):
            job.errors_json = {**job.errors_json, "lint_error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def run_job_on(db, job_id: int) -> bool:
    """在**给定会话**上跑完这一发。返回 False = 我没抢到，不是失败。"""
    if claim_portfolio_report_job(db, job_id) == 0:
        db.commit()
        return False
    db.commit()

    job = db.get(PortfolioReportJob, job_id)
    if job is None:
        return False
    try:
        if job.stage == STAGE_QUESTIONS:
            _run_questions_stage(db, job)
        else:
            _run_report_stage(db, job)
        job.status = "completed"
    except Exception as exc:  # noqa: BLE001 - 后台这一跑没人接异常，落库就是它唯一的去处
        logger.exception("组合分析作业失败 job=%s", job_id)
        db.rollback()
        job = db.get(PortfolioReportJob, job_id)
        if job is None:
            return False
        job.status = "failed"
        job.error = 1
        job.error_msg = f"{type(exc).__name__}: {str(exc)[:300]}"
    job.finished_at = utc_now_naive()
    job.claimed_at = None
    db.commit()
    return True


def process_portfolio_report_job(job_id: int) -> bool:
    db = SessionLocal()
    try:
        return run_job_on(db, job_id)
    finally:
        db.close()


def touch_job_for_read(db, job: PortfolioReportJob) -> str:
    if job.status in TERMINAL_STATUSES:
        return job.status
    lease_cutoff = utc_now_naive() - timedelta(minutes=max(1, int(settings.REPORT_JOB_LEASE_MINUTES)))
    stale = job.claimed_at is None or job.claimed_at < lease_cutoff
    if job.status == "running" and stale:
        job.status = "pending"
        job.claimed_at = None
        db.commit()
        submit_portfolio_report_job(job.id)
        return "pending"
    if job.status == "pending" and stale:
        submit_portfolio_report_job(job.id)
    return job.status


def latest_questions_child(db, parent_job_id: int) -> PortfolioReportJob | None:
    return (
        db.query(PortfolioReportJob)
        .filter(
            PortfolioReportJob.parent_job_id == parent_job_id,
            PortfolioReportJob.stage == STAGE_QUESTIONS,
            PortfolioReportJob.status == "completed",
        )
        .order_by(PortfolioReportJob.id.desc())
        .first()
    )


def assemble_document(db, job: PortfolioReportJob) -> dict:
    """这份组合分析的唯一读法：父行的三大节 + 最新那一发完成的第四节。"""
    if job.stage == STAGE_QUESTIONS:
        parent = db.get(PortfolioReportJob, job.parent_job_id or 0)
        if parent is None:
            return {}
    else:
        parent = job
    document = dict(parent.report_json or {})
    if not document:
        return {}
    child = latest_questions_child(db, parent.id)
    questions = (child.report_json or {}).get("questions") if child else None
    if questions:
        document["questions"] = questions
        document["questions_state"] = "deferred" if questions.get("deferred") else "ready"
    else:
        document["questions"] = None
        document["questions_state"] = "not_generated"
    document["job_id"] = parent.id
    document["questions_job_id"] = child.id if child else None
    return document


def serialize_job(job: PortfolioReportJob, *, document: dict | None = None) -> dict:
    """轮询载荷。**没有 `error_msg`、没有 `errors_json`**：那两处可能带模型输出。"""
    data = {
        "job_id": job.id,
        "stage": job.stage,
        "parent_job_id": job.parent_job_id,
        "resume_id": job.resume_id,
        "combo_key": job.combo_key,
        "project_indices": list(job.project_indices or []),
        "project_count": job.project_count,
        "project_names": list(job.project_names or []),
        "jd_id": job.jd_id,
        "target_position": job.target_position or "",
        "status": job.status,
        "total_score": job.total_score,
        "grade": job.grade,
        "difficulty": job.difficulty,
        "excluded": bool(job.excluded),
        "create_time": job.create_time.isoformat() if job.create_time else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    if document is not None:
        data["report"] = document or None
    return data


__all__ = [
    "TERMINAL_STATUSES",
    "assemble_document",
    "claim_portfolio_report_job",
    "create_portfolio_questions_job",
    "create_portfolio_report_job",
    "latest_questions_child",
    "process_portfolio_report_job",
    "run_job_on",
    "serialize_job",
    "shutdown_portfolio_report_job_executor",
    "submit_portfolio_report_job",
    "touch_job_for_read",
]
