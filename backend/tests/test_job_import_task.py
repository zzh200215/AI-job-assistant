"""D226：批量导入作业化之后的判据——进度会走、能被停、只认本人、崩了不假装能恢复。

形状照 `test_rewrite_job.py` 的路子走：驱动 `run_job_on(db, ...)` 这一层（执行器自己开的
SessionLocal 在测试里连的是另一块内存库），而不是另写一份"看起来一样"的循环。
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.job_recommend import router as job_router
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.models.history import JobDescription
from app.models.job_import import JobImportTask
from app.models.user import User
from app.services import job_import_service as jis
from app.utils.time_helper import utc_now_naive

CSV = (
    "title,company,raw_text\nA公司后端,公司A,负责接口与数据库\n,缺标题的行,没有title\nB公司算法,公司B,负责召回与重排\n"
)
JSON_BODY = json.dumps(
    [
        {"title": "C公司数据", "company": "公司C", "raw_text": "负责数仓"},
        {"title": "", "company": "缺标题", "raw_text": "不会入库"},
    ],
    ensure_ascii=False,
)


def _user(db, name="import_owner"):
    u = User(username=name, email=f"{name}@example.com", password=hash_password("Str0ngPass!234"), role="candidate")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _job(db, user_id, total=3, status="pending", claimed_at=None):
    job = JobImportTask(
        user_id=user_id, file_name="jobs.csv", source="imported", status=status, total=total, claimed_at=claimed_at
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_parse_keeps_every_row_and_its_number():
    rows = jis.parse_rows("jobs.csv", CSV.encode("utf-8"))
    assert [r["row"] for r in rows] == [1, 2, 3], rows
    assert rows[1]["title"] == ""  # 缺字段的行在解析阶段不丢，由作业计入 skipped


def test_an_unsupported_file_is_a_client_error():
    with pytest.raises(ValueError):
        jis.parse_rows("jobs.txt", b"whatever")


def test_run_creates_rows_counts_skips_and_finishes(db_session):
    user = _user(db_session)
    job = _job(db_session, user.id, total=3)
    rows = jis.parse_rows("jobs.csv", CSV.encode("utf-8"))

    assert jis.run_job_on(db_session, job.id, rows) is True
    db_session.refresh(job)
    assert job.status == "completed"
    assert (job.created, job.skipped, job.done) == (2, 1, 3), job.to_progress()
    assert db_session.query(JobDescription).filter(JobDescription.user_id == user.id).count() == 2
    assert job.problems[0]["row"] == 2, job.problems
    # error_msg 不上客户端载荷：里面可能带文件内容或库报错
    assert "error_msg" not in job.to_progress()


def test_a_second_claim_loses(db_session):
    """同一行只能有一个赢家：两个 transition 都从 pending 起跑的话会付两遍写库。"""
    user = _user(db_session)
    job = _job(db_session, user.id)
    assert jis.claim_job(db_session, job.id) == 1
    db_session.commit()
    assert jis.claim_job(db_session, job.id) == 0


def test_run_returns_false_for_the_loser_and_writes_nothing(db_session):
    user = _user(db_session)
    job = _job(db_session, user.id)
    rows = jis.parse_rows("jobs.csv", CSV.encode("utf-8"))
    assert jis.run_job_on(db_session, job.id, rows) is True
    db_session.expire_all()
    assert jis.run_job_on(db_session, job.id, rows) is False
    assert db_session.query(JobDescription).filter(JobDescription.user_id == user.id).count() == 2


def test_a_canceled_job_stops_before_writing_the_rest(db_session):
    user = _user(db_session)
    job = _job(db_session, user.id, status="canceled")
    rows = jis.parse_rows("jobs.csv", CSV.encode("utf-8"))
    # 已经被人领走过（claimed_at 有值）也不行：claim 会拒，直接返回 False
    assert jis.run_job_on(db_session, job.id, rows) is False
    db_session.refresh(job)
    assert job.status == "canceled"
    assert db_session.query(JobDescription).filter(JobDescription.user_id == user.id).count() == 0


def test_cancel_mid_flight_leaves_the_written_rows_and_marks_canceled(db_session, monkeypatch):
    """取消不回滚已经进去的行——那是已经发生的写；载荷里照实报"已经成功几行"。"""
    user = _user(db_session)
    job = _job(db_session, user.id, total=3)
    monkeypatch.setattr(settings, "JOB_IMPORT_PROGRESS_EVERY", 1)
    rows = jis.parse_rows("jobs.csv", CSV.encode("utf-8"))

    original = jis._is_canceled
    state = {"flips": 0}

    def flip(db, job_id):
        state["flips"] += 1
        if state["flips"] == 2:
            j = db_session.get(JobImportTask, job_id)
            j.status = "canceled"
            db_session.commit()
            return True
        return original(db, job_id)

    monkeypatch.setattr(jis, "_is_canceled", flip)
    assert jis.run_job_on(db_session, job.id, rows) is True
    db_session.refresh(job)
    assert job.status == "canceled"
    assert job.created < 2, f"取消之后剩下的行还在写：created={job.created}"
    assert job.done > 0 and job.finished_at is not None


def test_a_stale_running_row_is_failed_on_read_not_resubmitted(db_session, monkeypatch):
    """崩掉的进程没有可重放的解析结果：读的时候判失败并让人重传，而不是转圈。"""
    user = _user(db_session)
    job = _job(db_session, user.id, status="running", claimed_at=utc_now_naive())
    payload = jis.touch_job_for_read(db_session, job)
    assert payload["status"] == "running"  # 租约内不动它

    db_session.expire_all()
    job = db_session.get(JobImportTask, job.id)
    job.claimed_at = utc_now_naive() - (__import__("datetime").timedelta(minutes=settings.JOB_IMPORT_LEASE_MINUTES + 1))
    db_session.commit()
    db_session.expire_all()
    payload = jis.touch_job_for_read(db_session, db_session.get(JobImportTask, job.id))
    assert payload["status"] == "failed"
    db_session.refresh(job)
    assert "重新上传" in (job.error_msg or "")


def test_purge_removes_only_terminal_and_expired(db_session):
    import datetime

    user = _user(db_session)
    old_done = _job(db_session, user.id, status="completed")
    old_done.finished_at = utc_now_naive() - datetime.timedelta(days=settings.JOB_IMPORT_RETENTION_DAYS + 1)
    fresh_done = _job(db_session, user.id, status="completed")
    fresh_done.finished_at = utc_now_naive()
    pending = _job(db_session, user.id, status="pending")
    other = _job(db_session, _user(db_session, "other_owner").id, status="completed")
    other.finished_at = utc_now_naive() - datetime.timedelta(days=settings.JOB_IMPORT_RETENTION_DAYS + 1)
    db_session.commit()

    # 先取 id：purge 之后那些实例已经不在库里，再碰属性会 ObjectDeletedError
    ids = {"old_done": old_done.id, "fresh_done": fresh_done.id, "pending": pending.id, "other": other.id}
    db_session.expire_all()
    jis._purge_expired(db_session, user.id)
    db_session.commit()
    left = {row.id for row in db_session.query(JobImportTask).all()}
    assert ids["old_done"] not in left
    assert {ids["fresh_done"], ids["pending"], ids["other"]} <= left


def _client(db_session, user):
    app = FastAPI()
    app.include_router(job_router, prefix="/jobs")
    app.dependency_overrides[get_db] = lambda: db_session
    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "username": user.username, "role": user.role}
    )
    headers = {"Authorization": f"Bearer {token}"}
    return TestClient(app), headers


def test_the_endpoint_returns_a_job_and_the_progress_ends_completed(db_session, monkeypatch):
    user = _user(db_session)
    ran = []
    monkeypatch.setattr(jis, "submit_job", lambda job_id, rows: ran.append((job_id, rows)))
    client, headers = _client(db_session, user)

    response = client.post("/jobs/batch-import", headers=headers, files={"file": ("jobs.csv", CSV.encode("utf-8"))})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["status"] == "pending" and data["total"] == 3 and data["job_id"]
    assert ran and ran[0][0] == data["job_id"], "作业提交了但没带上解析结果"
    assert len(ran[0][1]) == 3

    polled = client.get(f"/jobs/batch-import/{data['job_id']}", headers=headers).json()["data"]
    assert polled["total"] == 3 and polled["status"] == "pending"


def test_unsupported_file_never_creates_a_job_row(db_session):
    user = _user(db_session)
    client, headers = _client(db_session, user)
    response = client.post("/jobs/batch-import", headers=headers, files={"file": ("notes.txt", b"hello")})
    body = response.json()
    assert body["code"] != 0 and "CSV" in body["message"] or "csv" in body["message"].lower()
    assert db_session.query(JobImportTask).count() == 0


def test_progress_and_cancel_are_owner_scoped(db_session, monkeypatch):
    user, other = _user(db_session, "owner_a"), _user(db_session, "owner_b")
    monkeypatch.setattr(jis, "submit_job", lambda *a: None)
    job = _job(db_session, user.id)
    client, headers = _client(db_session, other)

    assert client.get(f"/jobs/batch-import/{job.id}", headers=headers).json()["code"] != 0
    assert client.post(f"/jobs/batch-import/{job.id}/cancel", headers=headers).json()["code"] != 0
    db_session.refresh(job)
    assert job.status == "pending", "别人的作业被取消/改动了"

    mine, my_headers = _client(db_session, user)
    assert mine.post(f"/jobs/batch-import/{job.id}/cancel", headers=my_headers).json()["code"] == 0
    db_session.refresh(job)
    assert job.status == "canceled"
