"""§3 那条"每维待优化点必须点名具体位置"的门，与它的判据来源。

判据不是拍出来的：`tests/fixtures/dimension_note_samples.json` 是 2026-10-13 用真 provider
跑四份不同成色简历（84 / 41 / 34 / 21 分）得到的 28 条真实 note。
量出来的形状是——**28 条全部锚定**（27 条带逐字引用、1 条没带引号但指着"技能区/项目实践/求职意向"），
而改造前那一族通用建议五条**一条都不锚定**。
所以：单条没锚不拦（合法输出里就有 1/28），整表都没锚才拦（那是旧写法的确定形状）。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.report_html_lint import (
    _NOTE_ABSENT,
    _check_dimension_notes,
    is_anchored_note,
    lint_report_html,
)
from app.services.resume_report_service import generate_resume_report

FIXTURE = Path(__file__).parent / "fixtures" / "dimension_note_samples.json"

# 改造前那一族的原文形状（通用建议：换个候选人也能照抄）
GENERIC_NOTES = [
    "建议量化项目成果，补充岗位关键词，删除无效技能项。",
    "整体描述偏职责陈述，建议按 STAR 法则改写并突出与岗位契合的能力。",
    "缺少数据指标，建议增加量化结果以提升说服力。",
    "表达可以更精炼一些，重点不够突出。",
    "优势部分写得比较笼统，建议提炼差异化标签。",
]


def _real_notes() -> list[dict]:
    samples = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [note for row in samples for note in row["notes"]]


def _score_table(notes: list[str], scores: list[int | None] | None = None) -> str:
    """拼一张只有评分概览那一节的碎片，交给那条检查自己判。"""
    scores = scores if scores is not None else [8] * len(notes)
    rows = []
    for index, (note, score) in enumerate(zip(notes, scores, strict=False), start=1):
        cell = "—" if score is None else f"<b>{score}</b>"
        body = note if note else f'<span class="muted">{_NOTE_ABSENT}</span>'
        rows.append(
            f'<tr><td><b>维度 {index}</b></td><td class="n">{cell}</td><td class="n"><b>20</b></td><td>{body}</td></tr>'
        )
    total = sum(score for score in scores if score is not None)
    rows.append(f'<tr class="total"><td>合计</td><td class="n">{total}</td><td class="n">120</td><td>C</td></tr>')
    return '<section class="card" id="m-score"><table>' + "".join(rows) + "</table></section>"


# ---------------------------------------------------------------- 判据本身


def test_every_real_note_from_the_four_resumes_is_anchored():
    notes = _real_notes()

    assert len(notes) == 28, "夹具是四份真简历的七维输出，条数应当是 28"
    unanchored = [note["note"][:60] for note in notes if not is_anchored_note(note["note"])]
    assert unanchored == [], f"真样本被判成没锚点：{unanchored}"


def test_the_tables_those_real_notes_render_into_pass_the_gate():
    samples = json.loads(FIXTURE.read_text(encoding="utf-8"))

    for row in samples:
        html = _score_table([note["note"] for note in row["notes"]], [note["score"] for note in row["notes"]])
        assert _check_dimension_notes(html) == [], row["resume"]


def test_generic_advice_is_not_anchored():
    assert [note for note in GENERIC_NOTES if is_anchored_note(note)] == []


def test_a_whole_table_of_generic_advice_is_refused():
    issues = _check_dimension_notes(_score_table(GENERIC_NOTES))

    assert [issue.code for issue in issues] == ["notes-unanchored"]


# ---------------------------------------------------------------- 两条边界


def test_a_scored_row_without_any_note_is_a_delivery_failure():
    notes = [
        GENERIC_NOTES[0],
        "",
        GENERIC_NOTES[1],
        GENERIC_NOTES[2],
        GENERIC_NOTES[3],
        GENERIC_NOTES[4],
        GENERIC_NOTES[0],
    ]
    html = _score_table(notes)
    issues = _check_dimension_notes(html)

    codes = [issue.code for issue in issues]
    assert codes.count("note-missing") == 1, "空的那一栏要被点名，其余六栏不该被牵连"
    assert "notes-unanchored" in codes  # 剩下六栏全是通用建议，整表没一条锚定


def test_an_unscored_dimension_without_a_note_is_not_a_failure():
    """未评分是设计里的合法状态：那一行没有分，也就没有"给了分却没写理由"这回事。"""
    html = _score_table([GENERIC_NOTES[0], ""], scores=[None, None])

    assert _check_dimension_notes(html) == []


def test_one_stray_unanchored_note_does_not_block_delivery():
    """四份真样本里合法地出现过一条不带引号的 note（指着"技能区/项目实践"那一条）。
    按单条硬拦就会把合格报告判死，所以这里只允许"整表都没锚"才拦。"""
    notes = [GENERIC_NOTES[0]] + ["技能区写了 Java 与项目一致，但求职意向缺失。"] * 6
    html = _score_table(notes)

    assert _check_dimension_notes(html) == []


# ---------------------------------------------------------------- 对内那一位数


def test_the_service_counts_anchors_for_the_internal_view_only(db_session, make_resume):
    from app.core.security import hash_password
    from app.models.user import User

    user = User(
        username="anchor_stats",
        email="anchor_stats@example.com",
        password=hash_password("StrongP@ssw0rd"),
        role="candidate",
    )
    db_session.add(user)
    db_session.commit()
    rid = make_resume(user_id=user.id, parsed_json={"name": "张三", "self_evaluation": "5 年后端"})

    report = generate_resume_report(db_session, rid, user_id=user.id)
    internal = report.to_internal_dict()
    public = report.to_public_dict()

    assert report.note_anchor_stats["scored"] == 7
    assert report.note_anchor_stats["anchored"] == 7  # mock 载荷每条都带「」或栏目名
    assert report.note_anchor_stats["unanchored_keys"] == []
    assert "note_anchor_stats" in internal
    assert "note_anchor_stats" not in json.dumps(public, ensure_ascii=False), "这一位是对内的账，不上候选人的屏"


def test_the_accepted_artifact_still_passes_the_new_check():
    """最强的一条反向证据：人工确认过的那份成品，加了这条门之后照样零问题。"""
    html = (Path(__file__).parent / "fixtures" / "report_sample_good.html").read_text(encoding="utf-8")

    assert lint_report_html(html) == [], "这条新门不能把人工确认过的成品判成不合格"
