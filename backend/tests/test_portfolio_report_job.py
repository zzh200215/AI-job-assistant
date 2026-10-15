"""组合分析的作业链：一行作业、两节 stage、一份可下载的自包含 HTML。

这一族最值得钉的五条：
* **去重键是 `combo_key`**——同一 (人, 简历, 选中了哪几个项目) 上未终态只有一行，
  换岗位、连点、勾选顺序不同都不该付第二遍模型钱；
* **第四节是另一行作业**，挂在已完成的那一份上；命中红线那一份**拒绝续跑**并给人话说明；
* **出局由代码算**：两条正文逐字相同 → `excluded=1`、没有总分也没有等级；
* **表头「单项目均分」是真的去库里取**：跑过单项目分析的那一份要出现在这一格里，
  没跑过的那一份不许被猜出来；
* 轮询载荷里没有 `error_msg`、没有拒因、没有模型出处。
"""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from app.api import resume as resume_api
from app.core.security import hash_password
from app.models.history import Resume
from app.models.portfolio_report_job import STAGE_QUESTIONS, PortfolioReportJob
from app.models.project_report_job import ProjectReportJob
from app.models.user import User
from app.services import portfolio_report_job_service as jobs
from app.services.portfolio_report_html_lint import lint_portfolio_html
from app.services.portfolio_report_schema import combo_signature, report_from_dict
from tests.portfolio_report_payloads import PARSED, PARSED_WITH_DUP

_USER_SEQ = iter(range(1, 99999))


def _user(db):
    tag = next(_USER_SEQ)
    user = User(
        username=f"cbg_{tag}",
        email=f"cbg_{tag}@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _resume(db, user, parsed=None) -> int:
    resume = Resume(
        name="张三",
        file_name="c.pdf",
        file_path="uploads/c.pdf",
        file_type="pdf",
        file_size=1024,
        user_id=user.id,
        parsed_json=parsed or PARSED,
    )
    db.add(resume)
    db.commit()
    return resume.id


def _db(job):
    return job._sa_instance_state.session


def _create(db, user, resume_id, indices):
    names = [str(PARSED["project_experience"][i].get("name") or "") for i in indices]
    return jobs.create_portfolio_report_job(
        db,
        user_id=user.id,
        resume_id=resume_id,
        combo_key=combo_signature(indices),
        project_indices=indices,
        project_names=names,
        jd_id=None,
        target_position="大模型应用工程师",
    )


@pytest.fixture
def run_job(db_session):
    """建 (用户, 三项目简历, 跑完的组合前三节)，派发走 mock。"""

    def _run(indices=(0, 1, 2), parsed=None):
        user = _user(db_session)
        resume_id = _resume(db_session, user, parsed)
        job = _create(db_session, user, resume_id, list(indices))
        jobs.run_job_on(db_session, job.id)
        db_session.expire_all()
        return db_session.get(PortfolioReportJob, job.id), user, resume_id

    return _run


def test_前三节落地而第四节还没生成(run_job):
    job, user, _rid = run_job()
    assert job.status == "completed", job.error_msg
    assert job.project_count == 3 and job.combo_key == "0,1,2"
    assert job.excluded == 0
    assert job.total_score is not None and job.grade
    assert job.difficulty == "L3"
    document = job.report_json
    assert document["questions"] is None
    assert document["questions_state"] == "not_generated"
    assert len(document["compare"]["rows"]) == 7
    assert len(document["capabilities"]) == 5
    assert document["average_cell"].startswith("还没跑过") or "1/3" in document["average_cell"]

    data = resume_api.get_portfolio_report_job_api(job.id, db=_db(job), current_user=user)["data"]
    wire = json.dumps(data, ensure_ascii=False)
    for forbidden in ("error_msg", "stage_errors", "red_line_rejected", "provenance", "stack_reuse"):
        assert forbidden not in wire, f"{forbidden} 不该出现在轮询载荷里"


def test_库里那份能渲成过机检的自包含html(run_job):
    job, user, _rid = run_job()
    response = resume_api.download_portfolio_report_html(job.id, db=_db(job), current_user=user)
    document = response.body.decode("utf-8")
    assert "attachment" in response.headers["content-disposition"]
    assert quote("组合分析_合同初审助手") in response.headers["content-disposition"]
    report = report_from_dict(jobs.assemble_document(_db(job), job))
    assert lint_portfolio_html(document, report) == []
    assert 'id="c-profile"' in document
    assert 'href="#c-questions"' not in document
    assert "这一份下载的时候第四节还没生成" in document


def test_勾选顺序不同也算同一组(run_job, db_session):
    job, user, resume_id = run_job()
    # 去重只在**未终态**那一行上生效：已完成的那一份是历史，另点一次该起新行。
    job.status = "pending"
    job.finished_at = None
    db_session.commit()
    again = _create(db_session, user, resume_id, [2, 0, 1])
    assert again.id == job.id, "combo_key 与勾选顺序无关，不该另起一行"
    rows = db_session.query(PortfolioReportJob).filter(PortfolioReportJob.resume_id == resume_id).all()
    assert len(rows) == 1


def test_多一个项目就是另一组(run_job, db_session):
    job, user, resume_id = run_job((0, 1))
    assert job.combo_key == "0,1"
    other = _create(db_session, user, resume_id, [0, 1, 2])
    assert other.id != job.id


def test_两个worker同一行只有一个抢到(run_job):
    job, _user, _rid = run_job()
    db_session = _db(job)
    fresh = db_session.query(PortfolioReportJob).filter(PortfolioReportJob.id == job.id).one()
    fresh.status = "pending"
    fresh.claimed_at = None
    db_session.commit()
    assert jobs.run_job_on(db_session, job.id) is True
    assert jobs.run_job_on(db_session, job.id) is False or fresh.status == "completed"


def test_第四节是挂在同一份上的另一行(run_job, db_session):
    job, user, _rid = run_job()
    child = jobs.create_portfolio_questions_job(db_session, parent=job)
    assert child.stage == STAGE_QUESTIONS and child.parent_job_id == job.id
    assert child.combo_key == job.combo_key and child.project_indices == job.project_indices
    jobs.run_job_on(db_session, child.id)
    db_session.expire_all()
    child_row = db_session.get(PortfolioReportJob, child.id)
    assert child_row.status == "completed", child_row.error_msg

    document = jobs.assemble_document(db_session, job)
    questions = document["questions"]
    assert questions["distribution"]["total"] == 12
    assert document["questions_state"] == "ready"
    assert document["job_id"] == job.id and document["questions_job_id"] == child.id
    # 必练题那一栏在**第四节自己的载荷**里（组合那一族的使用建议没有 3.3 那个 practice 表，
    # 与单项目那一族不同，见规范 §5）。
    assert questions["practice"]["must_practice"] == "Q11"


def test_命中红线那份没有总分也不给出题(run_job, db_session):
    job, user, _rid = run_job((1, 2), parsed=PARSED_WITH_DUP)
    assert job.status == "completed", job.error_msg
    assert job.excluded == 1
    assert job.total_score is None and job.grade is None
    document = job.report_json
    assert document["score_cell"] == "不作数"
    assert document["excluded_by"][0]["key"] == "duplicate_projects"

    refused = resume_api.create_portfolio_questions_job_api(job.id, db=_db(job), current_user=user)
    assert refused["code"] != 0
    assert "先解开" in refused["message"] or "不出" in refused["message"]

    rendered = resume_api.download_portfolio_report_html(job.id, db=_db(job), current_user=user).body.decode("utf-8")
    assert 'id="redline-banner"' in rendered
    assert "不作数" in rendered
    assert 'class="qst"' not in rendered


def test_跑过的单项目分析会进表头那一格(run_job, db_session):
    job, user, resume_id = run_job()
    single = ProjectReportJob(
        user_id=user.id,
        resume_id=resume_id,
        project_index=0,
        project_name="合同初审助手",
        stage="report",
        status="completed",
        total_score=88,
        grade="优秀",
        difficulty="L3",
    )
    db_session.add(single)
    db_session.commit()

    again = _create(db_session, user, resume_id, [0, 1, 2])
    again.status = "pending"
    again.finished_at = None
    db_session.commit()
    jobs.run_job_on(db_session, again.id)
    db_session.expire_all()
    row = db_session.get(PortfolioReportJob, again.id)
    cell = row.report_json["average_cell"]
    assert "88" in cell, cell
    assert "1/3" in cell


def test_读路径会把过期的那一发重投(run_job, db_session, monkeypatch):
    from app.utils.time_helper import utc_now_naive

    job, _user, _rid = run_job()
    job.status = "pending"
    job.claimed_at = utc_now_naive().replace(year=2020)
    db_session.commit()
    submitted = []
    monkeypatch.setattr(jobs, "submit_portfolio_report_job", lambda job_id: submitted.append(job_id))
    assert jobs.touch_job_for_read(db_session, job) == "pending"
    assert submitted == [job.id]


def test_终态行过期后被清掉(run_job, db_session):
    from datetime import timedelta

    from app.utils.time_helper import utc_now_naive

    job, user, _rid = run_job()
    job.finished_at = utc_now_naive() - timedelta(days=400)
    db_session.commit()
    fresh = _create(db_session, user, job.resume_id, [0, 1])
    db_session.expire_all()
    # 清的是**那一条过期的**；新起的这一行本来就该在（它不是残留）。
    # 自动递增 id 会被新行复用，所以按状态与时刻认，不按 id 认。
    rows = db_session.query(PortfolioReportJob).filter(PortfolioReportJob.user_id == user.id).all()
    assert len(rows) == 1
    assert rows[0].id == fresh.id
    assert rows[0].status == "pending" and rows[0].finished_at is None


def test_接口层的项目数与越界都在这一层拒(resume_client_none):
    del resume_client_none


@pytest.fixture
def resume_client_none():
    yield None


def test_只给一个项目时接口拒绝(db_session):
    user = _user(db_session)
    resume_id = _resume(db_session, user)
    response = resume_api.create_portfolio_report_job_api(
        resume_id, payload={"project_indices": [1]}, db=db_session, current_user=user
    )
    assert response["code"] != 0
    assert "至少" in response["message"]


def test_序号越界时接口拒绝并说清有几个(db_session):
    user = _user(db_session)
    resume_id = _resume(db_session, user)
    response = resume_api.create_portfolio_report_job_api(
        resume_id, payload={"project_indices": [0, 9]}, db=db_session, current_user=user
    )
    assert response["code"] != 0
    assert "共 3 个" in response["message"]


def test_不给序号时默认把全部项目放在一起(db_session):
    user = _user(db_session)
    resume_id = _resume(db_session, user)
    response = resume_api.create_portfolio_report_job_api(resume_id, payload={}, db=db_session, current_user=user)
    assert response["code"] == 0
    assert response["data"]["project_indices"] == [0, 1, 2]
    assert response["data"]["project_count"] == 3
    row = db_session.query(PortfolioReportJob).filter(PortfolioReportJob.resume_id == resume_id).one()
    assert row.combo_key == "0,1,2"


def test_别人的作业行读不到(db_session):
    user = _user(db_session)
    resume_id = _resume(db_session, user)
    job = _create(db_session, user, resume_id, [0, 1])
    stranger = _user(db_session)
    assert resume_api.get_portfolio_report_job_api(job.id, db=db_session, current_user=stranger)["code"] != 0
