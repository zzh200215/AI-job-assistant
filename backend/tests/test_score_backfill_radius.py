"""A1 的两条自检：半径表要**算得对**，更要真的**只读**。

"70 条历史要不要回算"这个问题在没有半径表之前无法回答，而半径表本身是脚本产的——所以脚本的
判据必须钉住三件事，每一件都是"错了不会报错、只会安静地给出一张看起来正常的表"：

* **进半径的判据是落库路径自己盖的权威标记**，不是分数、不是日期。而这两条路径的标记**拼法不一样**
  （strategies 写 `score_method`、match_service 写 `match_score_method`），两种都必须认。判据写错的
  方向是 *多算*（把已经走权威的行走进去回算），所以这里给一条带标记的行塞进一个离谱的分（99），
  要求它压根不进桶；再把标记抹掉，同一行必须立刻进桶。
* **算不出来的行不能猜**。简历或岗位已经不在了 → 单独报 `not_recomputable` 和原因，绝不进分桶。
* **一条都不写**。回算（写路径）是另一件事、要另一次拍板，所以"这个脚本只读"必须可证伪：
  下面把 `Session.commit` / `Session.flush` 换成"一调用就红"，再跑一次 `main()`，
  并当场验一次这两个屏障真的会咬。
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

import scripts.score_backfill_radius as radius
from app.models.history import AnalysisRecord, JobDescription, Resume
from app.services.match_score_service import compute_canonical_score
from app.services.scoring_config import SCORE_METHOD

# 树里不存在的岗位 id：SQLite 默认不强制 FK，正好用来造"这行重算不了"。
GHOST_JD_ID = 999_999

BEFORE_FIX = datetime(2026, 8, 1, 9, 0, 0)
AFTER_FIX = datetime(2026, 9, 25, 9, 0, 0)


def _auth(resume: Resume, jd: JobDescription) -> int:
    """权威分，取法与脚本逐字相同（同一个 `int(round(float(...)))`，避免半位差）。"""
    return int(round(float(compute_canonical_score(resume, jd)["score"])))


@pytest.fixture
def pair(db_session):
    """一份能算出中间档分数的简历 + 一个明确要求它不全中的岗位。"""
    resume = Resume(
        user_id=1,
        file_name="radius.pdf",
        file_path="uploads/radius.pdf",
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
        raw_text="要 Python、MySQL；要求 Go 与 Kubernetes；三年起",
        parsed_json={
            "title": "后端开发工程师",
            "required_skills": ["Python", "MySQL", "Go", "Kubernetes"],
            "nice_to_have": ["Redis"],
            "keywords": ["Python", "MySQL", "订单", "支付"],
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
    return resume, jd


def _record(
    db: Session,
    resume: Resume,
    jd: JobDescription,
    *,
    row_id: int,
    score: int | None,
    report: dict | None = None,
    created: datetime = BEFORE_FIX,
    is_deleted: int = 0,
    jd_id: int | None = None,
) -> AnalysisRecord:
    row = AnalysisRecord(
        id=row_id,
        user_id=resume.user_id,
        resume_id=resume.id,
        jd_id=jd.id if jd_id is None else jd_id,
        match_score=score,
        match_report=report or {},
        optimize_suggestions={},
        interview_questions={},
        create_time=created,
        is_deleted=is_deleted,
    )
    db.add(row)
    db.commit()
    return row


def test_the_marker_decides_who_is_in_the_radius(db_session, pair):
    resume, jd = pair
    auth = _auth(resume, jd)
    # 这条夹具得落在中间档，否则下面 +40 / −15 的构造会跑出负数分，测的就不是分桶了。
    assert 20 <= auth <= 60, f"夹具分数跑出中间档：{auth}"

    # strategies.py 自 1d4e16a 起的落库形状：标记在，模型自报数被降级成另一个键。
    _record(
        db_session,
        resume,
        jd,
        row_id=1,
        score=99,
        report={
            "score_method": SCORE_METHOD,
            "model_reported_score": 99,
            "skill_gap": ["Go", "Kubernetes"],
        },
        created=AFTER_FIX,
    )

    s = radius.build_report(db_session, 15)["summary"]
    assert s["total"] == 1
    assert s["with_authority_marker"] == 1, "带标记的行已经被权威管着了，不该进半径"
    assert s["without_authority_marker"] == 0
    assert s["recomputable"] == 0
    assert s["without_and_created_after_fix"] == 0
    assert s["deltas"] == [], "不进半径的行一个分差都不该产生"
    assert s["delta_stats"] == {"n": 0, "max": None, "mean": None, "median": None, "p90": None}

    # 反向：把标记抹掉（其余一字不动），同一行必须立刻掉进半径。
    # 没有这一条，"with_authority_marker == 1" 有可能只是脚本压根没在看任何行。
    row = db_session.get(AnalysisRecord, 1)
    row.match_report = {"model_reported_score": 99}
    db_session.commit()

    s2 = radius.build_report(db_session, 15)["summary"]
    assert s2["with_authority_marker"] == 0
    assert s2["without_authority_marker"] == 1
    assert s2["recomputable"] == 1
    assert s2["deltas"] == [abs(auth - 99)]
    # 日期只是旁证，不是判据：这一行 create_time 晚于修复日，所以两个数都该是 1。
    assert s2["without_and_created_after_fix"] == 1


def test_both_spellings_of_the_marker_are_honoured(db_session, pair):
    """两条落库路径给同一个事实用了两个键名，判据必须都认。

    `strategies.py:262` 写 `score_method`，`match_service.py:103` 写 `match_score_method`，
    而树里除了这个脚本没有第三个读者。只认前一种的话，经 `POST /analysis/match` 写的行会被当成
    旧形状再算一遍——值相同、Δ0，屏幕上什么错都看不见，但半径表虚高，而这张表唯一的用途就是定半径。
    """
    resume, jd = pair
    _record(db_session, resume, jd, row_id=20, score=99, report={"match_score_method": SCORE_METHOD})

    s = radius.build_report(db_session, 15)["summary"]
    assert s["with_authority_marker"] == 1, "match_service 那种拼法没被认出来"
    assert s["without_authority_marker"] == 0
    assert s["deltas"] == []

    # 空串不算标记：降级分支里 `canonical["method"]` 有可能是 None，那不能当成"已走权威"。
    row = db_session.get(AnalysisRecord, 20)
    row.match_report = {"match_score_method": ""}
    db_session.commit()
    assert radius.build_report(db_session, 15)["summary"]["without_authority_marker"] == 1


def test_deltas_land_in_the_bucket_they_are_written_for(db_session, pair):
    resume, jd = pair
    auth = _auth(resume, jd)

    _record(db_session, resume, jd, row_id=2, score=auth)  # Δ0
    _record(db_session, resume, jd, row_id=3, score=auth + 5)  # Δ−5，边界归 ≤5
    _record(db_session, resume, jd, row_id=4, score=auth - 15)  # Δ+15，边界归 6–15
    _record(db_session, resume, jd, row_id=5, score=auth + 40)  # Δ−40

    report = radius.build_report(db_session, 15)
    s = report["summary"]
    assert s["recomputable"] == 4
    assert s["not_recomputable"] == 0
    assert s["buckets"] == {"equal": 1, "le5": 1, "le15": 1, "gt15": 1}
    assert s["delta_stats"] == {"n": 4, "max": 40, "mean": 15.0, "median": 10.0, "p90": 40}
    # 明细按 |Δ| 倒序：这张表存在的意义就是"先看最离谱的那几条"。
    assert [d["record_id"] for d in report["detail"]] == [5, 4, 3, 2]
    assert report["detail"][0]["delta"] == -40
    assert report["detail"][0]["stored"] == auth + 40
    assert report["detail"][0]["authoritative"] == auth
    # 重算走的是权威那一条，所以 method 必然是 SCORE_METHOD；cap 是否生效要单独看得见。
    assert report["detail"][0]["method"] == SCORE_METHOD
    assert isinstance(report["detail"][0]["cap_applied"], bool)


def test_detail_truncation_keeps_the_widest_gaps(db_session, pair):
    resume, jd = pair
    auth = _auth(resume, jd)
    for i, offset in enumerate([1, 30, 12, 25], start=6):
        _record(db_session, resume, jd, row_id=i, score=auth + offset)

    report = radius.build_report(db_session, 2)
    assert report["summary"]["recomputable"] == 4, "截断只作用于明细，汇总必须看全表"
    assert [d["record_id"] for d in report["detail"]] == [7, 9], "limit=2 要留下 Δ30 与 Δ25"


def test_rows_that_cannot_be_recomputed_are_reported_not_guessed(db_session, pair):
    resume, jd = pair
    _record(db_session, resume, jd, row_id=10, score=88, jd_id=GHOST_JD_ID, created=AFTER_FIX)

    report = radius.build_report(db_session, 15)
    s = report["summary"]
    assert s["without_authority_marker"] == 1
    assert s["recomputable"] == 0, "岗位已经不在了，不能拿一个猜出来的分数进桶"
    assert s["not_recomputable"] == 1
    assert s["not_recomputable_reasons"] == {"岗位已不可见": 1}
    assert s["buckets"] == {"equal": 0, "le5": 0, "le15": 0, "gt15": 0}
    assert s["deltas"] == []
    # 软删与"有没有分"都不影响它进不进半径的判定：这条行还活着且有分。
    assert s["visible_without_marker"] == 1


def test_visibility_counts_only_rows_a_candidate_can_still_see(db_session, pair):
    resume, jd = pair
    auth = _auth(resume, jd)
    _record(db_session, resume, jd, row_id=11, score=auth, is_deleted=1)  # 软删：看不见
    _record(db_session, resume, jd, row_id=12, score=None)  # 从来没分出过分：看不见

    report = radius.build_report(db_session, 15)
    s = report["summary"]
    assert s["without_authority_marker"] == 2
    assert s["visible_without_marker"] == 0, "回算会改到的'候选人还看得见的数'必须单独计数"

    # 没有分的那一行仍然进半径，且按"存 0"处理——Δ 就是整份权威分。
    # 这不是笔误：这类行的"回算代价"恰恰是最大的（从空白变成一个数）。
    assert auth > 15, f"夹具分数太低，这条用例的边界不成立：{auth}"
    assert s["recomputable"] == 2
    assert s["deltas"] == [0, auth]
    assert s["buckets"] == {"equal": 1, "le5": 0, "le15": 0, "gt15": 1}


def test_the_radius_script_never_writes(db_session, pair, capsys, monkeypatch):
    resume, jd = pair
    auth = _auth(resume, jd)
    _record(db_session, resume, jd, row_id=13, score=auth + 40)
    _record(db_session, resume, jd, row_id=14, score=99, report={"score_method": SCORE_METHOD})

    def _no_write(self, *args, **kwargs):
        raise AssertionError("半径脚本写了库——回算是另一次拍板，这里不许动手")

    monkeypatch.setattr(radius, "SessionLocal", lambda: db_session)
    # 两道屏障：commit 才是"落库"，flush 是它的前一步。第一次跑这条时只 patch 了 flush，
    # 结果任何一次 ORM 查询都红——因为 autoflush 每次查询都会调 flush，那是会话自己的记账，
    # 不是脚本在写。把 autoflush 关掉之后，flush 只剩"脚本显式要的"这一种来源。
    db_session.autoflush = False
    monkeypatch.setattr(Session, "commit", _no_write)
    monkeypatch.setattr(Session, "flush", _no_write)

    assert radius.main(["--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["with_authority_marker"] == 1
    assert payload["summary"]["recomputable"] == 1
    assert payload["detail"][0]["record_id"] == 13
    assert payload["detail"][0]["stored"] == auth + 40

    # 反证：这两道屏障不是摆设——同一时刻让脚本走一遍"写回权威分"，它必须立刻红。
    with pytest.raises(AssertionError, match="写了库"):
        db_session.commit()
    with pytest.raises(AssertionError, match="写了库"):
        db_session.flush()


def test_human_output_names_the_radius_it_measured(db_session, pair, capsys, monkeypatch):
    resume, jd = pair
    auth = _auth(resume, jd)
    _record(db_session, resume, jd, row_id=15, score=auth + 40)

    monkeypatch.setattr(radius, "SessionLocal", lambda: db_session)

    assert radius.main([]) == 0
    out = capsys.readouterr().out
    assert "不带权威标记（旧形状）：1" in out
    assert "相等 0 · ≤5 0 · 6–15 0 · >15 1" in out
    assert "Δ-40" in out
