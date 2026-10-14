"""一份单项目分析的 HTML 必须过交付前机检；每发变异只红它那一条。

这条文件钉的是**渲染层与机检层同一套口径**：服务端已经复核过的东西，
渲染器画错了、少画了、多画了，机检要在落盘前拦住，而不是等候选人下载了才发现少一节。
"""

import re

import pytest
from project_report_payloads import (
    BODY,
    ENTRY,
    PEERS,
    advice_payload,
    diagrams_payload,
    profile_payload,
    questions_payload,
)

from app.services import project_report_service as svc
from app.services.project_report_html import render_project_report_html
from app.services.project_report_html_lint import lint_project_html
from app.services.project_report_schema import ProjectReport, build_project_excerpt


def _report(with_questions: bool = True, excluded: bool = False) -> ProjectReport:
    payload = profile_payload()
    if excluded:
        payload["red_lines"] = [
            {
                "key": "others_work",
                "quote": "使用 Qwen 7B 做 LoRA 适配验证",
                "why": "整条适配写成自己主导，一问分工就露",
            }
        ]
    profile, _ = svc.validate_profile(payload, 0, BODY, PEERS)
    excerpt = build_project_excerpt(ENTRY, 0)
    report = ProjectReport(resume_id=1, project_index=0, report_date="2026-10-14")
    report.excerpt = excerpt
    report.portrait = profile["portrait"]
    report.dimensions = profile["dimensions"]
    report.excluded_by = profile["excluded_by"]
    report.difficulty = profile["difficulty"]
    report.highlights = profile["highlights"]
    report.hooks = profile["hooks"]
    report.risks = profile["risks"]
    report.peer_totals = profile["peer_totals"]
    report.total_score = svc.rubric.total_of(report.dimensions)
    report.grade = None if report.is_excluded() else svc.rubric.grade_of(report.total_score)
    report.grade_desc = "" if report.is_excluded() else svc.rubric.grade_desc_of(report.total_score)
    report.grade_scale = svc.rubric.grade_scale_block()
    report.contribution = svc.compute_contribution(0, report.total_score, report.peer_totals)
    report.metric_gap_evidence = svc.rubric.metric_gap_clauses(svc.excerpt_text(excerpt))
    report.stack_footprint = svc.rubric.stack_footprint(ENTRY["tech"], svc.excerpt_text(excerpt))

    diagrams, _ = svc.validate_diagrams(diagrams_payload(), svc.excerpt_text(excerpt))
    report.diagrams = diagrams
    advice, _ = svc.validate_advice(advice_payload(), report)
    report.advice = advice
    if with_questions and not excluded:
        items, distribution, _ = svc.validate_questions(questions_payload(), BODY, len(report.risks))
        report.questions = {
            "deferred": False,
            "note": "",
            "questions": items,
            "distribution": distribution,
            "practice": svc.practice_backfill(items),
        }
    elif excluded:
        report.questions = {"deferred": True, "note": "这一节先不出题。", "questions": [], "distribution": None}
    return report


def _issue_codes(html: str, report: ProjectReport) -> set[str]:
    return {issue.code for issue in lint_project_html(html, report)}


def test_a_complete_report_passes_the_delivery_lint():
    document = render_project_report_html(_report())
    assert lint_project_html(document, _report()) == []
    assert "一、项目档案" in document and "四、面试准备" in document
    assert "★ 我负责" in document


def test_excluded_report_renders_without_a_score_and_without_questions():
    report = _report(excluded=True)
    document = render_project_report_html(report)
    assert lint_project_html(document, report) == []
    assert "不作数" in document
    assert 'id="redline-banner"' in document


def test_section_four_is_absent_until_the_button_is_pressed():
    report = _report(with_questions=False)
    document = render_project_report_html(report)
    assert lint_project_html(document, report) == []
    assert 'href="#p-questions"' not in document
    assert "这一份下载的时候第四节还没生成" in document


@pytest.mark.parametrize(
    "needle,expected",
    [
        ('href="#p-advice"', "navigation"),
        ('<p class="vl">这一段是模型自己加的</p>', "excerpt-not-verbatim"),
        ("门禁", "mechanism-word"),
        ("法审通", "unreplaced-sample"),
        ('<img src="http://x/y.png">', "external-resource"),
    ],
)
def test_each_mutation_reds_its_own_check(needle, expected):
    report = _report()
    html = render_project_report_html(report)
    if expected == "navigation":
        mutated = html.replace('<a href="#p-advice">三、使用建议</a>', "")
    elif expected == "excerpt-not-verbatim":
        mutated = html.replace('<div class="paper" id="paper">', '<div class="paper" id="paper">' + needle, 1)
    else:
        mutated = html + needle
    codes = _issue_codes(mutated, report)
    assert expected in codes, codes


def test_a_wrong_total_in_the_table_does_not_ship():
    report = _report()
    html = render_project_report_html(report)
    mutated = re.sub(r'(<b id="score-total">)[^<]*(</b>)', r"\g<1>88\g<2>", html)
    assert "score-total" in _issue_codes(mutated, report)


def test_a_scored_dimension_with_no_reason_blocks_the_render():
    report = _report()
    rows = [dict(row) for row in report.dimensions]
    rows[1]["note"] = ""
    report.dimensions = rows
    with pytest.raises(RuntimeError) as caught:
        render_project_report_html(report)
    assert "note-missing" in str(caught.value)


def test_question_declaration_must_match_the_body():
    report = _report()
    html = render_project_report_html(report).replace('data-total="5"', 'data-total="20"')
    assert "question-count" in _issue_codes(html, report)


def test_a_third_followup_is_a_shape_break():
    report = _report()
    html = render_project_report_html(report).replace(
        '<p class="fu"><span class="lbl fuk">边界</span>追问二：定稿责任在谁，出了错怎么追</p>',
        '<p class="fu"><span class="lbl fuk">边界</span>追问二：定稿责任在谁，出了错怎么追</p>'
        '<p class="fu"><span class="lbl fuk">踩坑</span>追问三</p>',
        1,
    )
    assert "followup-count" in _issue_codes(html, report)


def test_a_figure_without_an_anchored_source_does_not_ship():
    report = _report()
    html = render_project_report_html(report).replace("<td>职责第 2 条</td>", "<td>见上文</td>", 1)
    assert "deep-dive-unanchored" in _issue_codes(html, report)


def test_ellipsis_is_caught_at_a_boundary_only():
    report = _report()
    html = render_project_report_html(report)
    assert "合同上传" in html  # 正常用词里带着"同上"两个字，不该被判省略写法
    assert "ellipsis" not in _issue_codes(html, report)
    assert "ellipsis" in _issue_codes(html + "<p>其余部分同上。</p>", report)
