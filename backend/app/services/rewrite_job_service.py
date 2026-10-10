"""D200: the background run behind `POST /resume/{id}/rewrite-suggestion-jobs`.

Shape borrowed from the interview per-turn evaluator (own thread pool, durable row, per-row claim
with a lease) rather than from orchestration: this is one model call returning one JSON, not a
multi-agent run, and `agent_task` cannot carry it — `models/agent.py:24` makes `jd_id` NOT NULL
while this endpoint's JD is optional, and putting these rows in `agent_task` would make the
candidate's task centre fill up with jobs they never asked to see.

Two things this file deliberately does not do:
* It never writes to `tb_resume`. The payload lives in this table and dies here.
* It does not put `error_msg` on the wire. That text can carry model output, and the polling
  endpoint is external — see the same reasoning at `llm_service.py:1097`.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Lock

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.rewrite_job import RewriteSuggestionJob
from app.services.llm_service import get_llm_provenance
from app.services.resume_rewrite_service import build_rewrite_suggestions
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
                max_workers=max(1, settings.REWRITE_JOB_MAX_WORKERS),
                thread_name_prefix="rewrite-job",
            )
        return _executor


def shutdown_rewrite_job_executor() -> None:
    """进程退出时丢掉未起跑的作业。语义与逐题评分那一池相同：`cancel_futures=True`。

    敢取消是因为这一族的可恢复性不靠进程：作业行留在 `pending`/`running`，租约过期后由轮询
    那一条路径重新投递（`touch_job_for_read`），所以取消只是把"再等一次模型"推给下一次读。
    """
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _purge_expired(db, user_id: int) -> None:
    """写时顺带清理：删掉本人已过保留期的终态作业，不另立调度任务。

    只删终态——`pending`/`running` 可能是别人正在等的那一发。
    """
    cutoff = utc_now_naive() - timedelta(days=max(1, int(settings.REWRITE_JOB_RETENTION_DAYS)))
    (
        db.query(RewriteSuggestionJob)
        .filter(
            RewriteSuggestionJob.user_id == user_id,
            RewriteSuggestionJob.status.in_(TERMINAL_STATUSES),
            RewriteSuggestionJob.finished_at < cutoff,
        )
        .delete(synchronize_session=False)
    )


def create_rewrite_job(db, *, user_id: int, resume_id: int, jd_id: int | None) -> RewriteSuggestionJob:
    """一行作业；同一 (人, 简历, 岗位) 上已有未终态行时**复用**而不是再插一行。

    双击、断网重提都会走到这里。插第二行等于让同一次改写付两遍模型钱。
    """
    _purge_expired(db, user_id)

    existing = (
        db.query(RewriteSuggestionJob)
        .filter(
            RewriteSuggestionJob.user_id == user_id,
            RewriteSuggestionJob.resume_id == resume_id,
            RewriteSuggestionJob.status.notin_(TERMINAL_STATUSES),
        )
        .order_by(RewriteSuggestionJob.id.desc())
        .first()
    )
    if existing is not None and (existing.jd_id or None) == (jd_id or None):
        existing.status = "pending"
        existing.claimed_at = None
        existing.error = 0
        existing.error_msg = None
        existing.suggestions = None
        existing.rejected = None
        existing.note = None
        existing.provenance = None
        existing.finished_at = None
        db.commit()
        return existing

    job = RewriteSuggestionJob(user_id=user_id, resume_id=resume_id, jd_id=jd_id, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def submit_rewrite_job(job_id: int) -> None:
    _get_executor().submit(process_rewrite_job, job_id)


def claim_rewrite_job(db, job_id: int) -> int:
    """把这一行从 `pending` 挪进 `running`，用 rowcount 当凭证（D178 同一条理由）。

    租约那半句是关键的：只看 `status == 'pending'` 的话，一次"把 running 改回 pending 重投"
    和"从 pending 起跑"是两条不同的 transition，两个扫描者可以各领一条而都以为赢了。
    """
    stamp = utc_now_naive()
    cutoff = stamp - timedelta(minutes=max(1, int(settings.REWRITE_JOB_LEASE_MINUTES)))
    return (
        db.query(RewriteSuggestionJob)
        .filter(
            RewriteSuggestionJob.id == job_id,
            RewriteSuggestionJob.status == "pending",
            (RewriteSuggestionJob.claimed_at.is_(None)) | (RewriteSuggestionJob.claimed_at < cutoff),
        )
        .update(
            {RewriteSuggestionJob.status: "running", RewriteSuggestionJob.claimed_at: stamp},
            synchronize_session=False,
        )
    )


def run_job_on(db, job_id: int) -> bool:
    """在**给定会话**上跑完这一发。返回 False = "我没抢到"，不是失败。

    拆成这一层是因为执行器入口自己开的那条 `SessionLocal` 在测试里连的是另一块内存库
    （本项目有两块，见 conftest），夹具数据不在里面。测试要能驱动同一段逻辑，而不是
    另写一份"看起来一样"的。
    """
    if claim_rewrite_job(db, job_id) == 0:
        db.commit()
        logger.info("改写作业已被别的线程领走，跳过：%s", job_id)
        return False
    db.commit()

    job = db.get(RewriteSuggestionJob, job_id)
    if job is None:
        return False
    try:
        result = build_rewrite_suggestions(db, job.resume_id, jd_id=job.jd_id, user_id=job.user_id)
        job.suggestions = result.get("suggestions") or []
        job.rejected = result.get("rejected") or []
        job.note = result.get("note")
        job.block_total = int(result.get("block_total") or 0)
        job.provenance = get_llm_provenance()
        job.status = "completed"
    except Exception as exc:  # noqa: BLE001 - 后台这一跑没人接异常，落库就是它唯一的去处
        logger.exception("改写作业失败：%s", job_id)
        db.rollback()
        job = db.get(RewriteSuggestionJob, job_id)
        if job is None:
            return False
        job.status = "failed"
        job.error = 1
        job.error_msg = f"{type(exc).__name__}: {str(exc)[:300]}"
    job.finished_at = utc_now_naive()
    job.claimed_at = None
    db.commit()
    return True


def process_rewrite_job(job_id: int) -> bool:
    """线程池的入口：自开一条会话，跑完就还回去。"""
    db = SessionLocal()
    try:
        return run_job_on(db, job_id)
    finally:
        db.close()


def touch_job_for_read(db, job: RewriteSuggestionJob) -> str:
    """读的时候自愈：进程死在半路留下的 `running`/过期租约，在这里退回 `pending` 并重投。

    放在读路径而不是调度任务里，是因为候选人一定会来读——轮询本身就是那条恢复扫描。
    """
    if job.status in TERMINAL_STATUSES:
        return job.status
    lease_cutoff = utc_now_naive() - timedelta(minutes=max(1, int(settings.REWRITE_JOB_LEASE_MINUTES)))
    stale = job.claimed_at is None or job.claimed_at < lease_cutoff
    if job.status == "running" and stale:
        job.status = "pending"
        job.claimed_at = None
        db.commit()
        submit_rewrite_job(job.id)
        return "pending"
    if job.status == "pending" and stale:
        # pending 且从没被领过（或租约早过了）= 投进去的那一发被 shutdown 取消了，补投一次。
        submit_rewrite_job(job.id)
    return job.status


def serialize_job(job: RewriteSuggestionJob) -> dict:
    """给轮询端点的载荷。**没有 `error_msg`**：那句里可能有模型返回的内容。"""
    return {
        "job_id": job.id,
        "resume_id": job.resume_id,
        "jd_id": job.jd_id,
        "status": job.status,
        "block_total": job.block_total,
        "suggestions": job.suggestions or [],
        "rejected": job.rejected or [],
        "note": job.note,
        "create_time": job.create_time.isoformat() if job.create_time else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
