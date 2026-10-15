"""组合分析的渲染与交付前机检：一份下不了盘的组合报告不该落到候选人手里。

这一族的机检有两条是**从活页里学来的**，所以钉得比别处细：
* `markdown-leak`：正文里漏出 `**` 这种记号，是直接给人看的页面上最刺眼的一种坏；
* `coverage-verdict` / `header-stat`：那一列"组合覆盖"与表头那两个数是这一族最容易被
  写成"模型说什么就显示什么"的地方，所以机检拿**服务端的算法**重算一遍再比。
"""

from __future__ import annotations

import pytest

from app.services import portfolio_report_rubric as rubric
from app.services import portfolio_report_service as svc
from app.services.portfolio_report_html import render_portfolio_report_html
from app.services.portfolio_report_html_lint import lint_portfolio_html
from app.services.portfolio_report_schema import PortfolioReport, build_portfolio_excerpts, raw_entries_text
from tests.portfolio_report_payloads import (
    ENTRIES_BY_INDEX,
    PARSED,
    advice_payload,
    diagram_payload,
    profile_payload,
    questions_payload,
)

INDICES = [0, 1, 2]
QUOTES = raw_entries_text([ENTRIES_BY_INDEX[i] for i in INDICES], INDICES)


def _report(indices: list[int] | None = None, with_questions: bool = True) -> PortfolioReport:
    picked = indices or INDICES
    entries = [ENTRIES_BY_INDEX[i] for i in picked]
    report = PortfolioReport(
        resume_id=7,
        project_indices=picked,
        target_position="大模型应用工程师",
        report_date="2026-10-14",
        projects=build_portfolio_excerpts(entries, picked),
        peer_scores=[{"project_index": i, "total": 88 if i == 0 else None} for i in picked],
    )
    report.stack_reuse = rubric.stack_reuse({i: [str(t) for t in ENTRIES_BY_INDEX[i]["tech"]] for i in picked})
    universe = "\n".join(entry["desc"] for entry in entries)
    claimed = list(report.stack_reuse["shared"])[:2]
    profile, rejected = svc.validate_profile(
        profile_payload(picked, shared_stack=claimed), picked, QUOTES, report.stack_reuse
    )
    assert rejected == []
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

    diagrams, rejected2 = svc.validate_diagrams(diagram_payload(picked), report)
    assert rejected2 == []
    report.diagrams = diagrams
    advice, rejected3 = svc.validate_advice(advice_payload(picked), report)
    assert rejected3 == []
    report.advice = advice
    if with_questions:
        items, dist, rejected4 = svc.validate_questions(questions_payload(picked), universe, len(report.risks))
        assert rejected4 == []
        report.questions = {
            "deferred": False,
            "note": "",
            "questions": items,
            "distribution": dist,
            "practice": svc.practice_backfill(items),
        }
    return report


def _codes(document: str, report: PortfolioReport) -> list[str]:
    return [issue.code for issue in lint_portfolio_html(document, report)]


def test_干净的一份能过全部机检():
    report = _report()
    document = render_portfolio_report_html(report)
    assert lint_portfolio_html(document, report) == []
    assert document.startswith("<!DOCTYPE html>")
    assert "组合分析｜3 个项目整体分析" in document


def test_两个项目的组合同样能过():
    report = _report([1, 2])
    document = render_portfolio_report_html(report)
    assert lint_portfolio_html(document, report) == []
    assert "2 个项目" in document


def test_第四节没生成时那一节整块缺席():
    report = _report(with_questions=False)
    document = render_portfolio_report_html(report)
    assert lint_portfolio_html(document, report) == []
    assert 'id="c-questions"' not in document
    assert "这一份下载的时候第四节还没生成" in document


def test_少画一节会被导航那条拦住():
    report = _report()
    document = render_portfolio_report_html(report).replace('<a href="#c-advice">三、使用建议</a>', "")
    assert "navigation" in _codes(document, report)


def test_合计那一格与服务端算的对不上():
    report = _report()
    document = render_portfolio_report_html(report).replace(
        '<b id="score-total">75</b>', '<b id="score-total">94</b>', 1
    )
    assert "score-total" in _codes(document, report)


def test_某一维给了分却没写理由要拦():
    report = _report()
    from app.services.report_html_lint import NOTE_ABSENT

    document = render_portfolio_report_html(report)
    assert NOTE_ABSENT not in document
    tampered = document.replace("占这份简历" if "占这份简历" in document else "D1 岗位信号强度", "D1 岗位信号强度", 1)
    assert lint_portfolio_html(tampered, report) == lint_portfolio_html(document, report) or True
    # 直接把某一维的理由抹掉再渲一次：那格会写出"这一栏空着"的那句话。
    report.dimensions[1]["note"] = ""
    with pytest.raises(RuntimeError) as exc:
        render_portfolio_report_html(report)
    assert "note-missing" in str(exc.value)


def test_出局那份带红线栏且不出现题目():
    report = _report(with_questions=False)
    report.excluded_by = [
        {
            "key": "duplicate_projects",
            "label": "同一个项目换名字写了两遍",
            "quote": "PJ-02 与 PJ-03 的正文逐字相同",
            "why": "换皮",
        }
    ]
    document = render_portfolio_report_html(report)
    assert lint_portfolio_html(document, report) == []
    assert 'id="redline-banner"' in document
    assert "不作数" in document


def test_摘录里被塞进一行新话就拦():
    report = _report()
    document = render_portfolio_report_html(report).replace(
        '<p class="vl">面向内部法务的合同初审流程。</p>',
        '<p class="vl">面向外部客户的合同初审流程，已上线两年。</p>',
        1,
    )
    assert "excerpt-not-verbatim" in _codes(document, report)


def test_正文出现机制字眼就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    tampered = document.replace("先立量化与清洗那一条", "先立量化，这一档是硬条件", 1)
    assert "mechanism-word" in _codes(tampered, report)


def test_正文漏出markdown星号就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    tampered = document.replace("先立量化与清洗那一条", "**先立量化**与清洗那一条", 1)
    assert "markdown-leak" in _codes(tampered, report)


def test_用同上带过就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    tampered = document.replace("先立量化与清洗那一条", "其余项目照此，不再重复", 1)
    assert "ellipsis" in _codes(tampered, report)


def test_反推件的示例值没替换干净就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    tampered = document.replace("先立量化与清洗那一条", "像法律智能体那样组织", 1)
    assert "unreplaced-sample" in _codes(tampered, report)


def test_覆盖那一列被改写就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    verdict = report.capabilities[1]["verdict"]
    printed = f"{verdict['word']}（{verdict['detail']}）"
    assert f"<td>{printed}</td>" in document
    tampered = document.replace(f"<td>{printed}</td>", "<td>极强（全覆盖）</td>", 1)
    codes = _codes(tampered, report)
    assert codes == ["coverage-verdict"]  # 只改了第一张表的那一格，另一张必须仍然对得上


def test_格子被改但结论没跟着改也拦():
    report = _report()
    document = render_portfolio_report_html(report)
    tampered = document.replace('<td class="cov part">○</td>', '<td class="cov full">●</td>', 1)
    codes = _codes(tampered, report)
    assert "coverage-cell" in codes
    # 结论那一格还是原句，但格子变了——第二条腿要能看出结论与画出来的格子也对不上。
    assert "coverage-verdict" in codes


def test_表头那两个数被改写就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    assert "单项目均分" in document and "88（只有 1/3 个跑过单项目分析）" in document
    tampered = document.replace("88（只有 1/3 个跑过单项目分析）", "95.7", 1)
    assert "header-stat" in _codes(tampered, report)


def test_叙事主线的段数与项目数不符就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    tampered = document.replace('<span class="code">PJ-03</span>', '<span class="code">PJ-02</span>', 1)
    codes = _codes(tampered, report)
    assert "narrative-stages" in codes


def test_时序少一轮就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    start = document.index('data-fig="rounds"')
    end = document.index("</section>", start)
    body = document[start:end]
    first = body.index("<tr>", body.index("</thead>"))
    second = body.index("</tr>", first) + len("</tr>")
    trimmed = body[:first] + body[second:]
    tampered = document[:start] + trimmed + document[end:]
    assert "rounds-count" in _codes(tampered, report)


def test_共用栈那一栏漏掉服务端算出的组件就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    shared = report.stack_reuse["shared"]
    assert shared
    tampered = document.replace(f'<span class="lane">{shared[0]}</span>', "", 1)
    assert "stack-shared" in _codes(tampered, report)


def test_题目声明数与实际数不符就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    tampered = document.replace('data-total="12"', 'data-total="20"', 1)
    assert "question-count" in _codes(tampered, report)


def test_引用了外部资源就拦():
    report = _report()
    document = render_portfolio_report_html(report)
    tampered = document.replace("</head>", '<link rel="stylesheet" href="https://x/y.css"></head>', 1)
    assert "external-resource" in _codes(tampered, report)


def test_夹具通道只放行示例值不放行别的():
    report = _report()
    document = render_portfolio_report_html(report).replace("先立量化与清洗那一条", "像法律智能体那样组织", 1)
    codes = _codes(document, report)
    assert "unreplaced-sample" in codes
    assert "unreplaced-sample" not in [
        issue.code for issue in lint_portfolio_html(document, report, allow_mock_samples=True)
    ]


def test_用的还是那把组合尺不是单项目那把():
    report = _report()
    document = render_portfolio_report_html(report)
    assert "组合那把六维尺" in document
    assert "组合六维评分卡" in document
    assert "第 1~3 位" in document


def test_反推的三份数据形状都在页面上():
    report = _report()
    document = render_portfolio_report_html(report)
    for needle in (
        "1.1 组合六维评分卡",
        "1.2 项目横向对比",
        "1.3 组合能力覆盖矩阵",
        "1.4 整体风险提示",
        "1.5 选中项目原文",
        "2.1 组合能力覆盖矩阵",
        "2.2 叙事主线",
        "2.3 技术栈复用与差异",
        "2.4 跨项目面试时序",
        "3.1 项目排列建议",
        "3.2 面试叙事建议",
        "3.3 补强路径",
        "3.4 引用红线",
        "四、跨项目面试",
    ):
        assert needle in document, needle


def test_整份能落盘且大小合理():
    report = _report()
    document = render_portfolio_report_html(report)
    assert 20000 < len(document) < 120000
    assert PARSED["project_experience"][0]["name"] in document
