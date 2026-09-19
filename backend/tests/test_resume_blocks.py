"""B1.1: anchored resume editing must be able to say *which* text it changed.

The parse prompt emits free JSON with no span, id or line number, and the
Markdown in `ResumeVersion` is a one-way projection that nothing scores. Without
an address space, a "rewrite suggestion" cannot be applied to the data the match
score reads — and a hallucinated anchor cannot be told apart from a real one.
"""

from __future__ import annotations

import copy

from app.services.resume_blocks import (
    SELF_EVALUATION_BLOCK_ID,
    SKILLS_BLOCK_ID,
    apply_block_edits,
    build_resume_blocks,
)


def _parsed():
    return {
        "name": "张三",
        "skills": ["Python", "FastAPI", "Python"],
        "self_evaluation": "三年后端经验",
        "work_experience": [
            {"company": "A 公司", "title": "后端工程师", "start": "2021-03", "end": "至今", "desc": "负责订单服务"},
            {"company": "B 公司", "title": "实习生", "start": "2020-01", "end": "2020-06", "desc": "参与内部工具开发"},
        ],
        "project_experience": [
            {"name": "推荐系统", "role": "负责人", "desc": "召回与排序实现"},
            {"name": "空描述项目", "role": "成员", "desc": "   "},
        ],
    }


def _ids(blocks):
    return [b["block_id"] for b in blocks]


# ---------------------------------------------------------------- anchors


def test_blocks_cover_every_text_bearing_section():
    blocks = build_resume_blocks(_parsed())
    assert _ids(blocks) == [
        SKILLS_BLOCK_ID,
        SELF_EVALUATION_BLOCK_ID,
        "work[0].desc",
        "work[1].desc",
        "proj[0].desc",
    ]


def test_block_labels_come_from_the_resume_itself():
    blocks = {b["block_id"]: b for b in build_resume_blocks(_parsed())}
    assert blocks["work[0].desc"]["label"] == "A 公司 · 后端工程师"
    assert blocks["proj[0].desc"]["label"] == "推荐系统 · 负责人"
    assert blocks["work[1].desc"]["text"] == "参与内部工具开发"
    assert blocks["work[0].desc"]["char_count"] == len("负责订单服务")


def test_empty_sections_are_not_offered_as_rewrite_targets():
    """An absent section is a completeness gap; presenting it as an editable line
    would invite the model to invent experience the candidate never had."""
    parsed = _parsed()
    parsed["work_experience"].append({"company": "C 公司", "title": "工程师", "desc": ""})
    blocks = build_resume_blocks(parsed)

    assert "work[2].desc" not in _ids(blocks)
    assert "proj[1].desc" not in _ids(blocks)  # whitespace-only desc


def test_missing_and_malformed_input_degrade_to_no_targets():
    assert build_resume_blocks(None) == []
    assert build_resume_blocks({}) == []
    # Ids carry the real list index, so a non-dict hole shifts nothing.
    assert _ids(build_resume_blocks({"work_experience": ["不是字典", {"desc": "有效文本"}]})) == ["work[1].desc"]
    assert build_resume_blocks({"self_evaluation": None, "skills": []}) == []


def test_block_ids_are_stable_across_calls():
    parsed = _parsed()
    assert _ids(build_resume_blocks(parsed)) == _ids(build_resume_blocks(parsed))


# ---------------------------------------------------------------- applying


def _apply(edits, parsed=None):
    return apply_block_edits(parsed if parsed is not None else _parsed(), edits)


def test_unknown_anchor_is_rejected_and_the_rest_still_applies():
    parsed = _parsed()
    new, applied, rejected = _apply(
        [
            {"block_id": "work[7].desc", "proposed_text": "幻觉出来的经历"},
            {"block_id": "work[0].desc", "proposed_text": "主导订单服务拆分，QPS 提升 3 倍"},
        ],
        parsed,
    )

    assert [r["block_id"] for r in rejected] == ["work[7].desc"]
    assert rejected[0]["reason"] == "unknown_block"
    assert [a["block_id"] for a in applied] == ["work[0].desc"]
    assert new["work_experience"][0]["desc"] == "主导订单服务拆分，QPS 提升 3 倍"
    assert new["work_experience"][1]["desc"] == "参与内部工具开发"


def test_applied_edit_reports_before_and_after():
    _, applied, _ = _apply([{"block_id": "self_evaluation", "proposed_text": "五年高并发后端与 RAG 落地经验"}])
    assert applied[0]["before"] == "三年后端经验"
    assert applied[0]["after"] == "五年高并发后端与 RAG 落地经验"
    assert applied[0]["kind"] == "self_evaluation"


def test_edits_never_mutate_the_source_dict():
    """The caller assigns the result onto Resume.parsed_json; that reassignment is
    what marks the column dirty and advances update_time, which every score and
    recommendation cache keys off. In-place mutation would apply the edit while
    leaving cached scores describing the old resume."""
    parsed = _parsed()
    snapshot = copy.deepcopy(parsed)

    new, applied, _ = _apply([{"block_id": "work[0].desc", "proposed_text": "改写后的描述"}], parsed)

    assert applied
    assert new is not parsed
    assert parsed == snapshot


def test_ids_still_resolve_after_an_edit_so_edits_can_chain():
    new, _, _ = _apply([{"block_id": "proj[0].desc", "proposed_text": "重建召回链路并上线"}])
    blocks = build_resume_blocks(new)

    assert "proj[0].desc" in _ids(blocks)
    again, applied, rejected = _apply([{"block_id": "work[1].desc", "proposed_text": "独立交付内部工具"}], new)
    assert applied and not rejected
    assert again["work_experience"][1]["desc"] == "独立交付内部工具"


def test_skills_edit_becomes_a_deduplicated_list():
    new, applied, _ = _apply([{"block_id": SKILLS_BLOCK_ID, "proposed_text": "Python、FastAPI；LangGraph / MySQL"}])

    assert applied[0]["kind"] == "skills"
    assert new["skills"] == ["Python", "FastAPI", "LangGraph", "MySQL"]
    assert new["self_evaluation"] == "三年后端经验"


def test_blank_and_no_op_edits_are_refused():
    parsed = _parsed()
    new, applied, rejected = _apply(
        [
            {"block_id": "work[0].desc", "proposed_text": "   "},
            {"block_id": "work[1].desc"},
            {"block_id": "work[0].desc", "proposed_text": "负责订单服务"},
            "不是对象",
        ],
        parsed,
    )

    assert applied == []
    assert [r["reason"] for r in rejected] == [
        "empty_or_missing_text",
        "empty_or_missing_text",
        "unchanged",
        "not_an_object",
    ]
    assert new == parsed


def test_editing_a_known_block_that_was_skipped_is_still_unknown():
    """A whitespace-only desc has no anchor, so pointing at it must be rejected
    rather than silently creating content."""
    parsed = _parsed()
    new, applied, rejected = _apply([{"block_id": "proj[1].desc", "proposed_text": "编造的项目细节"}], parsed)

    assert applied == []
    assert rejected[0]["reason"] == "unknown_block"
    assert parsed["project_experience"][1]["desc"] == "   "
    assert new["project_experience"][1]["desc"] == "   "
