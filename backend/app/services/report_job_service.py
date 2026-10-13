"""D229：报告作业的后台跑法。形状抄改写作业（自己的线程池、可恢复的一行、按租约认领），
不抄编排：一次报告是三发模型调用串起来的固定顺序，不是一次多智能体协作。

两条与改写作业相同的克制：
* 不把 `error_msg` 放上轮询载荷（那句里可能有模型输出）；
* 读路径自愈（过期 running 退回 pending 重投），不另立调度任务——候选人一定会来读。

还有一条是这一族特有的：**报告不落 `tb_resume`**。表里存的是这一份文档，
候选人点"采纳"走 `apply-rewrites` 那条既有写路径，快照与撤销都在那一侧。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Lock

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.report_job import ResumeReportJob
from app.services.resume_report_html import render_report_html
from app.services.resume_report_schema import Report
from app.services.resume_report_service import generate_resume_report
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
                thread_name_prefix="report-job",
            )
        return _executor


def shutdown_report_job_executor() -> None:
    """进程退出时丢掉未起跑的作业；可恢复性不靠进程，靠读路径那一次重投。"""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _purge_expired(db, user_id: int) -> None:
    cutoff = utc_now_naive() - timedelta(days=max(1, int(settings.REPORT_JOB_RETENTION_DAYS)))
    (
        db.query(ResumeReportJob)
        .filter(
            ResumeReportJob.user_id == user_id,
            ResumeReportJob.status.in_(TERMINAL_STATUSES),
            ResumeReportJob.finished_at < cutoff,
        )
        .delete(synchronize_session=False)
    )


def create_report_job(db, *, user_id: int, resume_id: int, jd_id: int | None, target_position: str) -> ResumeReportJob:
    """同一 (人, 简历) 上已有未终态行就复用它，不再插一行。

    这里的复用键**不含 jd_id**：一份报告的批改稿与面试预演是简历级的，
    换目标岗位重跑一次是同一件事的第二次尝试，双击不该付两遍模型钱。
    """
    _purge_expired(db, user_id)
    existing = (
        db.query(ResumeReportJob)
        .filter(
            ResumeReportJob.user_id == user_id,
            ResumeReportJob.resume_id == resume_id,
            ResumeReportJob.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(ResumeReportJob.id.desc())
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
        existing.finished_at = None
        existing.jd_id = jd_id
        existing.target_position = target_position or None
        db.commit()
        return existing

    job = ResumeReportJob(
        user_id=user_id,
        resume_id=resume_id,
        jd_id=jd_id,
        target_position=target_position or None,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def submit_report_job(job_id: int) -> None:
    _get_executor().submit(process_report_job, job_id)


def claim_report_job(db, job_id: int) -> int:
    stamp = utc_now_naive()
    cutoff = stamp - timedelta(minutes=max(1, int(settings.REPORT_JOB_LEASE_MINUTES)))
    return (
        db.query(ResumeReportJob)
        .filter(
            ResumeReportJob.id == job_id,
            ResumeReportJob.status == "pending",
            (ResumeReportJob.claimed_at.is_(None)) | (ResumeReportJob.claimed_at < cutoff),
        )
        .update(
            {ResumeReportJob.status: "running", ResumeReportJob.claimed_at: stamp},
            synchronize_session=False,
        )
    )


def run_job_on(db, job_id: int) -> bool:
    """在**给定会话**上跑完这一发。返回 False = 我没抢到，不是失败。

    拆这一层是因为线程池自开的那条 `SessionLocal` 在测试里连的是另一块内存库。
    """
    if claim_report_job(db, job_id) == 0:
        db.commit()
        return False
    db.commit()

    job = db.get(ResumeReportJob, job_id)
    if job is None:
        return False
    try:
        report = generate_resume_report(
            db,
            job.resume_id,
            jd_id=job.jd_id,
            target_position=job.target_position or "",
            user_id=job.user_id,
        )
        job.report_json = report.to_public_dict()
        job.errors_json = {
            "stage_errors": report.stage_errors,
            "redline_rejected": report.redline_rejected,
            "interview_rejected": report.interview_rejected,
        }
        job.provenance_json = report.provenance
        job.total_score = report.total_score
        job.grade = report.grade
        # 交付前机检在落库这一刻就跑一次：不合格的那一份不该等到下载时才暴露。
        try:
            render_report_html(report)
        except RuntimeError as exc:
            job.lint_failures = 1
            logger.error("报告未通过交付前机检 job=%s\n%s", job_id, exc)
        job.status = "completed"
    except Exception as exc:  # noqa: BLE001 - 后台这一跑没人接异常，落库就是它唯一的去处
        logger.exception("报告作业失败 job=%s", job_id)
        db.rollback()
        job = db.get(ResumeReportJob, job_id)
        if job is None:
            return False
        job.status = "failed"
        job.error = 1
        job.error_msg = f"{type(exc).__name__}: {str(exc)[:300]}"
    job.finished_at = utc_now_naive()
    job.claimed_at = None
    db.commit()
    return True


def process_report_job(job_id: int) -> bool:
    db = SessionLocal()
    try:
        return run_job_on(db, job_id)
    finally:
        db.close()


def touch_job_for_read(db, job: ResumeReportJob) -> str:
    if job.status in TERMINAL_STATUSES:
        return job.status
    lease_cutoff = utc_now_naive() - timedelta(minutes=max(1, int(settings.REPORT_JOB_LEASE_MINUTES)))
    stale = job.claimed_at is None or job.claimed_at < lease_cutoff
    if job.status == "running" and stale:
        job.status = "pending"
        job.claimed_at = None
        db.commit()
        submit_report_job(job.id)
        return "pending"
    if job.status == "pending" and stale:
        submit_report_job(job.id)
    return job.status


def serialize_job(job: ResumeReportJob, *, include_report: bool = True) -> dict:
    """轮询载荷。**没有 `error_msg`、没有 `errors_json`**：那两处可能带模型输出。"""
    data = {
        "job_id": job.id,
        "resume_id": job.resume_id,
        "jd_id": job.jd_id,
        "target_position": job.target_position or "",
        "status": job.status,
        "total_score": job.total_score,
        "grade": job.grade,
        "create_time": job.create_time.isoformat() if job.create_time else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
    if include_report:
        data["report"] = job.report_json or None
    return data


def report_from_dict(data: dict) -> Report:
    """把库里那份候选人视图还原成 Report。

    只还原渲染与"采纳"要用的部分；`model_reported_total` 之类的对内证据本来就没入库，
    所以这里不需要清字段，也不需要防它漏出去。
    """
    from app.services.resume_report_schema import Redline, RedlineBlock, RedlineEdit

    redline = None
    raw_redline = data.get("redline")
    if isinstance(raw_redline, dict):
        blocks = []
        for block in raw_redline.get("blocks") or []:
            edits = [
                RedlineEdit(
                    mark=int(edit.get("mark") or 0),
                    block_id=edit.get("block_id") or block["block_id"],
                    del_text=edit.get("del") or "",
                    ins_text=edit.get("ins") or "",
                    note=edit.get("note") or "",
                    key=bool(edit.get("key")),
                )
                for edit in (block.get("edits") or [])
            ]
            blocks.append(
                RedlineBlock(
                    block_id=block["block_id"],
                    label=block.get("label") or "",
                    text=block.get("text") or "",
                    edits=edits,
                    editable=bool(block.get("editable", True)),
                )
            )
        redline = Redline(
            blocks=blocks, mode=raw_redline.get("mode") or "changes", free_note=raw_redline.get("free_note") or ""
        )

    return Report(
        resume_id=int(data.get("resume_id") or 0),
        jd_id=data.get("jd_id"),
        target_position=data.get("target_position") or "",
        report_date=data.get("report_date") or "",
        verdict=data.get("verdict") or {},
        dimensions=data.get("dimensions") or [],
        total_score=data.get("total_score"),
        grade=data.get("grade"),
        grade_desc=data.get("grade_desc") or "",
        grade_scale=data.get("grade_scale") or "",
        to_next_grade=data.get("to_next_grade") or [],
        missing_keywords=data.get("missing_keywords") or [],
        competition=data.get("competition") or {},
        redline=redline,
        interview=data.get("interview"),
        apply_strategy=data.get("apply_strategy"),
        sections=data.get("sections") or [],
        personalization=data.get("personalization") or {},
    )


__all__ = [
    "TERMINAL_STATUSES",
    "claim_report_job",
    "create_report_job",
    "process_report_job",
    "report_from_dict",
    "run_job_on",
    "serialize_job",
    "shutdown_report_job_executor",
    "submit_report_job",
    "touch_job_for_read",
]
