"""D200: the background job behind rewrite suggestions — claim, reuse, recovery, and the one
invariant that must survive the change ("a suggestion never rewrites my CV").

Why these legs exist rather than "the endpoint returns 200": the sync endpoint was replaced by a
row plus a thread pool, and everything that used to be guaranteed by the request/response being
one atomic act is now guaranteed (or not) by this table. Each test below is a claim the old shape
got for free and the new one has to earn.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import resume as resume_api
from app.api.auth import get_current_user
from app.api.resume import router as resume_router
from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.models.history import JobDescription, Resume, ResumeVersion
from app.models.rewrite_job import RewriteSuggestionJob
from app.models.user import User
from app.services import resume_rewrite_service as svc
from app.services import rewrite_job_service as job_service
from app.services.match_score_service import resume_version_of
from app.utils.time_helper import utc_now_naive

PARSED = {
    "name": "张三",
    "skills": ["Python", "FastAPI"],
    "self_evaluation": "三年后端开发经验",
    "work_experience": [
        {"company": "A 公司", "title": "后端工程师", "start": "2021-03", "end": "至今", "desc": "负责订单服务"}
    ],
    "project_experience": [{"name": "下单系统", "desc": "自研秒杀模块"}],
}


@pytest.fixture
def actor(db_session):
    user = User(
        username="job_user", email="job_user@example.com", password=hash_password("StrongP@ssw0rd"), role="candidate"
    )
    other = User(
        username="job_other", email="job_other@example.com", password=hash_password("StrongP@ssw0rd"), role="candidate"
    )
    db_session.add_all([user, other])
    db_session.commit()
    return user, other


def _resume(db, user, parsed=None):
    row = Resume(
        user_id=user.id,
        name="作业验证简历",
        file_name="job.pdf",
        file_path="uploads/job.pdf",
        file_type="pdf",
        file_size=2048,
        parsed_json=parsed if parsed is not None else dict(PARSED),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _job(db, user):
    row = JobDescription(
        user_id=user.id,
        title="高级后端工程师",
        company="示例公司",
        raw_text="高级后端工程师",
        parsed_json={"title": "高级后端工程师", "required_skills": ["Python"]},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _good_suggestion(
    block_id="self_evaluation", original="三年后端开发经验", proposed="三年后端开发经验，专注订单链路"
):
    return {"block_id": block_id, "original": original, "proposed_text": proposed, "reason": "把已有事实写清楚"}


def _client(db, user):
    app = FastAPI()
    app.include_router(resume_router, prefix="/resume")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_submitting_does_not_call_the_model(db_session, actor, monkeypatch):
    """这条是整个改造的立论点：**POST 那一趟不许碰模型**。

    以前它是同步的，一次点击 = 一次 4.5–90 秒的等待；现在 POST 只落一行、投一次池。
    """
    user, _ = actor
    resume = _resume(db_session, user)
    calls = []
    monkeypatch.setattr(svc, "chat_json", lambda prompt, **kw: calls.append(prompt) or {"suggestions": []})
    submitted = []
    # 端点里那个名字是 import 进来的，打桩要打**它所在的那个模块**，打服务模块是打空枪。
    monkeypatch.setattr(resume_api, "submit_rewrite_job", lambda job_id: submitted.append(job_id))

    with TestClient(_client(db_session, user)) as client:
        body = client.post(f"/resume/{resume.id}/rewrite-suggestion-jobs", json={}).json()

    assert body["code"] == 0
    assert body["data"]["status"] == "pending"
    assert calls == [], "POST 这一趟碰了模型，异步就只是换了个 URL"
    assert len(submitted) == 1


def test_a_second_claim_of_the_same_row_loses(db_session, actor, monkeypatch):
    """同一行只能有一个赢家——`pending→running` 与 `running→pending` 是两条 transition，
    只看 status 会让两个扫描者各领一条（D177 在真 MySQL + 8 进程上量到过）。"""
    user, _ = actor
    resume = _resume(db_session, user)
    calls = []
    monkeypatch.setattr(
        svc, "chat_json", lambda prompt, **kw: calls.append(prompt) or {"suggestions": [_good_suggestion()]}
    )
    job = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None)

    assert job_service.run_job_on(db_session, job.id) is True
    assert job_service.run_job_on(db_session, job.id) is False
    assert len(calls) == 1, "第二次领到了同一行 ⇒ 同一次改写付了两遍模型钱"


def test_double_submit_reuses_the_unfinished_row(db_session, actor):
    user, _ = actor
    resume = _resume(db_session, user)

    first = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None)
    second = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None)

    assert first.id == second.id
    assert db_session.query(RewriteSuggestionJob).count() == 1


def test_a_different_target_job_is_not_reused(db_session, actor):
    user, _ = actor
    resume = _resume(db_session, user)
    other_job = _job(db_session, user)

    plain = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None)
    targeted = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=other_job.id)

    assert plain.id != targeted.id


def test_a_fresh_lease_blocks_reclaim_and_an_expired_one_does_not(db_session, actor):
    """claim 只认 `pending`——把过期 `running` 退回 pending 是读路径那条恢复干的（下面另测）。
    所以这里两种情况都从 pending 起步，差的只有租约年龄。"""
    user, _ = actor
    resume = _resume(db_session, user)
    job = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None)

    job.status = "pending"
    job.claimed_at = utc_now_naive()
    db_session.commit()
    assert job_service.claim_rewrite_job(db_session, job.id) == 0, "租约内就能重领 ⇒ 同一次改写付两遍模型钱"
    db_session.rollback()

    job = db_session.get(RewriteSuggestionJob, job.id)
    job.claimed_at = utc_now_naive() - timedelta(minutes=settings.REWRITE_JOB_LEASE_MINUTES + 1)
    db_session.commit()
    assert job_service.claim_rewrite_job(db_session, job.id) == 1


def test_a_stale_running_row_goes_back_to_pending_on_read(db_session, actor, monkeypatch):
    """进程死在半路的恢复：读路径把它退回 pending 并补投。没有调度任务，靠的是"候选人一定会来读"。"""
    user, _ = actor
    resume = _resume(db_session, user)
    job = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None)
    resubmitted = []
    monkeypatch.setattr(job_service, "submit_rewrite_job", lambda job_id: resubmitted.append(job_id))

    job.status = "running"
    job.claimed_at = utc_now_naive() - timedelta(minutes=settings.REWRITE_JOB_LEASE_MINUTES + 1)
    db_session.commit()

    assert job_service.touch_job_for_read(db_session, job) == "pending"
    assert resubmitted == [job.id]

    resubmitted.clear()
    job.status = "running"
    job.claimed_at = utc_now_naive()
    db_session.commit()
    assert job_service.touch_job_for_read(db_session, job) == "running"
    assert resubmitted == [], "还在租约内的 running 被重投 = 同一发模型钱付两遍"


def test_failure_is_recorded_internally_but_not_put_on_the_wire(db_session, actor, monkeypatch):
    """失败原因留在库里给排障用；轮询载荷里不许有它——那句可能带模型返回的内容。
    同一理由写在 `llm_service.py:1097` 的注释上。"""
    user, _ = actor
    resume = _resume(db_session, user)

    def boom(prompt, **kw):
        raise RuntimeError("模型回了一段带候选人原文的话")

    monkeypatch.setattr(svc, "chat_json", boom)
    job = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None)

    assert job_service.run_job_on(db_session, job.id) is True

    fresh = db_session.get(RewriteSuggestionJob, job.id)
    assert fresh.status == "failed"
    assert fresh.error == 1
    assert "候选人原文" in (fresh.error_msg or "")
    payload = job_service.serialize_job(fresh)
    assert "error_msg" not in json.dumps(payload, ensure_ascii=False)
    assert payload["status"] == "failed"


def test_a_finished_job_never_touches_the_resume(db_session, actor, monkeypatch):
    """D193 说这条不变量是 ③ 唯一的拦路石，那就把它在新形状下重新钉一遍：
    建议现在**存在**另一张表里了，但"不落进简历"这半句必须一个字都没松。"""
    user, _ = actor
    resume = _resume(db_session, user)
    before_parsed = json.dumps(resume.parsed_json, ensure_ascii=False, sort_keys=True)
    # 版本用仓库自己那把算式（`resume_version_of`），不另写一份"看起来一样"的哈希配方——
    # 这正是 D164 那条"判据只有一份"的老毛病。
    before_version = resume_version_of(resume)
    before_update = resume.update_time
    monkeypatch.setattr(svc, "chat_json", lambda prompt, **kw: {"suggestions": [_good_suggestion()]})
    job = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None)

    assert job_service.run_job_on(db_session, job.id) is True

    db_session.expire_all()
    after = db_session.get(Resume, resume.id)
    assert json.dumps(after.parsed_json, ensure_ascii=False, sort_keys=True) == before_parsed
    assert resume_version_of(after) == before_version
    assert after.update_time == before_update
    assert db_session.query(ResumeVersion).count() == 0
    # 而建议确实存在作业行里——"没写简历"不等于"什么都没发生"，否则这条守卫是空的。
    stored = db_session.get(RewriteSuggestionJob, job.id)
    assert len(stored.suggestions) == 1


def test_purge_removes_only_finished_and_expired_rows(db_session, actor):
    """清理的三条边界各压一次：**过期且终态**才删。

    两阶段是因为 `_purge_expired` 挂在每次提交上——第一版夹具想让一行"过期已完成"活着等到
    我数它，结果它在下一次 create 时就被清掉了，于是断言变成"1 == 2"。那不是产品错，
    是我把清理的时机猜反了。行与行之间用**不同简历**区分：SQLite 那块库的主键是 rowid 别名，
    删掉的 id 会被下一次插入复用，拿 id 当身份会得出假结论。
    """
    user, _ = actor
    retention = timedelta(days=settings.REWRITE_JOB_RETENTION_DAYS)
    stale = job_service.create_rewrite_job(
        db_session, user_id=user.id, resume_id=_resume(db_session, user).id, jd_id=None
    )
    stale.status = "completed"
    stale.finished_at = utc_now_naive() - retention - timedelta(days=1)
    db_session.commit()

    # 阶段一：下一发提交应当顺手清掉那一行；同一个人那份**未终态**的旧作业不许被清。
    waiting = job_service.create_rewrite_job(
        db_session, user_id=user.id, resume_id=_resume(db_session, user).id, jd_id=None
    )
    waiting.create_time = utc_now_naive() - retention - timedelta(days=1)
    db_session.commit()
    surviving = db_session.query(RewriteSuggestionJob).all()
    assert [r.id for r in surviving] == [waiting.id], "该删的没删，或不该删的被删了"

    # 阶段二：`completed` 但仍在保留期内的，下一次提交也不许动它——否则"过期"这半句就是装饰。
    fresh = job_service.create_rewrite_job(
        db_session, user_id=user.id, resume_id=_resume(db_session, user).id, jd_id=None
    )
    fresh.status = "completed"
    fresh.finished_at = utc_now_naive()
    db_session.commit()
    job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=_resume(db_session, user).id, jd_id=None)

    assert db_session.query(RewriteSuggestionJob).count() == 3


def test_another_users_resume_and_job_are_both_refused(db_session, actor, monkeypatch):
    user, other = actor
    resume = _resume(db_session, user)
    monkeypatch.setattr(svc, "chat_json", lambda prompt, **kw: {"suggestions": []})
    mine = job_service.create_rewrite_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None)

    with TestClient(_client(db_session, other)) as client:
        foreign_submit = client.post(f"/resume/{resume.id}/rewrite-suggestion-jobs", json={}).json()
        foreign_poll = client.get(f"/resume/rewrite-suggestion-jobs/{mine.id}").json()

    assert foreign_submit["code"] != 0
    assert foreign_poll["code"] != 0
    assert db_session.query(RewriteSuggestionJob).count() == 1, "别人的提交也建了行 ⇒ 表能被外人灌大"


def test_the_pool_is_sized_from_settings_and_rebuilt_after_shutdown(monkeypatch):
    """线程数不能硬编码：它和连接池是同一个算式的两头（`threadpool.py` 把 HTTP 那侧钉在 10+10）。"""
    monkeypatch.setattr(settings, "REWRITE_JOB_MAX_WORKERS", 3)
    monkeypatch.setattr(job_service, "_executor", None)
    try:
        assert job_service._get_executor()._max_workers == 3
    finally:
        job_service.shutdown_rewrite_job_executor()
    assert job_service._executor is None
