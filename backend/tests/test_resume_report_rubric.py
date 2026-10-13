"""七维口径（`app/services/resume_report_rubric.py`）的守卫。

这一族是纯函数，所以每一条都能在模型不在场的情况下判定。它们守的是三件事：
一张表（维度与满分）不会被任何一侧偷偷改动、模型给的数读不出来时判"未知"而不是 0、
总分与等级是七维之和的函数而不是模型的自报数。
"""

from __future__ import annotations

import pytest

from app.prompts.resume_report_overview import RESUME_REPORT_OVERVIEW_PROMPT
from app.services import resume_report_rubric as rubric

ALL_SEVEN = {
    "metric_ownership": 20,
    "interview_hooks": 10,
    "role_fit": 20,
    "transferability": 15,
    "project_depth": 20,
    "expression_structure": 10,
    "advantage_section": 5,
}


def _full_scores(value: int) -> dict:
    """七个维度都给同一个分。value 不得超过 5（最小的那维满分），否则读出来就带"未知"。"""
    return {key: {"score": value} for key in ALL_SEVEN}


def test_the_seven_dimensions_sum_to_exactly_100():
    assert rubric.TOTAL_FULL == 100
    assert {row[0]: row[2] for row in rubric.DIMENSIONS} == ALL_SEVEN


def test_read_dimensions_returns_all_seven_rows_in_table_order():
    rows = rubric.read_dimensions({"advantage_section": 5, "metric_ownership": 18})

    assert [row["key"] for row in rows] == list(ALL_SEVEN)
    assert rows[0]["score"] == 18
    assert rows[0]["label"] == "指标责任与达成（C）★"
    assert rows[0]["full"] == 20
    assert rows[0]["star"] is True
    assert rows[2]["star"] is False


def test_two_starred_dimensions_is_not_a_typo():
    """成品报告里带 ★ 的正好是 C 与 E 两维，只有一维带星说明表被改坏了。"""
    starred = [row[0] for row in rubric.DIMENSIONS if row[3]]

    assert starred == ["metric_ownership", "interview_hooks"]


def test_an_absent_dimension_is_unknown_not_zero():
    rows = rubric.read_dimensions({"metric_ownership": 12})

    assert rows[0]["score"] == 12
    assert rows[1]["score"] is None


def test_a_model_that_invents_an_eighth_dimension_does_not_move_the_total():
    payload = _full_scores(1)
    payload["team_culture_fit"] = {"score": 5}

    rows = rubric.read_dimensions(payload)

    assert len(rows) == 7
    assert rubric.total_of(rows) == 7


@pytest.mark.parametrize(
    "raw,expected",
    [
        (True, None),  # bool 是 int 的子类，不能靠 isinstance 放行
        ("12", None),
        (None, None),
        (-1, None),
        (21, None),  # 越界不夹紧：把 120 夹成满分等于给一个没量过的维度发满分
        (20, 20),
        (12.4, 12),
        (12.6, 13),
    ],
)
def test_only_a_number_inside_the_band_counts_as_a_score(raw, expected):
    payload = _full_scores(0)
    payload["metric_ownership"] = {"score": raw}

    rows = rubric.read_dimensions(payload)

    assert rows[0]["score"] == expected


def test_a_bare_number_still_reads_and_a_bare_string_note_is_empty():
    """模型偶尔直接给分数而不是对象；这与 `dfee148` 那次"整个 dict 当分数交给前端"是同一族形状问题。"""
    rows = rubric.read_dimensions({"role_fit": 14, "project_depth": "写得挺好"})

    assert rows[2]["score"] == 14
    assert rows[2]["note"] == ""
    assert rows[4]["score"] is None


def test_any_unknown_dimension_makes_the_total_unknown():
    rows = rubric.read_dimensions(_full_scores(3))
    assert rubric.total_of(rows) == 21

    rows[3]["score"] = None

    assert rubric.total_of(rows) is None
    assert rubric.grade_of(None) is None
    assert rubric.grade_desc_of(None) == ""


@pytest.mark.parametrize(
    "total,grade",
    [(100, "A"), (85, "A"), (84, "B"), (75, "B"), (74, "C"), (65, "C"), (64, "D"), (0, "D")],
)
def test_grade_bands_have_no_gaps_and_no_overlaps(total, grade):
    assert rubric.grade_of(total) == grade


def test_the_grade_line_explains_every_band_it_can_print():
    scale = rubric.grade_scale_block()

    for name, _low, _high, _desc in rubric.GRADE_BANDS:
        assert f"{name} " in scale, f"报告会给出的等级 {name} 在说明行里没有解释"


def test_a_non_string_note_never_becomes_a_python_repr_in_the_table():
    """`str({...})` 会把 "{'x': 1}" 印进候选人看到的"待优化点"那一栏。"""
    rows = rubric.read_dimensions(
        {"role_fit": {"score": 10, "note": {"为什么": "没说清"}, "missing_keywords": ["RAG", 7]}}
    )

    assert rows[2]["note"] == ""
    assert rows[2]["missing_keywords"] == ["RAG"]


def test_interview_rehearsal_needs_a_number_to_be_worth_generating():
    assert rubric.interview_allowed(None) is False, "总分未知时出题，等于把没有依据的口述稿递给人"
    assert rubric.interview_allowed(rubric.INTERVIEW_MIN_TOTAL - 1) is False
    assert rubric.interview_allowed(rubric.INTERVIEW_MIN_TOTAL) is True


def test_missing_keywords_are_collected_in_order_without_duplicates():
    rows = rubric.read_dimensions(
        {
            "role_fit": {"score": 10, "missing_keywords": ["RAG", "LangGraph", "RAG"]},
            "project_depth": {"score": 10, "missing_keywords": ["LangGraph", "评测集"]},
        }
    )

    assert rubric.missing_keywords_of(rows) == ["RAG", "LangGraph", "评测集"]


def test_the_prompt_carries_the_same_seven_rows_as_the_table():
    """Prompt 里的维度表由 `rubric_prompt_block()` 生成：手抄那一份改了，服务端校验还按旧表判。"""
    block = rubric.rubric_prompt_block()

    for key, label, full, _star, _rubric in rubric.DIMENSIONS:
        assert f"{key}（{label}，满分 {full}）" in block

    assert f"七维满分之和 = {rubric.TOTAL_FULL}" in block
    # 占位符没被替换掉，说明调用方忘了传 rubric_block。
    assert "{rubric_block}" not in RESUME_REPORT_OVERVIEW_PROMPT.format(
        rubric_block=block, resume_json="{}", target_position="", salary_expectation="未提供"
    )


def test_the_prompt_shows_every_seven_dimension_key_to_the_model():
    rendered = RESUME_REPORT_OVERVIEW_PROMPT.format(
        rubric_block=rubric.rubric_prompt_block(),
        resume_json="{}",
        target_position="",
        salary_expectation="未提供",
    )

    for key in ALL_SEVEN:
        assert f'"{key}"' in rendered, f"{key} 在输出要求里缺席，模型就不会填它"


def test_the_prompt_bans_the_words_the_report_must_not_contain():
    """禁词表在 prompt 里出现一次是规则本身，但成品不许有——所以禁词表必须与 §5 同源。"""
    rendered = RESUME_REPORT_OVERVIEW_PROMPT.format(
        rubric_block=rubric.rubric_prompt_block(),
        resume_json="{}",
        target_position="",
        salary_expectation="未提供",
    )

    assert "【待补" in rendered, "不编数字的出口没写进 prompt，模型就只能编一个"
    assert "严禁把" in rendered and "参与" in rendered and "主导" in rendered
