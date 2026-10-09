"""A3 的落工具：`scripts/score_backfill.py` 的写路径必须**点名才动**，而且能动就得能还原。

§10.38 那三条路里 ③ 是唯一同时消掉"两页矛盾"和"无告知改数"的那一条，代价是它真的会写候选人的历史
分数。所以这个文件钉的全是安全阀，而不是算法——算法那半由 `test_score_backfill_radius.py` 与
`test_match_score_single_source.py` 管：

* 默认 dry-run 且**不写**（把 `Session.commit` 换成一调用就红，再跑一遍 `main([])`）；
* `--apply` 不给 `--backup` 直接拒绝执行（没有 before-image 就没有回退路径）；
* 写进去的是权威数，而**候选人看过的那个留在 `match_report` 里**，备份文件里还有整份旧 `match_report`；
* 幂等：第二遍无可写；
* 行在我们读它之后被人改过 → 那一行不动（条件更新，rowcount 就是裁判）；
* 值本来就等于权威的行走"跳过"，**不为了盖标记去动一行数据**；
* 两个脚本共用同一个判据（`backfill.authority_marker is radius.authority_marker`），一分叉就红。
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

import scripts.score_backfill as backfill
import scripts.score_backfill_radius as radius
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.services.match_score_service import compute_canonical_score
from app.services.scoring_config import SCORE_METHOD

GHOST_JD_ID = 999_999
BEFORE_FIX = datetime(2026, 8, 1, 9, 0, 0)


def _auth(resume: Resume, jd: JobDescription) -> int:
    """权威分，取法与脚本逐字相同（同一个 `int(round(float(...)))`）。"""
    return int(round(float(compute_canonical_score(resume, jd)["score"])))


@pytest.fixture
def pair(db_session):
    resume = Resume(
        user_id=1,
        file_name="bf.pdf",
        file_path="uploads/bf.pdf",
        file_type="pdf",
        file_size=1,
        parsed_json={
            "years_exp": 3,
            "skills": ["Python", "MySQL", "Redis"],
            "project_experience": [{"name": "订单链路", "description": "负责下单、支付的稳定性"}],
            "education": "本科",
        },
        is_deleted=0,
    )
    jd = JobDescription(
        user_id=1,
        title="后端开发工程师",
        company="示例",
        raw_text="要 Python、MySQL；要求 Go 与 Kubernetes",
        parsed_json={
            "title": "后端开发工程师",
            "required_skills": ["Python", "MySQL", "Go", "Kubernetes"],
            "nice_to_have": ["Redis"],
            "keywords": ["Python", "MySQL", "订单"],
            "experience_requirement": "3年及以上",
            "education_requirement": "本科",
        },
        source="manual",
        is_active=1,
    )
    db_session.add_all([resume, jd])
    db_session.commit()
    db_session.refresh(resume)
    db_session.refresh(jd)
    assert 20 <= _auth(resume, jd) <= 60, "夹具分数跑出中间档，下面的 +40 / −30 构造就不成立"
    return resume, jd


def _record(db, resume, jd, *, row_id, score, report=None, jd_id=None) -> AnalysisRecord:
    row = AnalysisRecord(
        id=row_id,
        user_id=resume.user_id,
        resume_id=resume.id,
        jd_id=jd.id if jd_id is None else jd_id,
        match_score=score,
        match_report=report or {},
        optimize_suggestions={},
        interview_questions={},
        create_time=BEFORE_FIX,
        is_deleted=0,
    )
    db.add(row)
    db.commit()
    return row


def test_dry_run_is_the_default_and_it_never_writes(db_session, pair, capsys, monkeypatch):
    resume, jd = pair
    auth = _auth(resume, jd)
    _record(db_session, resume, jd, row_id=1, score=auth + 40)

    def _no_write(self, *args, **kwargs):
        raise AssertionError("dry-run 写了库")

    monkeypatch.setattr(backfill, "SessionLocal", lambda: db_session)
    db_session.autoflush = False
    monkeypatch.setattr(Session, "commit", _no_write)

    assert backfill.main([]) == 0
    out = capsys.readouterr().out
    assert "要改：1" in out
    assert "dry-run：一行都没写" in out

    # `--json` 是另一条出口，也得在屏障下面走一遍：第一版我只跑了人读那一条，
    # 于是把 `db.commit()` 插到 JSON 分支上的变异居然全绿——两条出口都要挡。
    assert backfill.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert payload["written"] == 0
    assert [item["action"] for item in payload["plan"]] == ["rewrite"]

    monkeypatch.undo()
    db_session.autoflush = True
    # 脚本在 finally 里 rollback + close 的是它自己 `SessionLocal()` 出来的 session；测试把宿主
    # session 注了进去，于是那一下回滚打到了宿主事务上，先前捕获的对象被请出 identity map。
    # 所以这里的断言一律重新取一次，不 refresh 旧对象——这是测试接缝的性质，不是被测代码的缺陷。
    assert db_session.get(AnalysisRecord, 1).match_score == auth + 40, "dry-run 之后分数必须还是候选人看过的那个"


def test_apply_refuses_without_a_backup(db_session, pair, monkeypatch):
    """不是礼貌提醒——这条是拒绝执行，不是警告之后照写。"""
    resume, jd = pair
    auth = _auth(resume, jd)
    row = _record(db_session, resume, jd, row_id=2, score=auth + 40)
    monkeypatch.setattr(backfill, "SessionLocal", lambda: db_session)

    with pytest.raises(SystemExit) as caught:
        backfill.main(["--apply"])
    assert "--backup" in str(caught.value)
    db_session.refresh(row)
    assert row.match_score == auth + 40, "被拒绝的那一次一个字节都不该落库"


def test_apply_writes_the_authoritative_number_and_keeps_the_one_the_candidate_saw(
    db_session, pair, tmp_path, capsys, monkeypatch
):
    resume, jd = pair
    auth = _auth(resume, jd)
    stored = auth + 40
    _record(
        db_session,
        resume,
        jd,
        row_id=3,
        score=stored,
        report={"summary": "模型那段话要留着", "gaps": ["Go"]},
    )
    backup = tmp_path / "out" / "before.json"
    monkeypatch.setattr(backfill, "SessionLocal", lambda: db_session)

    assert backfill.main(["--apply", "--backup", str(backup), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "apply"
    assert payload["written"] == 1
    assert payload["skipped_concurrent"] == 0

    # 同 dry-run 那条：脚本的 rollback 打在宿主事务上，旧对象要重新取。
    report = db_session.get(AnalysisRecord, 3).match_report
    assert db_session.get(AnalysisRecord, 3).match_score == auth
    # ③ 的全部意义在这三个键上：新数是权威的，旧数还在，来源也还在。
    assert report["displayed_before_backfill"] == stored
    assert report["model_reported_score"] == stored
    assert report["score_method"] == SCORE_METHOD
    assert report["summary"] == "模型那段话要留着"  # 旧报告里模型写的散文不能被覆盖掉
    assert report["gaps"] == ["Go"]

    image = json.loads(backup.read_text(encoding="utf-8"))
    assert [item["record_id"] for item in image] == [3]
    assert image[0]["match_score"] == stored
    assert image[0]["match_report"]["summary"] == "模型那段话要留着", "备份必须能还原改动前的整份样子"


def test_the_second_apply_has_nothing_left_to_do(db_session, pair, tmp_path, monkeypatch):
    """幂等：跑第二遍必须 0 写。做不到这条就说明"已走权威"的标记没真的落进去。"""
    resume, jd = pair
    auth = _auth(resume, jd)
    _record(db_session, resume, jd, row_id=4, score=auth + 40)
    monkeypatch.setattr(backfill, "SessionLocal", lambda: db_session)

    first = backfill.summarize(backfill.plan_rows(db_session))
    assert first["rewrite"] == 1
    written, raced = backfill.apply_plan(db_session, backfill.plan_rows(db_session))
    db_session.commit()
    assert (written, raced) == (1, 0)

    second = backfill.summarize(backfill.plan_rows(db_session))
    assert second["rewrite"] == 0
    assert second["skip_marked"] == 1, "回算过的行必须已经被判据认成「已走权威」"
    assert backfill.summarize(backfill.plan_rows(db_session))["total"] == 1


def test_a_row_changed_behind_our_back_is_left_alone(db_session, pair):
    """条件更新是这一条唯一的裁判：读到的旧值还在，才动手。"""
    resume, jd = pair
    auth = _auth(resume, jd)
    _record(db_session, resume, jd, row_id=5, score=auth + 40)

    plan = backfill.plan_rows(db_session)
    assert plan[0]["action"] == "rewrite"

    # 候选人在这中间又跑了一场分析：存分被别的写路径改掉了。
    row = db_session.get(AnalysisRecord, 5)
    row.match_score = auth + 7
    db_session.commit()

    written, raced = backfill.apply_plan(db_session, plan)
    db_session.commit()
    assert (written, raced) == (0, 1)
    db_session.refresh(row)
    assert row.match_score == auth + 7, "抢改过的行被覆盖了——条件更新没起作用"


def test_rows_whose_value_already_equals_the_authority_are_not_touched(db_session, pair):
    """值恰好相等的行走"跳过"，且不为了盖标记去写它。

    这是一次取舍而不是遗漏：写它能立刻把半径表清零，但那是一次候选人完全看不见的改动，
    而"同一个数恰好相等"并不等于"同一个方法算出来的"。
    """
    resume, jd = pair
    auth = _auth(resume, jd)
    row = _record(db_session, resume, jd, row_id=6, score=auth, report={"summary": "别动我"})

    plan = backfill.plan_rows(db_session)
    assert [item["action"] for item in plan] == ["skip_equal"]
    written, raced = backfill.apply_plan(db_session, plan)
    assert (written, raced) == (0, 0)
    db_session.refresh(row)
    assert row.match_report == {"summary": "别动我"}


def test_rows_the_resume_or_job_can_no_longer_reach_are_never_written(db_session, pair):
    resume, jd = pair
    _record(db_session, resume, jd, row_id=7, score=90, jd_id=GHOST_JD_ID)

    plan = backfill.plan_rows(db_session)
    assert [item["action"] for item in plan] == ["skip_unreachable"]
    assert backfill.summarize(plan)["rewrite"] == 0


def test_the_two_scripts_read_the_same_one_discriminator(db_session, pair):
    """半径脚本和回算工具必须认同一件事——两处各写一遍迟早分叉。"""
    assert backfill.authority_marker is radius.authority_marker, "判据被复制成了两份"

    resume, jd = pair
    auth = _auth(resume, jd)
    _record(db_session, resume, jd, row_id=8, score=99, report={"score_method": SCORE_METHOD})
    _record(db_session, resume, jd, row_id=9, score=99, report={"match_score_method": SCORE_METHOD})
    _record(db_session, resume, jd, row_id=10, score=auth + 40)

    radius_summary = radius.build_report(db_session, 15)["summary"]
    plan = backfill.summarize(backfill.plan_rows(db_session))
    assert radius_summary["with_authority_marker"] == 2
    assert plan["skip_marked"] == 2, "两边对「哪些行已经被权威管着」数得不一样"
    assert plan["rewrite"] == 1

    # 反证：把第一行的标记抹掉，两边必须**同时**把它算进半径。
    db_session.get(AnalysisRecord, 8).match_report = {}
    db_session.commit()
    assert radius.build_report(db_session, 15)["summary"]["with_authority_marker"] == 1
    assert backfill.summarize(backfill.plan_rows(db_session))["skip_marked"] == 1
