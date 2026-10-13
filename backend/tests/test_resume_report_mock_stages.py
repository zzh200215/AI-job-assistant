"""mock 世界里的批改稿与面试预演：派发对不对、载荷过不过服务端复核。

为什么要有这一支（D231）：mock 是本仓库的开发态与演示态，`LLM_PROVIDER=mock` 时
六模块页面只能出得来三个模块，剩下三节整块缺席——那已经不是"降级不伪造"，
而是**演示环境里看不到这件交付物**。概览那一段一直有 mock 载荷，另两段没有，
形状就永远不齐。

这里守三条：
1. **派发顺序**——面试预演的 prompt 角色行逐字含「资深面试辅导专家」，与 InterviewAgent
   的关键字撞车；载荷排在智能体那一段后面就会被静默领走，页面少一节且不报错。
2. **载荷真能过复核**——`del` 必须逐字命中 `_MOCK_RESUME` 铺出来的块文本。块文本一改，
   这一发就红，而不是等到演示当天发现右栏批注整块不见了。
3. **改写不新增事实**——口述稿与 `ins` 里不许出现这份简历没有的数字，禁词表也要过。
"""

from __future__ import annotations

import json

from app.prompts.rendering import render_prompt
from app.prompts.resume_report_interview import RESUME_REPORT_INTERVIEW_PROMPT
from app.prompts.resume_report_overview import RESUME_REPORT_OVERVIEW_PROMPT
from app.prompts.resume_report_redline import RESUME_REPORT_REDLINE_PROMPT
from app.services import llm_service
from app.services.report_html_lint import FOLLOWUP_ATOMS, FORBIDDEN_ELLIPSIS, FORBIDDEN_MECHANISM_WORDS
from app.services.resume_blocks import apply_block_edits, build_report_sections
from app.services.resume_report_rubric import rubric_prompt_block
from app.services.resume_report_service import (
    MAX_REDLINE_EDITS,
    validate_interview_questions,
    validate_redline_edits,
)

KNOWN_TEXT = json.dumps(llm_service._MOCK_RESUME, ensure_ascii=False)


def _payload(mock_text: str) -> dict:
    return json.loads(mock_text.strip().strip("`").removeprefix("json").strip())


def _redline_prompt() -> str:
    return render_prompt(
        RESUME_REPORT_REDLINE_PROMPT,
        sections_json=json.dumps(
            [
                {
                    "block_id": b["block_id"],
                    "label": b["label"],
                    "text": b["text"],
                    "editable": b["editable"],
                }
                for b in build_report_sections(llm_service._MOCK_RESUME)
            ],
            ensure_ascii=False,
        ),
        jd_text="未指定目标岗位",
        max_edits=MAX_REDLINE_EDITS,
    )


def _interview_prompt() -> str:
    return render_prompt(
        RESUME_REPORT_INTERVIEW_PROMPT,
        resume_json=KNOWN_TEXT,
        score_block="- 指标与个人达成数：12/20",
        pending_facts="（批改稿里没有留【待补】的数）",
        target_position="Python 后端开发工程师",
    )


def _overview_prompt() -> str:
    return render_prompt(
        RESUME_REPORT_OVERVIEW_PROMPT,
        rubric_block=rubric_prompt_block(),
        resume_json=KNOWN_TEXT,
        target_position="Python 后端开发工程师",
        salary_expectation="未提供",
    )


# ---------------------------------------------------------------- 1. 派发


def test_report_prompts_dispatch_to_their_own_payloads():
    assert _payload(llm_service._mock_chat(_overview_prompt())) == llm_service._MOCK_REPORT_OVERVIEW
    assert _payload(llm_service._mock_chat(_redline_prompt())) == llm_service._MOCK_REPORT_REDLINE
    assert _payload(llm_service._mock_chat(_interview_prompt())) == llm_service._MOCK_REPORT_INTERVIEW


def test_interview_report_prompt_does_not_get_taken_by_the_interview_agent():
    """这一条是派发顺序的守卫：两支 prompt 的角色行撞车，撞了不报错，只少一节。"""
    payload = _payload(llm_service._mock_chat(_interview_prompt()))
    assert "questions" in payload
    assert payload is not llm_service._MOCK_AGENT_INTERVIEW
    assert "basic_info" not in payload


# ---------------------------------------------------------------- 2. 载荷过复核


def test_mock_redline_edits_all_survive_server_review():
    sections = build_report_sections(llm_service._MOCK_RESUME)
    redline, rejected = validate_redline_edits(sections, llm_service._MOCK_REPORT_REDLINE, KNOWN_TEXT)
    assert rejected == []
    assert redline is not None
    assert redline.total == len(llm_service._MOCK_REPORT_REDLINE["edits"])
    # §4：两档都要给。只出 key 的载荷演示不了"关键/普通"那两种底色。
    assert redline.key_total and redline.total - redline.key_total


def test_mock_redline_marks_are_contiguous_and_notes_are_named():
    sections = build_report_sections(llm_service._MOCK_RESUME)
    redline, _ = validate_redline_edits(sections, llm_service._MOCK_REPORT_REDLINE, KNOWN_TEXT)
    assert [edit.mark for edit in redline.edits] == list(range(1, redline.total + 1))
    assert all(edit.note for edit in redline.edits)


def test_mock_redline_adoption_writes_back_and_skips_field_blocks():
    """采纳这条路要在 mock 世界里真走得通：可写块落进简历，字段块（技术栈）不落。"""
    sections = build_report_sections(llm_service._MOCK_RESUME)
    redline, _ = validate_redline_edits(sections, llm_service._MOCK_REPORT_REDLINE, KNOWN_TEXT)
    proposals = redline.edits_for_apply()
    assert {p["block_id"] for p in proposals} == {"work[0].desc", "proj[0].desc", "skills", "self_evaluation"}

    new_parsed, applied, rejected = apply_block_edits(llm_service._MOCK_RESUME, proposals)
    assert rejected == []
    assert len(applied) == len(proposals)
    assert "部署：Docker" in "、".join(new_parsed["skills"])
    assert new_parsed["work_experience"][0]["desc"].startswith("负责招聘平台【待补")
    # 一个块里两处批改要一起落进同一段文本，不能后者把前者覆盖掉。
    proj_desc = new_parsed["project_experience"][0]["desc"]
    assert "字段口径与切片策略" in proj_desc and "由你负责的那一段的量与口径" in proj_desc
    # 技术栈那一栏是字段值：批注上屏，但 parsed_json 里没有对应的可写字段。
    assert new_parsed["project_experience"][0]["tech"] == llm_service._MOCK_RESUME["project_experience"][0]["tech"]


def test_mock_interview_questions_all_survive_server_review():
    questions, rejected = validate_interview_questions(llm_service._MOCK_REPORT_INTERVIEW, KNOWN_TEXT)
    assert rejected == []
    assert len(questions) == len(llm_service._MOCK_REPORT_INTERVIEW["questions"])
    assert [q["no"] for q in questions] == list(range(1, len(questions) + 1))


def test_mock_interview_covers_every_kind_and_every_followup_atom():
    """题型与追问标签的白名单是分布条的分组键：夹具漏一类，页面上那一类就是空的。"""
    questions, _ = validate_interview_questions(llm_service._MOCK_REPORT_INTERVIEW, KNOWN_TEXT)
    kinds = {q["kind"] for q in questions}
    assert kinds == {"基础概念", "项目深挖", "对比权衡", "踩坑与边界", "场景设计"}

    atoms: set[str] = set()
    for question in questions:
        for follow in question["followups"]:
            atoms.update(part.strip() for part in follow["kind"].split("/"))
    assert atoms == set(FOLLOWUP_ATOMS)


def test_mock_interview_defers_nothing_but_names_every_gap():
    """需补强必须点名缺的是哪个数，否则这一档就只是一句装饰。"""
    questions, _ = validate_interview_questions(llm_service._MOCK_REPORT_INTERVIEW, KNOWN_TEXT)
    weak = [q for q in questions if q["status"] == "需补强"]
    assert weak and all(q["missing"] for q in weak)
    assert all(q["missing"] == [] for q in questions if q["status"] == "可答")
    # 每个项目都要有题：这份 mock 简历只有一个项目，另一档必须是通用。
    projects = {q["project"] for q in questions}
    assert "通用" in projects and len(projects) > 1


# ---------------------------------------------------------------- 3. 措辞与事实


def _all_mock_strings() -> list[str]:
    texts: list[str] = []
    for payload in (llm_service._MOCK_REPORT_REDLINE, llm_service._MOCK_REPORT_INTERVIEW):
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, str):
                texts.append(node)
    return texts


def test_mock_payloads_carry_no_forbidden_wordings():
    for text in _all_mock_strings():
        assert not [word for word in FORBIDDEN_MECHANISM_WORDS + FORBIDDEN_ELLIPSIS if word in text], text[:40]


def test_mock_payloads_are_marked_as_fixtures():
    """除 `ins` 之外每个字段都带 `（mock）`：下载报告要能被机检认出是夹具，
    也没人会把演示文案当成真分析投出去。`ins` 是唯一的例外——它会被"采纳"
    原样写回简历正文，带标记的简历文本没人能用，所以标记留在同一批注的 `note` 上。"""
    for edit in llm_service._MOCK_REPORT_REDLINE["edits"]:
        assert edit["note"].startswith("（mock）")
        assert "（mock）" not in edit["ins"]
        assert "（mock）" not in edit["del"]

    for question in llm_service._MOCK_REPORT_INTERVIEW["questions"]:
        for field in ("question", "answer"):
            assert question[field].startswith("（mock）")
        for follow in question["followups"]:
            assert follow["text"].startswith("（mock）")
