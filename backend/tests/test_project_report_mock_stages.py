"""mock 世界里的单项目分析：派发对不对、四支载荷过不过真复核。

与 `test_resume_report_mock_stages.py` 同一族理由（D231）：`LLM_PROVIDER=mock` 是本仓库的
开发态与演示态，四支里任何一支没有 mock 载荷，那一节在演示环境里就整块不见——
那已经不是"降级不伪造"，而是这件交付物看不到。

这里守三条：
1. **派发顺序**：项目报告的四支必须排在智能体那一段之前，且四个关键字互不吞并；
2. **载荷真能过复核**：扣分点必须锚定、图与表里的数字必须来自那条项目原文、
   两轮追问与三态齐不齐——项目原文一改，这一发就该红，而不是等演示当天发现少一节；
3. **渲染与交付前机检**：四支都过了复核的那一份，必须能渲出一份过机检的 HTML。
"""

from __future__ import annotations

import json

from app.prompts.project_report_advice import PROJECT_REPORT_ADVICE_PROMPT
from app.prompts.project_report_diagrams import PROJECT_REPORT_DIAGRAMS_PROMPT
from app.prompts.project_report_profile import PROJECT_REPORT_PROFILE_PROMPT
from app.prompts.project_report_questions import PROJECT_REPORT_QUESTIONS_PROMPT
from app.prompts.rendering import render_prompt
from app.services import llm_service
from app.services import project_report_service as svc
from app.services.project_report_html import render_project_report_html
from app.services.project_report_schema import ProjectReport, build_project_excerpt, excerpt_text

ENTRY = llm_service._MOCK_RESUME["project_experience"][0]
EXCERPT = build_project_excerpt(ENTRY, 0)
BODY = excerpt_text(EXCERPT)
RAW = svc.raw_entry_text(ENTRY)


def _payload(mock_text: str) -> dict:
    return json.loads(mock_text.strip().strip("`").removeprefix("json").strip())


def _profile_prompt() -> str:
    return render_prompt(
        PROJECT_REPORT_PROFILE_PROMPT,
        jd_text="未指定目标岗位",
        project_name=EXCERPT["name"],
        project_role=EXCERPT["role"],
        project_period="（原文没有写起止时间）",
        project_tech="、".join(EXCERPT["tech"]),
        project_excerpt=BODY,
        peer_projects_json="[]",
        rubric_block=svc.rubric.rubric_prompt_block(),
        red_line_block=svc.rubric.red_line_prompt_block(),
        difficulty_block=svc.rubric.difficulty_prompt_block(),
    )


def _diagrams_prompt() -> str:
    return render_prompt(
        PROJECT_REPORT_DIAGRAMS_PROMPT,
        project_name=EXCERPT["name"],
        project_role=EXCERPT["role"],
        project_tech="、".join(EXCERPT["tech"]),
        project_excerpt=BODY,
        difficulty_level="L3",
        difficulty_reason="（mock）两段链路",
        score_block="- 指标责任：8/19",
        risk_block="1. 只有绝对值没有前后对比",
    )


def _advice_prompt() -> str:
    return render_prompt(
        PROJECT_REPORT_ADVICE_PROMPT,
        project_name=EXCERPT["name"],
        project_tech="、".join(EXCERPT["tech"]),
        project_excerpt=BODY,
        difficulty_level="L3",
        difficulty_reason="（mock）两段链路",
        score_block="- 指标责任：8/19",
        risk_block="1. 只有绝对值没有前后对比",
        pending_block="【待补：成功率差值】",
    )


def _questions_prompt() -> str:
    return render_prompt(
        PROJECT_REPORT_QUESTIONS_PROMPT,
        project_name=EXCERPT["name"],
        project_role=EXCERPT["role"],
        project_tech="、".join(EXCERPT["tech"]),
        project_excerpt=BODY,
        difficulty_level="L3",
        score_block="- 指标责任：8/19",
        risk_block="1. 只有绝对值没有前后对比",
        risk_total=1,
        hook_block="- 为什么回查放在生成之后",
        target_position="AI 应用后端",
        kind_block="- 背景与定位",
        followup_atoms="、".join(sorted(svc.FOLLOWUP_ATOMS)),
    )


def _report_from_mocks() -> ProjectReport:
    profile, profile_rejected = svc.validate_profile(_payload(llm_service._mock_chat(_profile_prompt())), 0, RAW, [])
    assert profile_rejected == []
    report = ProjectReport(resume_id=1, project_index=0, report_date="2026-10-14")
    report.excerpt = EXCERPT
    report.portrait = profile["portrait"]
    report.dimensions = profile["dimensions"]
    report.difficulty = profile["difficulty"]
    report.highlights = profile["highlights"]
    report.hooks = profile["hooks"]
    report.risks = profile["risks"]
    report.total_score = svc.rubric.total_of(report.dimensions)
    report.grade = svc.rubric.grade_of(report.total_score)
    report.grade_scale = svc.rubric.grade_scale_block()
    report.contribution = svc.compute_contribution(0, report.total_score, [])
    diagrams, diagram_rejected = svc.validate_diagrams(_payload(llm_service._mock_chat(_diagrams_prompt())), BODY)
    assert diagram_rejected == [] and diagrams is not None
    report.diagrams = diagrams
    advice, advice_rejected = svc.validate_advice(_payload(llm_service._mock_chat(_advice_prompt())), report)
    assert advice_rejected == [] and advice is not None
    report.advice = advice
    items, distribution, question_rejected = svc.validate_questions(
        _payload(llm_service._mock_chat(_questions_prompt())), RAW, len(report.risks)
    )
    assert question_rejected == []
    report.questions = {
        "deferred": False,
        "note": "",
        "questions": items,
        "distribution": distribution,
        "practice": svc.practice_backfill(items),
    }
    return report


def test_each_project_prompt_is_claimed_by_its_own_payload():
    expected = {
        _profile_prompt(): "portrait",
        _diagrams_prompt(): "function_arch",
        _advice_prompt(): "citation",
        _questions_prompt(): "questions",
    }
    for prompt, key in expected.items():
        assert key in _payload(llm_service._mock_chat(prompt))


def test_dispatch_happens_before_the_agent_keywords():
    # 项目报告的 prompt 里有"资深"/"专家"式角色行；派发若排在智能体之后就会被静默领走。
    for prompt in (_profile_prompt(), _diagrams_prompt(), _advice_prompt(), _questions_prompt()):
        text = llm_service._mock_chat(prompt)
        assert "target_agents" not in text and "sub_tasks" not in text


def test_profile_dimensions_are_all_scored_and_anchored():
    profile, _ = svc.validate_profile(_payload(llm_service._mock_chat(_profile_prompt())), 0, RAW, [])
    scored = [row for row in profile["dimensions"] if not row["positional"]]
    assert len(scored) == 5 and all(row["score"] is not None for row in scored)
    assert profile["anchor_stats"]["unanchored_keys"] == []
    assert profile["excluded_by"] == []
    assert profile["difficulty"]["level"] in {row[0] for row in svc.rubric.DIFFICULTY_BANDS}


def test_mock_payloads_declare_themselves_as_fixtures():
    for name in ("_MOCK_PROJECT_PROFILE", "_MOCK_PROJECT_DIAGRAMS", "_MOCK_PROJECT_ADVICE", "_MOCK_PROJECT_QUESTIONS"):
        blob = json.dumps(getattr(llm_service, name), ensure_ascii=False)
        assert "（mock）" in blob, name


def test_diagram_numbers_all_come_from_the_mock_resume_project():
    diagrams, rejected = svc.validate_diagrams(_payload(llm_service._mock_chat(_diagrams_prompt())), BODY)
    assert rejected == []
    assert diagrams["figures"] == list(svc.DIAGRAM_KEYS)
    assert all(len(diagrams[key]["deep_dive"]) >= 2 for key in svc.DIAGRAM_KEYS)


def test_advice_expected_column_names_a_dimension():
    report = _report_from_mocks()
    for row in report.advice["strengthen"]:
        assert svc.rubric.mentions_dimension(row["expected"])
    assert report.advice["level"] == report.difficulty["level"]


def test_questions_cover_every_kind_and_keep_two_followups():
    report = _report_from_mocks()
    distribution = report.questions["distribution"]
    assert set(distribution["by_kind"]) == set(svc.QUESTION_KINDS)
    assert distribution["total"] == len(report.questions["questions"])
    assert distribution["high_risk"] == 1
    assert all(len(item["followups"]) == svc.FOLLOWUP_COUNT for item in report.questions["questions"])
    assert report.questions["practice"]["high_risk"] == "Q4"


def test_the_mock_report_renders_and_passes_the_delivery_lint():
    document = render_project_report_html(_report_from_mocks())
    assert "一、项目档案" in document and "四、面试准备" in document
    assert "共 8 题" in document
