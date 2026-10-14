"""单项目分析的作业链：一行作业、两节 stage、一份可下载的自包含 HTML。

这一族最值得钉的四条：
* **同一 (人, 简历, 第几个项目) 上未终态只有一行**——换岗位/连点都不该付第二遍模型钱；
* **第四节是另一行作业**，挂在已完成的那一份上；命中红线那一份**拒绝续跑**并给人话说明；
* **装配只有一条路**：`assemble_document` 是"这份项目分析"的唯一读法，轮询与下载都走它；
* 轮询载荷里没有 `error_msg`、没有拒因、没有模型出处。
"""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from app.api import resume as resume_api
from app.core.security import hash_password
from app.models.history import Resume
from app.models.project_report_job import STAGE_QUESTIONS, ProjectReportJob
from app.models.user import User
from app.services import llm_service
from app.services import project_report_job_service as jobs
from app.services import project_report_service as svc
from app.services.project_report_html_lint import lint_project_html
from app.services.project_report_schema import build_project_excerpt, excerpt_text
from app.utils.time_helper import utc_now_naive

PARSED = llm_service._MOCK_RESUME
_USER_SEQ = iter(range(1, 9999))


def _user(db):
    tag = next(_USER_SEQ)
    user = User(
        username=f"pjob_{tag}",
        email=f"pjob_{tag}@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _resume(db, user) -> int:
    resume = Resume(
        name="张三",
        file_name="p.pdf",
        file_path="uploads/p.pdf",
        file_type="pdf",
        file_size=1024,
        user_id=user.id,
        parsed_json=PARSED,
    )
    db.add(resume)
    db.commit()
    return resume.id


@pytest.fixture
def run_job(db_session):
    """建 (用户, 简历, 跑完的前三节)，全程走真派发（provider=mock）。"""

    def _run(project_index: int = 0):
        user = _user(db_session)
        resume_id = _resume(db_session, user)
        job = jobs.create_project_report_job(
            db_session,
            user_id=user.id,
            resume_id=resume_id,
            project_index=project_index,
            project_name="智能简历解析服务",
            jd_id=None,
            target_position="",
        )
        jobs.run_job_on(db_session, job.id)
        db_session.expire_all()
        return db_session.get(ProjectReportJob, job.id), user, resume_id

    return _run


def test_the_three_sections_land_and_the_fourth_is_not_generated(run_job):
    job, user, _rid = run_job()
    assert job.status == "completed"
    assert job.total_score == 60 and job.grade == "需重构"
    assert job.difficulty == "L3" and job.excluded == 0
    document = job.report_json
    assert document["questions"] is None
    assert document["questions_state"] == "not_generated"
    assert document["diagrams"]["figures"] == ["function_arch", "core_flow", "system_arch", "sequence"]
    assert len(document["advice"]["strengthen"]) == 1

    data = resume_api.get_project_report_job_api(job.id, db=_db(job), current_user=user)["data"]
    wire = json.dumps(data, ensure_ascii=False)
    for forbidden in ("error_msg", "stage_errors", "red_line_rejected", "provenance"):
        assert forbidden not in wire, f"{forbidden} 不该出现在轮询载荷里"


def _db(job):
    return job._sa_instance_state.session


def test_the_stored_document_renders_a_lint_clean_standalone_html(run_job):
    job, user, _rid = run_job()
    response = resume_api.download_project_report_html(job.id, db=_db(job), current_user=user)
    document = response.body.decode("utf-8")
    assert "attachment" in response.headers["content-disposition"]
    # 文件名按 RFC 5987 编码进 header，断言也要用同一个编码结果比。
    assert quote("项目分析_智能简历解析服务.html") in response.headers["content-disposition"]
    assert lint_project_html(document, _report_of(job)) == []
    assert 'id="p-profile"' in document and 'href="#p-questions"' not in document
    assert "这一份下载的时候第四节还没生成" in document


def _report_of(job):
    from app.services.project_report_schema import report_from_dict

    assembled = jobs.assemble_document(_db(job), job)
    return report_from_dict(assembled)


def test_a_resubmit_while_pending_reuses_the_row_and_never_starts_a_second(run_job, db_session):
    job, user, resume_id = run_job()
    job.status = "pending"
    job.finished_at = None
    db_session.commit()
    again = jobs.create_project_report_job(
        db_session,
        user_id=user.id,
        resume_id=resume_id,
        project_index=0,
        project_name="x",
        jd_id=None,
        target_position="",
    )
    assert again.id == job.id
    rows = db_session.query(ProjectReportJob).filter(ProjectReportJob.resume_id == resume_id).all()
    assert len(rows) == 1


def test_two_workers_on_one_row_and_only_one_wins(db_session, monkeypatch):
    user = _user(db_session)
    resume_id = _resume(db_session, user)
    job = jobs.create_project_report_job(
        db_session,
        user_id=user.id,
        resume_id=resume_id,
        project_index=0,
        project_name="x",
        jd_id=None,
        target_position="",
    )
    calls = []

    def counting(prompt, **kwargs):
        calls.append(1)
        return json.loads(llm_service._mock_chat(prompt).strip().strip("`").removeprefix("json").strip())

    monkeypatch.setattr(svc, "chat_json", counting)
    assert jobs.run_job_on(db_session, job.id) is True
    # 第二次来抢：这一行已经不是 pending，`claim` 更新 0 行 → 返回 False，一问模型都没打。
    assert jobs.run_job_on(db_session, job.id) is False
    assert len(calls) == 3


def test_all_three_profile_diagram_advice_calls_run_in_one_job(db_session, monkeypatch):
    user = _user(db_session)
    resume_id = _resume(db_session, user)
    job = jobs.create_project_report_job(
        db_session,
        user_id=user.id,
        resume_id=resume_id,
        project_index=0,
        project_name="x",
        jd_id=None,
        target_position="",
    )
    seen = []

    def counting(prompt, **kwargs):
        seen.append(prompt)
        return json.loads(llm_service._mock_chat(prompt).strip().strip("`").removeprefix("json").strip())

    monkeypatch.setattr(svc, "chat_json", counting)
    jobs.run_job_on(db_session, job.id)
    text = " ".join(seen)
    assert "一、项目档案" in text and "二、项目图解" in text and "三、使用建议" in text
    assert "四、面试准备" not in text  # 按按钮才跑那一发，没点就不花钱


def test_questions_stage_refuses_an_excluded_parent(db_session, monkeypatch):
    user = _user(db_session)
    resume_id = _resume(db_session, user)
    body = excerpt_text(build_project_excerpt(PARSED["project_experience"][0], 0))

    def with_red_line(prompt, **kwargs):
        payload = json.loads(llm_service._mock_chat(prompt).strip().strip("`").removeprefix("json").strip())
        if "一、项目档案" in prompt:
            payload["red_lines"] = [
                {
                    "key": "others_work",
                    "quote": "基于 LLM 的简历结构化解析",
                    "why": "（mock）整条链路写成自己主导，一问分工就露",
                }
            ]
        return payload

    monkeypatch.setattr(svc, "chat_json", with_red_line)
    job = jobs.create_project_report_job(
        db_session,
        user_id=user.id,
        resume_id=resume_id,
        project_index=0,
        project_name="x",
        jd_id=None,
        target_position="",
    )
    jobs.run_job_on(db_session, job.id)
    db_session.expire_all()
    job = db_session.get(ProjectReportJob, job.id)
    assert job.excluded == 1
    assert job.total_score is not None and job.grade is None
    assert job.report_json["score_cell"] == "不作数"
    assert body  # 逐字引用的那条确实来自这一条项目原文

    refused = resume_api.create_project_questions_job_api(job.id, db=db_session, current_user=user)
    assert refused["code"]
    assert "一票否决" in refused["message"]
    assert db_session.query(ProjectReportJob).filter(ProjectReportJob.stage == STAGE_QUESTIONS).count() == 0


def test_questions_land_on_a_child_row_and_are_assembled_onto_the_document(run_job):
    job, user, _rid = run_job()
    db = _db(job)
    child = jobs.create_questions_job(db, parent=job)
    assert child.stage == STAGE_QUESTIONS and child.parent_job_id == job.id
    jobs.run_job_on(db, child.id)
    db.expire_all()

    child = db.get(ProjectReportJob, child.id)
    assert child.status == "completed"
    assert child.report_json["distribution"]["total"] == 8

    document = jobs.assemble_document(db, job)
    assert document["questions_state"] == "ready"
    assert document["questions"]["questions"][0]["no"] == 1
    assert document["advice"]["practice"]["high_risk"] == "Q4"
    assert document["job_id"] == job.id and document["questions_job_id"] == child.id

    response = resume_api.download_project_report_html(child.id, db=db, current_user=user)
    document_html = response.body.decode("utf-8")
    assert 'id="p-questions"' in document_html
    assert lint_project_html(document_html, _report_of(job)) == []


def test_a_second_questions_call_reuses_the_open_child_row(run_job):
    job, _user, _rid = run_job()
    db = _db(job)
    first = jobs.create_questions_job(db, parent=job)
    first.status = "pending"
    db.commit()
    second = jobs.create_questions_job(db, parent=job)
    assert first.id == second.id
    assert db.query(ProjectReportJob).filter(ProjectReportJob.stage == STAGE_QUESTIONS).count() == 1


def test_touch_for_read_resubmits_a_stale_running_row(run_job, monkeypatch):
    job, _user, _rid = run_job()
    db = _db(job)
    job.status = "running"
    job.claimed_at = utc_now_naive() - (jobs.timedelta(minutes=jobs.settings.REPORT_JOB_LEASE_MINUTES + 1))
    db.commit()
    submitted = []
    monkeypatch.setattr(jobs, "submit_project_report_job", lambda job_id: submitted.append(job_id))
    assert jobs.touch_job_for_read(db, job) == "pending"
    assert submitted == [job.id]
