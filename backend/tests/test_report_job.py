"""报告作业：一行作业、一次跑完、一份可下载的自包含 HTML（`report_job_service` + 路由）。

这一族里最值得钉的是两条：
* **候选人视图不带对内证据**——`error_msg`、拒因、模型出处都可能含模型输出；
* **"采纳"只有写入的一条路**——编号折成整块改写之后仍走 `apply-rewrites`，
  所以快照、撤销、`expected_original` 防过期锚点这些既有守卫一个都不必重写。
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from app.api import resume as resume_api
from app.core.security import hash_password
from app.models.history import Resume
from app.models.report_job import ResumeReportJob
from app.models.user import User
from app.services import report_job_service as jobs
from app.services import resume_analysis_service
from app.services import resume_report_service as report_svc
from app.services.report_html_lint import lint_report_html
from app.services.resume_blocks import build_resume_blocks
from app.utils.time_helper import utc_now_naive

SELF_EVAL = "1 年多 AI 应用开发经验，做过法律、金融、电网三个场景"
PROJ_DESC = "证据检索准确率约 92%，这套检索链路是我搭的。最大执行步数写在配置里。"
PARSED = {
    "name": "示例候选人",
    "phone": "13600000001",
    "email": "z@example.com",
    "years_exp": 2,
    "education": "本科",
    "major": "计算机科学与技术",
    "current_title": "AI 应用开发工程师（RAG / Agent）",
    "self_evaluation": SELF_EVAL,
    "skills": ["LangChain", "BM25", "RRF", "FastAPI"],
    "work_experience": [
        {"company": "上海合提", "title": "AI 应用开发", "start": "2024.11", "end": "至今", "desc": "负责检索链路"}
    ],
    "project_experience": [
        {"name": "法律智能体平台", "role": "主程", "tech": ["FastAPI", "LangGraph"], "desc": PROJ_DESC}
    ],
}

_USER_SEQ = iter(range(1, 9999))


def _user(db):
    tag = next(_USER_SEQ)
    user = User(
        username=f"rjob_{tag}",
        email=f"rjob_{tag}@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _resume(db, user) -> int:
    resume = Resume(
        name="示例候选人",
        file_name="r.pdf",
        file_path="uploads/r.pdf",
        file_type="pdf",
        file_size=1024,
        user_id=user.id,
        parsed_json=PARSED,
    )
    db.add(resume)
    db.commit()
    return resume.id


def _fake_stages(monkeypatch, redline_payload, interview_payload):
    """概览那一发仍走 mock 分发（`_MOCK_REPORT_OVERVIEW`，七维之和 65）；
    批改与面试两支由用例直接给载荷——这一族要的是"给这一份简历喂一条/零条能过的批改"，
    而仓库那份 mock 载荷（`_MOCK_REPORT_REDLINE`）的 `del` 逐字锚在 `_MOCK_RESUME` 上，
    与本族的 `PARSED` 不是同一份简历，命中不了。六节齐那条走真派发，见
    `test_mock_provider_alone_renders_every_module_and_passes_the_lint`。"""
    from app.services import llm_service

    def fake_chat(prompt, **kwargs):
        if "批改稿（模块三）" in prompt:
            return redline_payload if redline_payload is not None else {"edits": [], "no_change_note": ""}
        if "面试预演（模块四）" in prompt:
            return interview_payload if interview_payload is not None else {"questions": []}
        return json.loads(llm_service._mock_chat(prompt).strip().strip("`").removeprefix("json").strip())

    monkeypatch.setattr(report_svc, "chat_json", fake_chat)
    monkeypatch.setattr(resume_analysis_service, "chat_json", fake_chat)


@pytest.fixture
def run_job(db_session, monkeypatch):
    """建 (用户, 简历, 跑完的作业)，返回 (job_id, user, resume_id)。"""

    def _run(redline_payload=None, interview_payload=None):
        _fake_stages(monkeypatch, redline_payload, interview_payload)
        user = _user(db_session)
        resume_id = _resume(db_session, user)
        job = jobs.create_report_job(db_session, user_id=user.id, resume_id=resume_id, jd_id=None, target_position="")
        jobs.run_job_on(db_session, job.id)
        db_session.expire_all()
        return job.id, user, resume_id

    return _run


_ONE_KEY_EDIT = {
    "block_id": "self_evaluation",
    "del": "做过法律、金融、电网三个场景",
    "ins": "负责三个场景的检索链路",
    "note": "面试官一定追哪一块是你负责的",
    "tier": "key",
}
_BASIC_EDIT = {
    "block_id": "basic",
    "del": "工作经验：2 年",
    "ins": "工作经验：2 年 6 个月",
    "note": "与个人优势里的年限口径要对齐，两个数并排出现面试官一定会问",
    "tier": "key",
}
_TODO_EDIT = {
    "block_id": "proj[0].desc",
    "del": "最大执行步数写在配置里。",
    "ins": "最大执行步数是【待补：实际配置值】，跑一半挂掉能接着跑。",
    "note": "长任务最怕跑飞，这题要有纸面上的数",
    "tier": "normal",
}


def test_poll_payload_exposes_neither_error_text_nor_rejections(run_job, db_session):
    job_id, user, _rid = run_job(
        redline_payload={"edits": [_ONE_KEY_EDIT], "no_change_note": ""},
        interview_payload={"questions": []},
    )

    data = resume_api.get_report_job_api(job_id, db=db_session, current_user=user)["data"]

    assert data["status"] == "completed"
    assert data["total_score"] == 65 and data["grade"] == "C"
    assert data["report"]["redline"]["total"] == 1
    wire = json.dumps(data, ensure_ascii=False)
    for forbidden in ("error_msg", "redline_rejected", "interview_rejected", "provenance", "model_reported_total"):
        assert forbidden not in wire, f"{forbidden} 不该出现在轮询载荷里"


def test_a_missing_interview_module_is_recorded_not_fabricated(run_job, db_session):
    job_id, _user_row, _rid = run_job(redline_payload={"edits": [_ONE_KEY_EDIT], "no_change_note": ""})

    job = db_session.get(ResumeReportJob, job_id)

    assert job.report_json["interview"] is None
    assert "interview" in (job.errors_json or {}).get("stage_errors", {}), "整节没出来时必须留下一句对内可查的原因"
    assert job.lint_failures == 0


def test_the_stored_report_renders_a_lint_clean_standalone_html(run_job, db_session):
    job_id, user, _rid = run_job(
        redline_payload={"edits": [_ONE_KEY_EDIT, _TODO_EDIT, _BASIC_EDIT], "no_change_note": ""},
        interview_payload={"questions": []},
    )

    response = resume_api.download_report_html(job_id, db=db_session, current_user=user)
    document = response.body.decode("utf-8")

    assert "attachment" in response.headers["content-disposition"]
    assert lint_report_html(document) == []
    assert 'id="m-boss"' in document
    assert '<sup class="mk key">1</sup>' in document
    assert "【待补：实际配置值】" in document
    # 从库里那一行还原时不能丢字段：填空与标题姓名都是下载那份文件的成分。
    assert "本报告的两处填空" in document
    assert "简历评估报告 · 示例候选人" in document


def test_mock_provider_alone_renders_every_module_and_passes_the_lint(db_session):
    """开发态/演示态（provider=mock，不打任何补丁）六节必须齐。

    D231 之前这一条是不成立的：mock 只派得出概览那一段，批改与面试两节整块缺席，
    六模块页面在演示环境里根本看不到，那两节的形状也就从没被真浏览器读过。
    这里不打补丁，走的就是 `llm_service._mock_chat` 的真派发。
    """
    from app.services import llm_service

    user = _user(db_session)
    resume = Resume(
        name="示例候选人",
        file_name="mock.pdf",
        file_path="uploads/mock.pdf",
        file_type="pdf",
        file_size=1024,
        user_id=user.id,
        parsed_json=llm_service._MOCK_RESUME,
    )
    db_session.add(resume)
    db_session.commit()

    job = jobs.create_report_job(db_session, user_id=user.id, resume_id=resume.id, jd_id=None, target_position="")
    jobs.run_job_on(db_session, job.id)
    db_session.expire_all()

    job = db_session.get(ResumeReportJob, job.id)
    report = job.report_json

    assert job.status == "completed"
    assert job.total_score == 65 and job.grade == "C"
    assert report["redline"]["total"] == 6 and report["redline"]["key_total"] == 3
    assert report["interview"]["distribution"]["total"] == 8
    assert len(report["apply_strategy"]["chapters"]) == 5
    assert (job.errors_json or {}).get("stage_errors", {}) == {}
    assert job.lint_failures == 0
    assert {stage: row["source"] for stage, row in (job.provenance_json or {}).items()} == {
        "overview": "mock",
        "redline": "mock",
        "interview": "mock",
    }

    document = resume_api.download_report_html(job.id, db=db_session, current_user=user).body.decode("utf-8")
    assert lint_report_html(document) == []
    for anchor in ("m-summary", "m-score", "m-fit", "m-resume", "m-interview", "m-boss"):
        assert f'id="{anchor}"' in document, anchor


def test_applying_a_mark_goes_through_the_existing_rewrite_path(run_job, db_session):
    job_id, user, resume_id = run_job(redline_payload={"edits": [_ONE_KEY_EDIT, _BASIC_EDIT], "no_change_note": ""})

    data = resume_api.apply_redline_api(job_id, {"marks": [1, 2]}, db=db_session, current_user=user)["data"]

    assert data["changed"] is True
    # 2 号打在基本信息那栏：字段值，批得上但不写回简历。
    assert [item["block_id"] for item in data["applied"]] == ["self_evaluation"]
    assert (
        db_session.get(Resume, resume_id).parsed_json["self_evaluation"]
        == "1 年多 AI 应用开发经验，负责三个场景的检索链路"
    )
    assert data["snapshot_version_id"]

    revert = resume_api.revert_rewrite(
        resume_id,
        {"snapshot_version_id": data["snapshot_version_id"]},
        db=db_session,
        current_user=user,
    )
    assert revert["data"]["reverted"] is True
    db_session.expire_all()
    restored = db_session.get(Resume, resume_id).parsed_json
    assert restored["self_evaluation"] == SELF_EVAL
    assert build_resume_blocks(restored)


def test_a_computed_number_is_refused_even_though_it_is_not_invented_out_of_thin_air(run_job, db_session):
    """从起止时间推出的"1 年 8 个月"是算出来的，不是简历上写着的——同一条不编数字的规矩管它。
    模型的正确出口是 `【待补：…】`，所以这一条必须被拒、且拒因写得很具体。"""
    job_id, _user_row, resume_id = run_job(
        redline_payload={
            "edits": [
                {
                    "block_id": "basic",
                    "del": "工作经验：2 年",
                    "ins": "工作经验：AI 应用开发 1 年 8 个月",
                    "note": "与个人优势的口径要对齐",
                    "tier": "key",
                }
            ],
            "no_change_note": "",
        }
    )

    job = db_session.get(ResumeReportJob, job_id)
    refused = (job.errors_json or {}).get("redline_rejected") or []

    assert [item["reason"] for item in refused] == ["invented_number"]
    # 全被拒 ≠ "这一版可以原样用"。这一节是没出来，报告里没有替它编一句好话。
    assert job.report_json["redline"] is None
    assert "redline" in (job.errors_json or {}).get("stage_errors", {})


def test_an_unknown_mark_is_refused_without_touching_the_resume(run_job, db_session):
    job_id, user, resume_id = run_job(redline_payload={"edits": [_ONE_KEY_EDIT], "no_change_note": ""})

    response = resume_api.apply_redline_api(job_id, {"marks": [9]}, db=db_session, current_user=user)

    assert response["code"] != 0 and "编号不存在" in response["message"]
    assert db_session.get(Resume, resume_id).parsed_json["self_evaluation"] == SELF_EVAL


def test_marks_that_all_land_on_field_columns_say_so_instead_of_claiming_success(run_job, db_session):
    job_id, user, _rid = run_job(redline_payload={"edits": [_BASIC_EDIT], "no_change_note": ""})

    response = resume_api.apply_redline_api(job_id, {"marks": [1]}, db=db_session, current_user=user)

    assert response["code"] != 0
    assert "需要自己在简历文件里改" in response["message"]


def test_a_foreign_job_is_not_readable_nor_downloadable_nor_appliable(run_job, db_session):
    job_id, _owner, _rid = run_job()
    other = _user(db_session)

    assert resume_api.get_report_job_api(job_id, db=db_session, current_user=other)["code"] != 0
    assert resume_api.download_report_html(job_id, db=db_session, current_user=other)["code"] != 0
    assert resume_api.apply_redline_api(job_id, {"marks": [1]}, db=db_session, current_user=other)["code"] != 0


def test_submitting_twice_reuses_the_open_row(run_job, db_session):
    job_id, user, resume_id = run_job()
    db_session.query(ResumeReportJob).filter(ResumeReportJob.id == job_id).update({"status": "pending"})
    db_session.commit()

    again = jobs.create_report_job(db_session, user_id=user.id, resume_id=resume_id, jd_id=None, target_position="")

    assert again.id == job_id
    assert db_session.query(ResumeReportJob).filter(ResumeReportJob.user_id == user.id).count() == 1


def test_only_one_claimer_wins_a_row(run_job, db_session):
    job_id, _user_row, _rid = run_job()
    db_session.query(ResumeReportJob).filter(ResumeReportJob.id == job_id).update(
        {"status": "pending", "claimed_at": None}
    )
    db_session.commit()

    first = jobs.claim_report_job(db_session, job_id)
    second = jobs.claim_report_job(db_session, job_id)

    assert (first, second) == (1, 0)


def test_a_stale_running_row_is_requeued_on_read(run_job, db_session, monkeypatch):
    job_id, _user_row, _rid = run_job()
    job = db_session.get(ResumeReportJob, job_id)
    job.status = "running"
    job.claimed_at = utc_now_naive() - timedelta(minutes=90)
    db_session.commit()
    resubmitted: list[int] = []
    monkeypatch.setattr(jobs, "submit_report_job", lambda job_id_: resubmitted.append(job_id_))

    status = jobs.touch_job_for_read(db_session, job)

    assert status == "pending"
    assert resubmitted == [job_id], "读路径就是那条恢复扫描，不另立调度任务"
