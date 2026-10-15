"""mock 世界里的组合分析：派发对不对、四支载荷过不过真复核、几个项目数都长得起来。

与单项目那一族同一族理由（D231）：`LLM_PROVIDER=mock` 是本仓库的开发态与演示态，
四支里任何一支没有 mock 载荷，那一节在演示环境里就整块不见——那已经不是"降级不伪造"，
而是这件交付物看不到。

这里守四条：
1. **派发各领各支**：组合那四支的关键字必须各归各的，且排在智能体段之前；
2. **载荷现读项目清单**：两个项目给两段、三个项目给三段——写死两个项目的夹具
   在第三个项目进来时会自己造出假阳性；
3. **真复核零拒因**：扣分点锚定、表与图里的数字来自原文、五轮与每题两轮追问齐；
4. **渲得出、过得了机检**，而且 mock 那份不许把项目之外的数字带进正文。
"""

from __future__ import annotations

import json

from app.prompts.portfolio_report_advice import PORTFOLIO_REPORT_ADVICE_PROMPT
from app.prompts.portfolio_report_diagrams import PORTFOLIO_REPORT_DIAGRAMS_PROMPT
from app.prompts.portfolio_report_profile import PORTFOLIO_REPORT_PROFILE_PROMPT
from app.prompts.portfolio_report_questions import PORTFOLIO_REPORT_QUESTIONS_PROMPT
from app.prompts.rendering import render_prompt
from app.services import llm_service
from app.services import portfolio_report_rubric as rubric
from app.services import portfolio_report_service as svc
from app.services.portfolio_report_html import render_portfolio_report_html
from app.services.portfolio_report_schema import (
    PortfolioReport,
    build_portfolio_excerpts,
    raw_entries_text,
    universe_text,
)
from tests.portfolio_report_payloads import ENTRIES_BY_INDEX

INDICES = [0, 1, 2]
BLOCKS = {
    "组合分析 · 一、组合档案": "summary",
    "组合分析 · 二、组合图解": "narrative",
    "组合分析 · 三、使用建议": "arrangements",
    "组合分析 · 四、跨项目面试": "questions",
}


def _payload(mock_text: str) -> dict:
    return json.loads(mock_text.strip().strip("`").removeprefix("json").strip())


def _projects_block(indices: list[int]) -> str:
    return svc._projects_block(build_portfolio_excerpts([ENTRIES_BY_INDEX[i] for i in indices], list(indices)))


def _report(indices: list[int]) -> PortfolioReport:
    report = PortfolioReport(
        resume_id=3,
        project_indices=list(indices),
        target_position="大模型应用工程师",
        report_date="2026-10-14",
        projects=build_portfolio_excerpts([ENTRIES_BY_INDEX[i] for i in indices], list(indices)),
        peer_scores=[{"project_index": i, "total": 88 if i == 0 else None} for i in indices],
    )
    report.stack_reuse = rubric.stack_reuse({i: [str(t) for t in ENTRIES_BY_INDEX[i]["tech"]] for i in indices})
    texts = {i: universe_text(build_portfolio_excerpts([ENTRIES_BY_INDEX[i]], [i])) for i in indices}
    report.duplicate_evidence = rubric.duplicate_pairs(texts) + rubric.near_copy_pairs(texts)
    report.per_project_metric_gaps = rubric.metric_gaps_by_project(texts)
    return report


def _run(indices: list[int]) -> PortfolioReport:
    """把四支 mock 依次喂进**真复核**：任何一支有拒因，这一发就该红。"""
    report = _report(indices)
    universe = raw_entries_text([ENTRIES_BY_INDEX[i] for i in indices], list(indices))
    block = _projects_block(indices)

    profile_prompt = render_prompt(
        PORTFOLIO_REPORT_PROFILE_PROMPT,
        jd_text="未指定目标岗位",
        projects_block=block,
        server_facts_block=svc._facts_block(report, report.stack_reuse),
        rubric_block=rubric.rubric_prompt_block(),
        red_line_block=rubric.red_line_prompt_block(),
        difficulty_block=rubric.difficulty_prompt_block(),
        compare_row_keys="、".join(rubric.COMPARE_ROW_KEYS),
        capability_keys="、".join(rubric.CAPABILITY_KEYS),
    )
    profile, rejected = svc.validate_profile(
        _payload(llm_service._mock_chat(profile_prompt)), list(indices), universe, report.stack_reuse
    )
    assert rejected == [], rejected
    report.summary = profile["summary"]
    report.dimensions = profile["dimensions"]
    report.difficulty = profile["difficulty"]
    report.compare = {"rows": profile["compare"]}
    report.capabilities = profile["capabilities"]
    report.risks = profile["risks"]
    report.total_score = rubric.total_of(report.dimensions)
    report.grade = rubric.grade_of(report.total_score)
    report.grade_desc = rubric.grade_desc_of(report.total_score)
    report.grade_scale = rubric.grade_scale_block()

    diagram_prompt = render_prompt(
        PORTFOLIO_REPORT_DIAGRAMS_PROMPT,
        projects_block=block,
        score_block=svc._score_block(report),
        risk_block=svc._risk_block(report.risks),
        stack_block=svc._stack_block(report),
        round_keys="、".join(rubric.INTERVIEW_ROUND_KEYS),
    )
    diagrams, rejected2 = svc.validate_diagrams(_payload(llm_service._mock_chat(diagram_prompt)), report)
    assert rejected2 == [], rejected2
    report.diagrams = diagrams

    advice_prompt = render_prompt(
        PORTFOLIO_REPORT_ADVICE_PROMPT,
        projects_block=block,
        score_block=svc._score_block(report),
        risk_block=svc._risk_block(report.risks),
        pending_block="（档案里没有留下【待补】的数）",
        index_list="、".join(str(i) for i in indices),
    )
    advice, rejected3 = svc.validate_advice(_payload(llm_service._mock_chat(advice_prompt)), report)
    assert rejected3 == [], rejected3
    report.advice = advice

    question_prompt = render_prompt(
        PORTFOLIO_REPORT_QUESTIONS_PROMPT,
        projects_block=block,
        score_block=svc._score_block(report),
        risk_block=svc._risk_block(report.risks),
        risk_total=len(report.risks),
        compare_block=svc._compare_block(report),
        target_position="大模型应用工程师",
        kind_block="\n".join(f"- {kind}" for kind in rubric.QUESTION_KINDS),
        followup_atoms="、".join(sorted(svc.FOLLOWUP_ATOMS)),
    )
    items, dist, rejected4 = svc.validate_questions(
        _payload(llm_service._mock_chat(question_prompt)), universe, len(report.risks)
    )
    assert rejected4 == [], rejected4
    report.questions = {
        "deferred": False,
        "note": "",
        "questions": items,
        "distribution": dist,
        "practice": svc.practice_backfill(items),
    }
    return report


def test_四个关键字各领各的那一支():
    for marker, expected in BLOCKS.items():
        document = llm_service._mock_chat(f"本次任务（{marker}）\n" + _projects_block([0, 1]))
        assert expected in _payload(document), marker


def test_智能体的角色行不会把组合那四支领走():
    # D231 那条教训的另一半：这四支必须排在智能体段之前，否则形状完全不同还不报错。
    prompt = "你是资深简历诊断专家。\n本次任务：组合分析 · 一、组合档案\n" + _projects_block([0, 1])
    assert "summary" in _payload(llm_service._mock_chat(prompt))


def test_三个项目的组合四支都过真复核():
    report = _run(INDICES)
    assert len(report.compare["rows"]) == 7
    assert len(report.capabilities) == 5
    assert len(report.diagrams["narrative"]["stages"]) == 3
    assert len(report.diagrams["rounds"]) == 5
    assert report.questions["distribution"]["total"] == 12
    assert report.questions["distribution"]["answerable"] == 11
    assert report.questions["distribution"]["weak"] == 1


def test_两个项目的组合同样起得来():
    report = _run([0, 1])
    assert len(report.diagrams["narrative"]["stages"]) == 2
    assert all(len(row["cells"]) == 2 for row in report.compare["rows"])
    assert all(len(row["cells"]) == 2 for row in report.capabilities)
    assert report.capabilities[0]["verdict"]["word"] == "极强"


def test_mock那份渲得出且过得了机检():
    report = _run(INDICES)
    document = render_portfolio_report_html(report)
    assert "组合分析｜3 个项目整体分析" in document
    assert "（mock）" in document


def test_mock载荷里每一句人话写的数字都得能在原文里逐字找到():
    """这一族的 mock 有数字（"30 - 60 分钟缩短至 5 - 10 分钟"、"1200 余份"、"2 小时"、"9.3%"），
    它们全部是从被选中项目原文里 lifted 来的。这一条钉的是 lift 这件事本身：
    哪天 fixture 里冒出一个原文没有的百分比，这里就该红——而不是等真复核在演示当天拦人。

    结构位不参与：`score` 与 `project_index` 是给服务端读的数，`expected` 是
    "对我们自己那张六维表的说法"（与生产代码同一份豁免，见 `number_violations`）。
    """
    universe = raw_entries_text([ENTRIES_BY_INDEX[i] for i in INDICES], INDICES)
    known = json.dumps({"entry": universe}, ensure_ascii=False)
    block = _projects_block(INDICES)
    report = _report(INDICES)
    prompts = (
        render_prompt(
            PORTFOLIO_REPORT_PROFILE_PROMPT,
            jd_text="未指定",
            projects_block=block,
            server_facts_block=svc._facts_block(report, report.stack_reuse),
            rubric_block=rubric.rubric_prompt_block(),
            red_line_block=rubric.red_line_prompt_block(),
            difficulty_block=rubric.difficulty_prompt_block(),
            compare_row_keys="、".join(rubric.COMPARE_ROW_KEYS),
            capability_keys="、".join(rubric.CAPABILITY_KEYS),
        ),
        render_prompt(
            PORTFOLIO_REPORT_DIAGRAMS_PROMPT,
            projects_block=block,
            score_block=svc._score_block(report),
            risk_block=svc._risk_block(report.risks),
            stack_block=svc._stack_block(report),
            round_keys="、".join(rubric.INTERVIEW_ROUND_KEYS),
        ),
        render_prompt(
            PORTFOLIO_REPORT_ADVICE_PROMPT,
            projects_block=block,
            score_block=svc._score_block(report),
            risk_block=svc._risk_block(report.risks),
            pending_block="（无）",
            index_list="、".join(str(i) for i in INDICES),
        ),
        render_prompt(
            PORTFOLIO_REPORT_QUESTIONS_PROMPT,
            projects_block=block,
            score_block=svc._score_block(report),
            risk_block=svc._risk_block(report.risks),
            risk_total=3,
            compare_block=svc._compare_block(report),
            target_position="大模型应用工程师",
            kind_block="、".join(rubric.QUESTION_KINDS),
            followup_atoms="、".join(sorted(svc.FOLLOWUP_ATOMS)),
        ),
    )
    exempt = {"project_index", "score", "expected", "no", "source", "cell", "row", "key", "level", "capability"}
    bad: list[str] = []

    def walk(node: object, key: str = "") -> None:
        if isinstance(node, str):
            if key in exempt:
                return
            hits = svc.invented_numbers(node, known)
            if hits:
                bad.append(f"{key}：{node[:28]} → {hits[:3]}")
        elif isinstance(node, dict):
            for name, child in node.items():
                walk(child, name)
        elif isinstance(node, list):
            for child in node:
                walk(child, key)

    for prompt in prompts:
        walk(_payload(llm_service._mock_chat(prompt)))
    assert bad == []
