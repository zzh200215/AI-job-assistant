"""单 worker 的排队行为：`REPORT_JOB_MAX_WORKERS=1` 时第二个人到底怎么等。

这条量的是**跑法**不是内容：三发作业一起交进去，
① 池子真的串行（同时起跑的作业数不超过 1），
② 每一发最后都到终态，没有谁被排在队列里饿死，
③ 一个作业内部只被认领一次——重复投递（读路径自愈会重投）不会把它跑第二遍。

为什么写进仓库而不是临时探针：账上那条"一个 worker，第二个人要等一整发报告的时间"
一直是推的，不是量的；而下一次有人把 worker 数抬上去，撞的就是这三条。
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta

import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.history import Resume
from app.models.report_job import ResumeReportJob
from app.models.user import User
from app.services import llm_service, report_job_service, resume_analysis_service, resume_report_service
from app.services import report_job_service as jobs

STAGE_SECONDS = 0.25
_RUNNING: list[str] = []
_PEAK = {"concurrent": 0}
_LOCK = threading.Lock()


@pytest.fixture
def slow_stages(monkeypatch):
    """三支 prompt 各睡 0.25s，一发作业 ≈ 0.75s；返回的仍是仓库自带的 mock 载荷。

    记同时在跑的作业数：`REPORT_JOB_MAX_WORKERS=1` 那句配置只在这里能被验出来，
    光读 `settings` 什么也证不了。
    """
    _RUNNING.clear()
    _PEAK["concurrent"] = 0

    def make(stage):
        def wrapper(prompt, **kwargs):
            with _LOCK:
                _RUNNING.append(stage)
                _PEAK["concurrent"] = max(_PEAK["concurrent"], len(_RUNNING))
            time.sleep(STAGE_SECONDS)
            with _LOCK:
                _RUNNING.remove(stage)
            return llm_service.chat_json(prompt, **kwargs)

        return wrapper

    monkeypatch.setattr(resume_report_service, "chat_json", make("report"))
    monkeypatch.setattr(resume_analysis_service, "chat_json", make("overview"))
    yield


@pytest.fixture
def three_jobs():
    """在 app 引擎那条内存库上建 (用户, 简历, 作业) 三组——线程池自开的就是这条会话。"""
    db = SessionLocal()
    ids: list[int] = []
    user_ids: list[int] = []
    try:
        for tag in range(3):
            user = User(
                username=f"queue_{tag}",
                email=f"queue_{tag}@example.com",
                password=hash_password("StrongP@ssw0rd"),
                role="candidate",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            user_ids.append(user.id)
            resume = Resume(
                name="示例候选人",
                file_name="q.pdf",
                file_path="uploads/q.pdf",
                file_type="pdf",
                file_size=1024,
                user_id=user.id,
                parsed_json=llm_service._MOCK_RESUME,
            )
            db.add(resume)
            db.commit()
            job = jobs.create_report_job(db, user_id=user.id, resume_id=resume.id, jd_id=None, target_position="")
            ids.append(job.id)
        yield ids
    finally:
        db.query(ResumeReportJob).filter(ResumeReportJob.id.in_(ids)).delete(synchronize_session=False)
        db.query(Resume).filter(Resume.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


def _wait_for_terminal(db, job_ids, limit_seconds):
    deadline = time.monotonic() + limit_seconds
    while time.monotonic() < deadline:
        db.expire_all()
        rows = db.query(ResumeReportJob).filter(ResumeReportJob.id.in_(job_ids)).all()
        if all(row.status in report_job_service.TERMINAL_STATUSES for row in rows):
            return rows
        time.sleep(0.05)
    return []


def test_one_worker_serializes_three_jobs_and_all_reach_terminal_state(slow_stages, three_jobs, monkeypatch):
    monkeypatch.setattr(settings, "REPORT_JOB_MAX_WORKERS", 1)
    report_job_service.shutdown_report_job_executor()
    db = SessionLocal()
    started = time.monotonic()
    try:
        for job_id in three_jobs:
            jobs.submit_report_job(job_id)
        rows = _wait_for_terminal(db, three_jobs, limit_seconds=30)

        assert len(rows) == 3, "有作业没跑到终态"
        assert {row.status for row in rows} == {"completed"}
        assert all(row.total_score == 65 for row in rows)
        # 串行：同一时刻起跑的作业不超过一个。
        assert _PEAK["concurrent"] == 1
        # 三发各 ≈0.75s，串行之后墙钟至少是三倍——这是"第二个人等一整发报告"的那句账。
        elapsed = time.monotonic() - started
        assert elapsed >= 3 * 3 * STAGE_SECONDS * 0.6, f"排队没量出来：{elapsed:.2f}s"
    finally:
        db.close()
        report_job_service.shutdown_report_job_executor()


def test_resubmitting_a_running_job_does_not_run_it_twice(slow_stages, three_jobs, monkeypatch):
    """读路径自愈会重投 pending 作业；租约必须保证只有一份在跑。"""
    monkeypatch.setattr(settings, "REPORT_JOB_MAX_WORKERS", 1)
    report_job_service.shutdown_report_job_executor()
    db = SessionLocal()
    try:
        job_id = three_jobs[0]
        jobs.submit_report_job(job_id)
        for _ in range(5):
            jobs.submit_report_job(job_id)  # 与读路径自愈重投同一个形状

        assert _wait_for_terminal(db, [job_id], limit_seconds=30), "重投之后这一发没跑完"
        row = db.get(ResumeReportJob, job_id)
        assert row.status == "completed"
        # 只跑了一发：完成时刻与开始时刻之差落在一发的量级里，不是六发。
        assert row.finished_at - row.create_time < timedelta(seconds=6 * 3 * STAGE_SECONDS)
        assert _PEAK["concurrent"] == 1
    finally:
        db.close()
        report_job_service.shutdown_report_job_executor()
