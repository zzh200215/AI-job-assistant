"""单项目分析的后台跑法：一条作业行、租约认领、读路径自愈。

形状抄 `report_job_service`（同一族问题：一次跑要几发模型调用，同步路由会把一根
anyio 线程和一条 DB 连接按住几分钟），这一族多出来的只有两件事：

* **两条 stage**：`report`（前三节）与 `questions`（第四节，按按钮才跑）。
  子行指回父行，父行是那份文档的正文所在；
* **装配只有一条路**：`assemble_document` 是"这份项目分析"唯一的读法——父行的三大节
  加上**最新那一发完成的**子行的第四节。下载、轮询、前端都走它。
  两份都能写的文档才会漂移；这里子行只写自己那一节，别的都是算出来的。

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
from app.models.project_report_job import STAGE_QUESTIONS, STAGE_REPORT, ProjectReportJob
from app.services.project_report_html import render_project_report_html
from app.services.project_report_schema import ProjectReport, report_from_dict
from app.services.project_report_service import generate_project_questions, generate_project_report
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
                thread_name_prefix="project-report-job",
            )
        return _executor


def shutdown_project_report_job_executor() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _purge_expired(db, user_id: int) -> None:
    cutoff = utc_now_naive() - timedelta(days=max(1, int(settings.REPORT_JOB_RETENTION_DAYS)))
    (
        db.query(ProjectReportJob)
        .filter(
            ProjectReportJob.user_id == user_id,
            ProjectReportJob.status.in_(TERMINAL_STATUSES),
            ProjectReportJob.finished_at < cutoff,
        )
        .delete(synchronize_session=False)
    )


def create_project_report_job(
    db, *, user_id: int, resume_id: int, project_index: int, project_name: str, jd_id: int | None, target_position: str
) -> ProjectReportJob:
    """同一 (人, 简历, 第几个项目) 上有未终态行就复用它，双击不该付两遍模型钱。"""
    _purge_expired(db, user_id)
    existing = (
        db.query(ProjectReportJob)
        .filter(
            ProjectReportJob.user_id == user_id,
            ProjectReportJob.resume_id == resume_id,
            ProjectReportJob.project_index == project_index,
            ProjectReportJob.stage == STAGE_REPORT,
            ProjectReportJob.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(ProjectReportJob.id.desc())
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
        existing.project_name = project_name or None
        existing.jd_id = jd_id
        existing.target_position = target_position or None
        db.commit()
        return existing

    job = ProjectReportJob(
        user_id=user_id,
        resume_id=resume_id,
        project_index=project_index,
        project_name=project_name or None,
        stage=STAGE_REPORT,
        jd_id=jd_id,
        target_position=target_position or None,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_questions_job(db, *, parent: ProjectReportJob) -> ProjectReportJob:
    """在已完成的那一份前三节之上续跑第四节；已有未终态的子行就复用。"""
    existing = (
        db.query(ProjectReportJob)
        .filter(
            ProjectReportJob.user_id == parent.user_id,
            ProjectReportJob.parent_job_id == parent.id,
            ProjectReportJob.stage == STAGE_QUESTIONS,
            ProjectReportJob.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(ProjectReportJob.id.desc())
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

    job = ProjectReportJob(
        user_id=parent.user_id,
        resume_id=parent.resume_id,
        project_index=parent.project_index,
        project_name=parent.project_name,
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


def submit_project_report_job(job_id: int) -> None:
    _get_executor().submit(process_project_report_job, job_id)


def claim_project_report_job(db, job_id: int) -> int:
    stamp = utc_now_naive()
    cutoff = stamp - timedelta(minutes=max(1, int(settings.REPORT_JOB_LEASE_MINUTES)))
    return (
        db.query(ProjectReportJob)
        .filter(
            ProjectReportJob.id == job_id,
            ProjectReportJob.status == "pending",
            (ProjectReportJob.claimed_at.is_(None)) | (ProjectReportJob.claimed_at < cutoff),
        )
        .update({ProjectReportJob.status: "running", ProjectReportJob.claimed_at: stamp}, synchronize_session=False)
    )


def _run_report_stage(db, job: ProjectReportJob) -> None:
    report = generate_project_report(
        db,
        job.resume_id,
        job.project_index,
        jd_id=job.jd_id,
        target_position=job.target_position or "",
        user_id=job.user_id,
    )
    job.report_json = report.to_public_dict()
    job.errors_json = {
        "stage_errors": report.stage_errors,
        "red_line_rejected": report.red_line_rejected,
        "diagram_rejected": report.diagram_rejected,
        "advice_rejected": report.advice_rejected,
    }
    job.provenance_json = report.provenance
    # 出局那一份库里**也不留总分与等级**：文档那一侧写的是"不作数"，库里却存着 73，
    # 于是"这一份到底有没有分"就有了两个答案——列表页读列、详情页读文档，两处会打架。
    job.total_score = None if report.is_excluded() else report.total_score
    job.grade = None if report.is_excluded() else report.grade
    job.difficulty = report.difficulty.get("level") or None
    job.excluded = 1 if report.is_excluded() else 0
    _try_lint(db, job, report)


def _run_questions_stage(db, job: ProjectReportJob) -> None:
    parent = db.get(ProjectReportJob, job.parent_job_id or 0)
    if parent is None or not parent.report_json:
        raise ValueError("这一节要挂在一份已完成的前三节上")
    report = report_from_dict(parent.report_json)
    generate_project_questions(db, report, user_id=job.user_id)
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


def _try_lint(db, job: ProjectReportJob, report: ProjectReport) -> None:
    """落库这一刻渲一次：不合格不拦这一发（文档已经在库里），只记 lint_failures。"""
    try:
        render_project_report_html(report)
    except RuntimeError as exc:
        job.lint_failures = 1
        logger.error("单项目分析未通过交付前机检 job=%s\n%s", job.id, exc)


def run_job_on(db, job_id: int) -> bool:
    """在**给定会话**上跑完这一发。返回 False = 我没抢到，不是失败。"""
    if claim_project_report_job(db, job_id) == 0:
        db.commit()
        return False
    db.commit()

    job = db.get(ProjectReportJob, job_id)
    if job is None:
        return False
    try:
        if job.stage == STAGE_QUESTIONS:
            _run_questions_stage(db, job)
        else:
            _run_report_stage(db, job)
        job.status = "completed"
    except Exception as exc:  # noqa: BLE001 - 后台这一跑没人接异常，落库就是它唯一的去处
        logger.exception("单项目分析作业失败 job=%s", job_id)
        db.rollback()
        job = db.get(ProjectReportJob, job_id)
        if job is None:
            return False
        job.status = "failed"
        job.error = 1
        job.error_msg = f"{type(exc).__name__}: {str(exc)[:300]}"
    job.finished_at = utc_now_naive()
    job.claimed_at = None
    db.commit()
    return True


def process_project_report_job(job_id: int) -> bool:
    db = SessionLocal()
    try:
        return run_job_on(db, job_id)
    finally:
        db.close()


def touch_job_for_read(db, job: ProjectReportJob) -> str:
    if job.status in TERMINAL_STATUSES:
        return job.status
    lease_cutoff = utc_now_naive() - timedelta(minutes=max(1, int(settings.REPORT_JOB_LEASE_MINUTES)))
    stale = job.claimed_at is None or job.claimed_at < lease_cutoff
    if job.status == "running" and stale:
        job.status = "pending"
        job.claimed_at = None
        db.commit()
        submit_project_report_job(job.id)
        return "pending"
    if job.status == "pending" and stale:
        submit_project_report_job(job.id)
    return job.status


def latest_questions_child(db, parent_job_id: int) -> ProjectReportJob | None:
    return (
        db.query(ProjectReportJob)
        .filter(
            ProjectReportJob.parent_job_id == parent_job_id,
            ProjectReportJob.stage == STAGE_QUESTIONS,
            ProjectReportJob.status == "completed",
        )
        .order_by(ProjectReportJob.id.desc())
        .first()
    )


def assemble_document(db, job: ProjectReportJob) -> dict:
    """这份项目分析的唯一读法：父行的三大节 + 最新那一发完成的第四节。"""
    if job.stage == STAGE_QUESTIONS:
        parent = db.get(ProjectReportJob, job.parent_job_id or 0)
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
        advice = document.get("advice") or {}
        practice = dict(advice.get("practice") or {})
        backfill = questions.get("practice") or {}
        practice["must_practice"] = backfill.get("must_practice") or ""
        practice["high_risk"] = backfill.get("high_risk") or ""
        advice["practice"] = practice
        document["advice"] = advice
    else:
        document["questions"] = None
        document["questions_state"] = "not_generated"
    document["job_id"] = parent.id
    document["questions_job_id"] = child.id if child else None
    return document


def serialize_job(job: ProjectReportJob, *, document: dict | None = None) -> dict:
    """轮询载荷。**没有 `error_msg`、没有 `errors_json`**：那两处可能带模型输出。"""
    data = {
        "job_id": job.id,
        "stage": job.stage,
        "parent_job_id": job.parent_job_id,
        "resume_id": job.resume_id,
        "project_index": job.project_index,
        "project_name": job.project_name or "",
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
    "claim_project_report_job",
    "create_project_report_job",
    "create_questions_job",
    "latest_questions_child",
    "process_project_report_job",
    "run_job_on",
    "serialize_job",
    "shutdown_project_report_job_executor",
    "submit_project_report_job",
    "touch_job_for_read",
]
