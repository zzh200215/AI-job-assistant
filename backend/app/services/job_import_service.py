"""D226: the background run behind `POST /jobs/batch-import`.

Shape borrowed from `rewrite_job_service` (own thread pool, durable row, per-row claim with a
lease, write-time purge, read-time self-heal) rather than invented here.

One deliberate difference from that file: **the parsed rows are not stored**. A batch import's
payload is the uploaded file itself (up to 10 MB), which has no business living in a JSON column.
That buys the normal case everything it needs and gives up one thing — if the process dies mid-run,
there is nothing to re-parse from. So the read path does not resubmit a stale `running` row: it
marks it `failed` with a message that says "重新上传文件". Pretending otherwise (a lease that
"recovers" a job it cannot recover) is how a row ends up failed-by-timeout forever.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Lock

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.history import JobDescription
from app.models.job_import import JobImportTask
from app.utils.time_helper import utc_now_naive

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "failed", "canceled")
RUNNING_STALE = "导入进程已中断（服务重启或崩溃），未完成的行没有落库，请重新上传文件。"

_executor: ThreadPoolExecutor | None = None
_executor_lock = Lock()


def parse_rows(file_name: str, content: bytes) -> list[dict]:
    """把上传的文件解析成"每一条待入库岗位"的字典列表。

    缺必填字段的行不在这里丢——它们要计入 `skipped` 并留下原因，候选人才能知道"1000 行里
    有 40 行没标题"，而不是拿到一个 `imported 960` 却不知道为什么。
    """
    name = (file_name or "").lower()
    rows: list[dict] = []
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig")
        for index, row in enumerate(csv.DictReader(io.StringIO(text)), start=1):
            rows.append(
                {
                    "row": index,
                    "title": (row.get("title") or row.get("职位名称") or "").strip(),
                    "company": (row.get("company") or row.get("公司") or "").strip(),
                    "location": (row.get("location") or row.get("地点") or "").strip(),
                    "salary_range": (row.get("salary_range") or row.get("薪资") or "").strip(),
                    "industry": (row.get("industry") or row.get("行业") or "").strip(),
                    "raw_text": (
                        row.get("raw_text") or row.get("rawText") or row.get("JD文本") or row.get("jd_text") or ""
                    ).strip(),
                }
            )
    elif name.endswith(".json"):
        data = json.loads(content.decode("utf-8"))
        items = data if isinstance(data, list) else data.get("jobs", data.get("items", []))
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                rows.append({"row": index, "title": "", "raw_text": "", "malformed": "不是对象"})
                continue
            rows.append(
                {
                    "row": index,
                    "title": (item.get("title") or item.get("职位名称") or "").strip(),
                    "company": (item.get("company") or item.get("公司") or "").strip(),
                    "location": (item.get("location") or item.get("地点") or "").strip(),
                    "salary_range": (item.get("salary_range") or item.get("薪资") or "").strip(),
                    "industry": (item.get("industry") or item.get("行业") or "").strip(),
                    "raw_text": (
                        item.get("raw_text")
                        or item.get("rawText")
                        or item.get("jd_text")
                        or item.get("description")
                        or ""
                    ).strip(),
                }
            )
    else:
        raise ValueError("only CSV and JSON are supported")
    return rows


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, settings.JOB_IMPORT_MAX_WORKERS),
                thread_name_prefix="job-import",
            )
        return _executor


def shutdown_job_import_executor() -> None:
    """进程退出时丢掉未起跑的作业；已经在跑的那一发由 `cancel_futures` 一起取消。

    与 rewrite 那一池不同的是：**这里不靠重投恢复**（解析结果没落库），所以取消掉的 pending
    作业会被读路径判成 failed 并提示重新上传，而不是悄悄再跑一遍。
    """
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _purge_expired(db, user_id: int) -> None:
    cutoff = utc_now_naive() - timedelta(days=max(1, int(settings.JOB_IMPORT_RETENTION_DAYS)))
    (
        db.query(JobImportTask)
        .filter(
            JobImportTask.user_id == user_id,
            JobImportTask.status.in_(TERMINAL_STATUSES),
            JobImportTask.finished_at < cutoff,
        )
        .delete(synchronize_session=False)
    )


def create_job(db, *, user_id: int, file_name: str, source: str, total: int) -> JobImportTask:
    """一行新作业。

    这里**不**复用"同一人未终态的作业"来去重（rewrite 那边做了）：两次上传是两个不同的文件，
    把它们并成一行会让第二次静默丢失。双击的防护交给前端的按钮禁用，不靠服务端猜。
    """
    _purge_expired(db, user_id)
    job = JobImportTask(
        user_id=user_id,
        file_name=(file_name or "")[:200],
        source=source,
        status="pending",
        total=max(0, int(total)),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_job(db, job_id: int) -> int:
    """`pending` → `running`，用 rowcount 当凭证；租约让同一行的两次不同 transition 不能都赢。"""
    stamp = utc_now_naive()
    cutoff = stamp - timedelta(minutes=max(1, int(settings.JOB_IMPORT_LEASE_MINUTES)))
    return (
        db.query(JobImportTask)
        .filter(
            JobImportTask.id == job_id,
            JobImportTask.status == "pending",
            (JobImportTask.claimed_at.is_(None)) | (JobImportTask.claimed_at < cutoff),
        )
        .update({JobImportTask.status: "running", JobImportTask.claimed_at: stamp}, synchronize_session=False)
    )


def _is_canceled(db, job_id: int) -> bool:
    """每个进度批次都重读一次状态：取消要能真的停下，而不是等跑完再声明。

    同一条会话里 `db.get` 会命中 identity map，拿不到别人提交的值 —— 必须先 expire。
    """
    db.expire_all()
    row = db.get(JobImportTask, job_id)
    return bool(row) and row.status == "canceled"


def run_job_on(db, job_id: int, rows: list[dict]) -> bool:
    """在**给定会话**上跑完这次导入。返回 False = "我没抢到这一行"，不是失败。

    拆成这一层是因为执行器自己开的 `SessionLocal` 在测试里连的是另一块内存库（本项目有两块，
    见 conftest），夹具数据不在里面；测试要能驱动同一段逻辑，而不是另写一份"看起来一样"的。
    """
    if claim_job(db, job_id) == 0:
        db.commit()
        logger.info("导入作业已被别的线程领走，跳过：%s", job_id)
        return False
    db.commit()

    job = db.get(JobImportTask, job_id)
    if job is None:
        return False

    every = max(1, int(settings.JOB_IMPORT_PROGRESS_EVERY))
    problems: list[dict] = list(job.problems or [])
    created = job.created or 0
    skipped = job.skipped or 0
    done = job.done or 0
    canceled = False

    try:
        for index, item in enumerate(rows):
            if index % every == 0 and _is_canceled(db, job_id):
                canceled = True
                break
            reason = item.get("malformed") or (
                "" if (item.get("title") and item.get("raw_text")) else "缺 title 或 JD 文本"
            )
            done += 1
            if reason:
                skipped += 1
                if len(problems) < settings.JOB_IMPORT_MAX_PROBLEMS:
                    problems.append({"row": item.get("row"), "reason": reason})
                continue
            db.add(
                JobDescription(
                    user_id=job.user_id,
                    title=item["title"],
                    company=item.get("company", ""),
                    location=item.get("location", ""),
                    salary_range=item.get("salary_range", ""),
                    industry=item.get("industry", ""),
                    raw_text=item["raw_text"],
                    source=job.source,
                )
            )
            created += 1
            if index % every == every - 1:
                job.done, job.created, job.skipped, job.problems = done, created, skipped, problems
                db.commit()
        if canceled:
            job.status = "canceled"
            job.error = 0
            job.finished_at = utc_now_naive()
        else:
            job.done, job.created, job.skipped, job.problems = done, created, skipped, problems
            job.status = "completed"
            job.finished_at = utc_now_naive()
            job.claimed_at = None
        db.commit()
        if not canceled and created:
            # 推荐结果带一份进程内缓存，新岗位进来了得让它重算 —— 这一句原先挂在请求里，
            # 作业化之后必须跟着落库这一步走，否则导入完的岗位要等到缓存自然过期才可能出现。
            from app.services.job_recommend_engine import JobRecommendationEngine

            JobRecommendationEngine.clear_cache()
    except Exception as exc:  # noqa: BLE001 - 后台这一跑没人接异常，落库就是它唯一的去处
        logger.exception("导入作业失败：%s", job_id)
        db.rollback()
        job = db.get(JobImportTask, job_id)
        if job is None:
            return False
        job.status = "failed"
        job.error = 1
        job.error_msg = f"{type(exc).__name__}: {str(exc)[:300]}"
        job.done, job.created, job.skipped, job.problems = done, created, skipped, problems
        job.finished_at = utc_now_naive()
        db.commit()
    return True


def submit_job(job_id: int, rows: list[dict]) -> None:
    _get_executor().submit(process_job, job_id, rows)


def process_job(job_id: int, rows: list[dict]) -> bool:
    db = SessionLocal()
    try:
        return run_job_on(db, job_id, rows)
    finally:
        db.close()


def touch_job_for_read(db, job: JobImportTask) -> dict:
    """读的时候把"跑不动了"的行收口：过期的 `running` 判 failed，而不是转圈给候选人看。

    这里不重投（解析结果没在库里，重投也无从跑起），见模块 docstring。
    """
    if job.status in TERMINAL_STATUSES:
        return job.to_progress()
    lease_cutoff = utc_now_naive() - timedelta(minutes=max(1, int(settings.JOB_IMPORT_LEASE_MINUTES)))
    if job.status == "running" and (job.claimed_at is None or job.claimed_at < lease_cutoff):
        job.status = "failed"
        job.error = 1
        job.error_msg = RUNNING_STALE
        job.finished_at = utc_now_naive()
        db.commit()
        db.refresh(job)
    return job.to_progress()


def cancel_job(db, job: JobImportTask) -> dict:
    """取消：`pending`/`running` → `canceled`。已经进去的岗位不回滚。

    不回滚是有意的：一行已经 commit 的岗位就是一次已经发生的写，"取消"能停住剩下的部分，
    不能把别人可能已经看见的数据收回 —— 所以载荷里把"已经成功几行"照实报出来。
    """
    if job.status in TERMINAL_STATUSES:
        return job.to_progress()
    job.status = "canceled"
    job.finished_at = utc_now_naive()
    job.claimed_at = None
    db.commit()
    db.refresh(job)
    return job.to_progress()


def get_owned_job(db, job_id: int, user_id: int) -> JobImportTask | None:
    """按 id 取，**且必须是本人的**——取不到就返回 None，让调用方给 404，不区分"不存在/别人的"。"""
    return db.query(JobImportTask).filter(JobImportTask.id == job_id, JobImportTask.user_id == user_id).first()
