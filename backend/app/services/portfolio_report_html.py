"""把一份组合分析渲染成自包含 HTML（`docs/portfolio-report-spec.md` §8）。

三条与本族同源、但这一族各自成立的约束：

* **所有来自候选人与模型的文本都先 `html.escape`**，结构标签由本模块自己发；
* **产出前过一遍 `portfolio_report_html_lint`**：坏掉的那一份不落盘；
* 样式与页内脚本全部内联，零外部资源——离线双击可开是这份交付物的定义。

两处与单项目那一族**故意不同**的形状，理由写在规范里：
1. **表头多一格「单项目均分」**，一份都没跑过时那一格写那句人话而不是猜一个数；
2. **1.3 的「组合覆盖」那一列与 2.3 的两栏技术栈全部由数据画出来**，
   模型在这两处一个字都不占——它是组合层最容易自我表扬的地方。

第四节还没生成时整块缺席（导航里也不留那一栏）：给候选人一个空壳的"四、跨项目面试"
比不给更坏，他会以为系统看过了、只是没写。
"""

from __future__ import annotations

import html
import re
from typing import Any

from app.services import portfolio_report_rubric as rubric
from app.services.portfolio_report_html_lint import SECTIONS, format_issues, lint_portfolio_html
from app.services.portfolio_report_schema import (
    EXCLUDED_NOTE,
    QUESTIONS_DEFERRED,
    QUESTIONS_NOT_GENERATED,
    QUESTIONS_READY,
    PortfolioReport,
    project_label,
)
from app.services.report_html_lint import NOTE_ABSENT, THREE_RUBRICS_NOTE

TITLE = "组合分析"
_TODO = re.compile(r"(【待补[^】]*】)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")

FIGURE_TITLES = {
    "coverage": "2.1 组合能力覆盖矩阵",
    "narrative": "2.2 叙事主线",
    "stack": "2.3 技术栈复用与差异",
    "rounds": "2.4 跨项目面试时序",
}


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def _todo(value: Any) -> str:
    return _TODO.sub(r'<span class="todo">\1</span>', _e(value))


def _inline(value: Any) -> str:
    escaped = _todo(value)
    return _BOLD.sub(r"<b>\1</b>", escaped.replace("\n", "<br>"))


def _cell(text: str, tag: str = "td", klass: str = "") -> str:
    return f'<{tag} class="{klass}">{text}</{tag}>' if klass else f"<{tag}>{text}</{tag}>"


def _row(cells: list[str], klass: str = "") -> str:
    return (f'<tr class="{klass}">' if klass else "<tr>") + "".join(cells) + "</tr>"


def _table(headers: list[str], rows: list[str], klass: str = "tbl") -> str:
    if not rows:
        return ""
    head = _row([_cell(_e(name), "th") for name in headers], "hd")
    return f'<table class="{klass}"><thead>{head}</thead><tbody>' + "".join(rows) + "</tbody></table>"


def _kv_table(pairs: list[tuple[str, Any]]) -> str:
    rows = [_row([_cell(f"<b>{_e(key)}</b>"), _cell(_inline(value))]) for key, value in pairs]
    return _table(["项", "内容"], rows)


def _ordered_indices(report: PortfolioReport) -> list[int]:
    return [int(excerpt.get("project_index") or 0) for excerpt in report.projects]


# ------------------------------------------------------------------ 表头与导航
def _nav(present: list[str]) -> str:
    links = "".join(f'<a href="#{anchor}">{_e(label)}</a>' for anchor, label in SECTIONS if anchor in present)
    return f'<nav class="modnav" id="modnav">{links}</nav>'


def _pills(report: PortfolioReport) -> str:
    summary = report.summary or {}
    first, last = rubric.span_of(report.project_indices)
    items = [
        ("组合", summary.get("projects_line") or "、".join(project_label(row) for row in report.projects)),
        ("项目数", f"{report.project_count} 个（简历第 {first}~{last} 位）"),
        ("单项目均分", report.average_cell()),
        ("组合难度", report.difficulty.get("level") or "未定级"),
        ("组合评分", report.score_cell()),
    ]
    return "".join(f'<span class="pill"><b>{_e(name)}</b>{_e(value)}</span>' for name, value in items if value)


def _header(report: PortfolioReport) -> str:
    summary = report.summary or {}
    title = f"{TITLE}｜{report.project_count} 个项目整体分析"
    lines = [f'<div class="ttl">{_e(title)}</div>']
    if summary.get("common_skeleton"):
        lines.append(f'<div class="sub">共同骨架：{_e(summary["common_skeleton"])}</div>')
    if summary.get("difference_line"):
        lines.append(f'<div class="sub">差异主线：{_e(summary["difference_line"])}</div>')
    return f'<header class="top">{"".join(lines)}<div class="pills">{_pills(report)}</div></header>'


# ------------------------------------------------------------------ 一、组合档案
def _band(row: dict[str, Any]) -> str:
    if row.get("positional"):
        span = row.get("span") or [0, 0]
        if span[0] == span[1]:
            return f"第 {span[0]} 位"
        return f"第 {span[0]}~{span[1]} 位"
    if row["score"] is None:
        return "未读出来"
    ratio = row["score"] / row["full"] if row["full"] else 0
    return "优" if ratio >= 0.9 else "良" if ratio >= 0.75 else "中" if ratio >= 0.6 else "弱"


def _scorecard(report: PortfolioReport) -> str:
    rows = []
    for row in report.dimensions:
        score = "—" if row["score"] is None else str(row["score"])
        note = _todo(row["note"]) if row["note"] else f'<span class="muted">{NOTE_ABSENT}</span>'
        low = row["score"] is None or (row["full"] and row["score"] / row["full"] <= 0.7)
        rows.append(
            _row(
                [
                    _cell(f"<b>{_e(row['label'])}</b>"),
                    _cell(f"<b>{_e(score)}</b>", klass="n"),
                    _cell(f"<b>{row['full']}</b>", klass="n"),
                    _cell(_e(_band(row))),
                    _cell(note),
                ],
                "hot" if low else "",
            )
        )
    rows.append(
        _row(
            [
                _cell("合计"),
                _cell(f'<b id="score-total">{_e(report.score_cell())}</b>', klass="n"),
                _cell(f"<b>{rubric.TOTAL_FULL}</b>", klass="n"),
                _cell(_e(report.grade or ("出局" if report.is_excluded() else "—"))),
                _cell(_e(report.grade_desc) or '<span class="muted">—</span>'),
            ],
            "total",
        )
    )
    scale = (
        f'<p class="concl" id="grade-scale">评级档位：{_e(report.grade_scale)}。'
        "这一档说的是<b>这一组项目叠在一起</b>；这里的档位区间按组合口径切，"
        "同名的那一档与单项目报告里的不是同一个分数带。</p>"
    )
    return (
        "<h3>1.1 组合六维评分卡</h3>"
        + _table(["维度", "得分", "满分", "落档", "主要扣分理由"], rows, "tbl scorecard")
        + scale
    )


def _redline_banner(report: PortfolioReport) -> str:
    if not report.is_excluded():
        return ""
    rows = [
        _row(
            [
                _cell(f"<b>{_e(row['label'])}</b>"),
                _cell(f'<span class="vl">{_e(row["quote"])}</span>'),
                _cell(_inline(row["why"])),
            ]
        )
        for row in report.excluded_by
    ]
    return (
        '<div class="redline" id="redline-banner"><b>'
        + _e(EXCLUDED_NOTE)
        + "</b>"
        + _table(["命中哪一条", "逐字证据", "为什么这一条致命"], rows)
        + "</div>"
    )


def _compare_table(report: PortfolioReport) -> str:
    rows = (report.compare or {}).get("rows") or []
    if not rows:
        return ""
    indices = _ordered_indices(report)
    headers = ["对比项"] + [project_label(row) for row in report.projects]
    body = [
        _row(
            [_cell(f"<b>{_e(row['label'])}</b>")]
            + [_cell(_inline(row["cells"].get(str(index), "—"))) for index in indices]
        )
        for row in rows
    ]
    return "<h3>1.2 项目横向对比</h3>" + _table(headers, body)


def _coverage_rows(report: PortfolioReport, *, as_figure: bool) -> str:
    indices = _ordered_indices(report)
    headers = ["能力维度"] + [project_label(row) for row in report.projects] + ["组合覆盖"]
    body = []
    for row in report.capabilities:
        verdict = row.get("verdict") or {}
        mark_cells = []
        for index in indices:
            cell = row["cells"].get(index, rubric.COVER_NONE)
            mark = rubric.COVERAGE_MARKS.get(cell, "")
            klass = "cov full" if cell == rubric.COVER_FULL else "cov part" if cell == rubric.COVER_PARTIAL else "cov"
            mark_cells.append(_cell(_e(mark), klass=klass))
        tail = f"{verdict.get('word', '')}（{verdict.get('detail', '')}）" if verdict else "—"
        body.append(_row([_cell(f"<b>{_e(row['label'])}</b>")] + mark_cells + [_cell(_e(tail))]))
    if not body:
        return ""
    table = _table(headers, body, "tbl matrix")
    legend = '<p class="note"><span class="cov full">●</span> 重点覆盖　<span class="cov part">○</span> 部分覆盖　空白 未覆盖</p>'
    title = "2.1 组合能力覆盖矩阵" if as_figure else "1.3 组合能力覆盖矩阵"
    note = (
        '<p class="concl">这一列不是模型写的：由上面那一行的格子推出来——每个项目都重点覆盖才算极强。</p>'
        if not as_figure
        else '<p class="note">同一张表的格子，与 1.3 是同一个来源，这里只换一种画法。</p>'
    )
    return f"<h3>{_e(title)}</h3>" + table + legend + note


def _risk_table(report: PortfolioReport) -> str:
    if not report.risks:
        return ""
    body = [
        _row([_cell(f"<b>{_e(row['point'])}</b>"), _cell(_inline(row["detail"])), _cell(_inline(row["fix"]))])
        for row in report.risks
    ]
    return "<h3>1.4 整体风险提示</h3>" + _table(["风险点", "说明", "补齐建议"], body)


def _excerpt_blocks(report: PortfolioReport) -> str:
    blocks = []
    for excerpt in report.projects:
        lines = []
        for section in excerpt.get("sections") or []:
            lines.append(f'<p class="hd">{_e(section.get("label"))}</p>')
            lines.extend(f'<p class="vl">{_e(line)}</p>' for line in section.get("lines") or [])
        if not lines:
            lines = ['<p class="vl muted">（这一条项目没有正文可摘）</p>']
        blocks.append(
            f'<div class="paper" data-project="{_e(excerpt.get("project_index"))}">'
            f'<p class="hd"><b>{_e(project_label(excerpt))}</b>（代号 {_e(excerpt.get("code"))}）</p>'
            + "".join(lines)
            + "</div>"
        )
    if not blocks:
        return ""
    return (
        "<h3>1.5 选中项目原文（逐字摘录，未作改写）</h3>"
        '<p class="note">上面每一栏的说法都要能回到这几段字里；这一节一个字都不过模型。</p>' + "".join(blocks)
    )


def _profile_section(report: PortfolioReport) -> str:
    return (
        '<section class="card" id="c-profile"><h2 class="ct">一、组合档案</h2>'
        + _redline_banner(report)
        + _scorecard(report)
        + _compare_table(report)
        + _coverage_rows(report, as_figure=False)
        + _risk_table(report)
        + _excerpt_blocks(report)
        + "</section>"
    )


# ------------------------------------------------------------------ 二、组合图解
def _figure_narrative(report: PortfolioReport) -> str:
    narrative = (report.diagrams or {}).get("narrative") or {}
    stages = narrative.get("stages") or []
    if not stages:
        return ""
    cards = []
    for stage in stages:
        points = "".join(f"<li>{_inline(point)}</li>" for point in stage.get("points") or [])
        cards.append(
            '<div class="node">'
            f'<div class="nh">{_e(stage.get("stage_name"))}｜{_e(stage.get("label"))}'
            f'<span class="code">{_e(stage.get("code"))}</span></div>'
            f"<ul>{points}</ul>"
            f'<div class="q">核心问题：{_e(stage.get("core_question"))}</div>'
            f'<div class="how">能力关键词：{_e(stage.get("keywords"))}</div>'
            "</div>"
        )
    tail = f'<p class="concl">{_inline(narrative.get("one_line"))}</p>' if narrative.get("one_line") else ""
    title = f'<h4 class="sl">{_e(narrative.get("title"))}</h4>' if narrative.get("title") else ""
    return (
        f'<div class="fig" data-fig="narrative"><h3>{_e(FIGURE_TITLES["narrative"])}</h3>'
        + title
        + f'<div class="flow lanes-vertical">{"".join(cards)}</div>'
        + tail
        + "</div>"
    )


def _figure_stack(report: PortfolioReport) -> str:
    diagrams = report.diagrams or {}
    stack = diagrams.get("stack") or report.stack_reuse or {}
    shared = stack.get("shared") or []
    unique = stack.get("unique_by_index") or {}
    by_index = {int(excerpt.get("project_index") or 0): excerpt for excerpt in report.projects}
    shared_cell = (
        '<div class="lanes">' + "".join(f'<span class="lane">{_e(name)}</span>' for name in shared) + "</div>"
        if shared
        else '<p class="muted">（技术栈清单里没有一个组件出现在两个以上项目里）</p>'
    )
    unique_rows = []
    for key, items in sorted(unique.items(), key=lambda kv: int(kv[0])):
        excerpt = by_index.get(int(key)) or {}
        chips = (
            "".join(f'<span class="lane grey">{_e(name)}</span>' for name in items) or '<span class="muted">—</span>'
        )
        unique_rows.append(
            _row([_cell(f"<b>{_e(project_label(excerpt))}</b>"), _cell(f'<div class="lanes">{chips}</div>')])
        )
    unique_table = _table(["只在这一个项目里出现", "组件"], unique_rows) if unique_rows else ""
    reads = [
        ('<p class="para"><b>共用栈说明什么：</b>' + _inline(diagrams.get("reuse_read")) + "</p>")
        if diagrams.get("reuse_read")
        else "",
        ('<p class="para"><b>差异栈说明什么：</b>' + _inline(diagrams.get("unique_read")) + "</p>")
        if diagrams.get("unique_read")
        else "",
        ('<p class="concl"><b>回答「是不是换皮」：</b>' + _inline(diagrams.get("sameness_answer")) + "</p>")
        if diagrams.get("sameness_answer")
        else "",
    ]
    return (
        f'<div class="fig" data-fig="stack"><h3>{_e(FIGURE_TITLES["stack"])}</h3>'
        f'<h4 class="sl">这 {len(report.projects)} 个项目共用 · 熟练度信号'
        "（这一栏由技术栈清单求交集算出来）</h4>" + shared_cell + unique_table + "".join(reads) + "</div>"
    )


def _figure_rounds(report: PortfolioReport) -> str:
    diagrams = report.diagrams or {}
    rounds = diagrams.get("rounds") or []
    if not rounds:
        return ""
    rows = [
        _row(
            [
                _cell(
                    f"<b>{_e(row['label'])}</b>" + ('<span class="star">胜负手</span>' if row.get("decisive") else "")
                ),
                _cell(_inline(row["text"])),
            ]
        )
        for row in rounds
    ]
    strategy = (
        '<p class="concl"><b>准备策略：</b>' + _inline(diagrams.get("strategy")) + "</p>"
        if diagrams.get("strategy")
        else ""
    )
    usage = (
        '<p class="usage"><b>使用说明：</b>' + _inline(diagrams.get("usage")) + "</p>" if diagrams.get("usage") else ""
    )
    return (
        f'<div class="fig" data-fig="rounds"><h3>{_e(FIGURE_TITLES["rounds"])}</h3>'
        + _table(["轮次", "面试官在问什么、要拿出什么"], rows)
        + strategy
        + usage
        + "</div>"
    )


def _diagrams_section(report: PortfolioReport) -> str:
    parts = ['<section class="card" id="c-diagrams"><h2 class="ct">二、组合图解</h2>']
    matrix = _coverage_rows(report, as_figure=True)
    if matrix:
        parts.append(f'<div class="fig" data-fig="coverage">{matrix}</div>')
    parts.append(_figure_narrative(report))
    parts.append(_figure_stack(report))
    parts.append(_figure_rounds(report))
    parts.append("</section>")
    return "".join(part for part in parts if part)


# ------------------------------------------------------------------ 三、使用建议
def _advice_section(report: PortfolioReport) -> str:
    advice = report.advice or {}
    parts = ['<section class="card" id="c-advice"><h2 class="ct">三、使用建议</h2>']

    arrangements = advice.get("arrangements") or []
    if arrangements:
        rows = []
        for position, row in enumerate(arrangements):
            mark = "　<b>（默认采用）</b>" if position == advice.get("default_index") else ""
            rows.append(
                _row(
                    [
                        _cell(f"<b>{_e(row['rendered'])}</b>{_e(mark)}"),
                        _cell(_inline(row["scenario"])),
                        _cell(_inline(f"{row['pros']}｜风险：{row['cons']}")),
                    ]
                )
            )
        parts.append("<h3>3.1 项目排列建议</h3>" + _table(["排列方式", "适用场景", "好处 / 风险"], rows))
        if advice.get("default_reason"):
            parts.append(f'<p class="concl">{_inline(advice["default_reason"])}</p>')

    asked = advice.get("asked_before") or []
    if asked:
        rows = [_row([_cell(f"<b>{_e(row['asked'])}</b>"), _cell(_inline(row["answer"]))]) for row in asked]
        parts.append("<h3>3.2 面试叙事建议</h3>" + _table(["被问", "怎么答"], rows))

    strengthen = advice.get("strengthen") or []
    if strengthen:
        rows = [
            _row([_cell(f"<b>{_e(row['gap'])}</b>"), _cell(_inline(row["action"])), _cell(_inline(row["expected"]))])
            for row in strengthen
        ]
        parts.append("<h3>3.3 补强路径（组合层面）</h3>" + _table(["缺口", "补齐动作", "补齐后预计"], rows))

    citation = advice.get("citation") or {}
    if citation:
        parts.append(
            "<h3>3.4 引用红线（组合层面）</h3>"
            + _kv_table(
                [
                    ("可借鉴", citation.get("borrow", "")),
                    ("需改造", citation.get("adapt", "")),
                    ("一抄就穿", citation.get("breaks", "")),
                ]
            )
        )
    parts.append("</section>")
    return "".join(parts)


# ------------------------------------------------------------------ 四、跨项目面试
def _questions_section(report: PortfolioReport) -> str:
    payload = report.questions or {}
    state = report.questions_state()
    if state == QUESTIONS_DEFERRED:
        return (
            '<section class="card" id="c-questions"><h2 class="ct">四、跨项目面试</h2>'
            + f'<p class="concl" id="deferred-note">{_inline(payload.get("note") or "")}</p></section>'
        )
    items = payload.get("questions") or []
    if not items:
        return ""
    dist = payload.get("distribution") or {}
    stat = (
        f'<div class="qstat" id="qstat" data-total="{len(items)}" '
        f'data-answerable="{dist.get("answerable", 0)}" data-weak="{dist.get("weak", 0)}" '
        f'data-high="{dist.get("high_risk", 0)}">共 {len(items)} 题 · 可答 {dist.get("answerable", 0)} · '
        f'需补强 {dist.get("weak", 0)} · 高危 {dist.get("high_risk", 0)}</div>'
    )
    blocks = []
    for item in items:
        klass = {"可答": "", "需补强": " warn", "高危": " danger"}.get(item["status"], "")
        followups = "".join(
            f'<p class="fu"><span class="lbl fuk">{_e(follow["kind"])}</span>{_inline(follow["text"])}</p>'
            for follow in item.get("followups") or []
        )
        missing = ""
        if item.get("missing"):
            missing = '<ul class="miss">' + "".join(f"<li>{_inline(text)}</li>" for text in item["missing"]) + "</ul>"
        risk = f'<p class="how">对应 1.4 第 {item["risk_ref"]} 条风险。</p>' if item.get("risk_ref") else ""
        blocks.append(
            f'<div class="qst" data-no="{item["no"]}" data-status="{_e(item["status"])}">'
            f'<p class="q"><span class="no">Q{item["no"]}</span> · {_e(item["question"])}'
            f'<em class="kind">{_e(item["kind"])}</em></p>'
            f'<span class="lbl z">标准答案</span><p class="ans">{_inline(item["answer"])}</p>'
            + followups
            + missing
            + risk
            + f'<span class="st{klass}">{_e(item["status"])}</span>'
            + "</div>"
        )
    kinds = "、".join(f"{name} {count} 题" for name, count in (dist.get("by_kind") or {}).items())
    tail = f'<p class="concl">题型分布：{_e(kinds)}。</p>' if kinds else ""
    return (
        '<section class="card" id="c-questions"><h2 class="ct">四、跨项目面试</h2>'
        '<p class="note">只针对组合层面的追问；单个项目的深挖题在它们各自的项目分析里。</p>'
        + stat
        + "".join(blocks)
        + tail
        + "</section>"
    )


# ------------------------------------------------------------------ 汇总
def _sections_present(report: PortfolioReport) -> list[str]:
    present = ["c-profile"]
    if report.diagrams:
        present.append("c-diagrams")
    if report.advice:
        present.append("c-advice")
    if report.questions_state() in (QUESTIONS_READY, QUESTIONS_DEFERRED):
        present.append("c-questions")
    return present


def render_portfolio_report_html(report: PortfolioReport) -> str:
    present = _sections_present(report)
    parts = [_header(report), _nav(present), '<main class="wrap">', _profile_section(report)]
    if report.diagrams:
        parts.append(_diagrams_section(report))
    if report.advice:
        parts.append(_advice_section(report))
    if report.questions_state() in (QUESTIONS_READY, QUESTIONS_DEFERRED):
        parts.append(_questions_section(report))
    parts.append("</main>")

    missing_note = (
        '<p class="tailnote" id="tail-note">这一份下载的时候第四节还没生成：点页面上那个按钮才会出跨项目的题，'
        "出题要再花一发模型调用。</p>"
        if report.questions_state() == QUESTIONS_NOT_GENERATED
        else ""
    )
    parts.append(
        '<footer class="ft">'
        + missing_note
        + "生成日期："
        + _e(report.report_date)
        + "　·　本文档基于候选人提交的简历文本整理，项目名 / 公司名 / 真实人名按脱敏规则处理；带"
        + '<span class="todo">【待补】</span>'
        + "的地方需由使用者按文中的路径跑一遍、填上真实数据后再使用。<br>"
        + "这一份用的是<b>组合那把六维尺</b>（含位次区间）。"
        + _e(THREE_RUBRICS_NOTE)
        + "</footer>"
        + '<button class="totop" id="totop" type="button" aria-label="回顶部">↑</button>'
    )

    document = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{TITLE}｜{report.project_count} 个项目整体分析</title>"
        f"<style>{_CSS}</style></head><body>" + "\n".join(parts) + f"<script>{_JS}</script></body></html>"
    )
    issues = lint_portfolio_html(document, report)
    if issues:
        raise RuntimeError("组合分析未通过交付前机检：\n" + format_issues(issues))
    return document


_CSS = """
:root{--brand:#1a3a5c;--brand2:#2f6fb5;--ink:#222a37;--ink2:#4a566b;--ink3:#8a93a6;--line:#e6ebf3;--line2:#d5dbe8;
--soft:#f6f9ff;--hot:#b23a2e;--hot-soft:#fdf2f0;--warn:#8a5a10;--warn-soft:#fdf7ec;--ok:#1f6b3b;--mine:#eaf3ff}
*{box-sizing:border-box}
body{margin:0;background:#f3f6fb;color:var(--ink);font:15px/1.72 -apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.top{background:#fff;border-bottom:1px solid var(--line);padding:18px 22px 12px}
.ttl{font-size:20px;font-weight:700;color:var(--brand)}
.sub{font-size:13px;color:var(--ink2);margin-top:4px}
.pills{margin-top:10px;display:flex;flex-wrap:wrap;gap:8px}
.pill{background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:4px 12px;font-size:13px;color:var(--ink2)}
.pill b{color:var(--brand);margin-right:6px}
.modnav{position:sticky;top:0;z-index:40;background:#fff;border-bottom:1px solid var(--line);padding:0 22px;display:flex;gap:4px;overflow-x:auto}
.modnav a{padding:11px 13px;font-size:13.5px;color:var(--ink2);text-decoration:none;white-space:nowrap;border-bottom:2px solid transparent}
.modnav a.on{color:var(--brand2);border-bottom-color:var(--brand2);font-weight:600}
.wrap{max-width:1080px;margin:0 auto;padding:18px 22px 40px}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;padding:20px 22px;margin-bottom:16px;box-shadow:0 2px 10px rgba(30,50,100,.05);scroll-margin-top:52px}
h2.ct{margin:0 0 14px;font-size:18px;color:var(--brand)}
h3{margin:20px 0 8px;font-size:15.5px;color:var(--brand)}
h4.sl{margin:14px 0 4px;font-size:14px;color:var(--ink)}
p{margin:6px 0}
.tbl{width:100%;border-collapse:collapse;margin:8px 0 12px;font-size:14px}
.tbl th{background:var(--soft);color:var(--brand);text-align:left;font-weight:600;padding:8px 10px;border:1px solid var(--line)}
.tbl td{padding:8px 10px;border:1px solid var(--line);vertical-align:top}
.tbl tr.hot td{background:var(--hot-soft)}
.tbl tr.total td{background:#f1f5fb;font-weight:600}
.tbl td.n,.tbl th.n{text-align:center;white-space:nowrap}
.matrix td.cov{text-align:center;font-weight:700;width:86px}
.matrix td.cov.full{color:var(--brand2)}
.matrix td.cov.part{color:var(--ink3)}
.paper{border:1px solid var(--line2);border-radius:10px;padding:12px 16px;background:#fcfdff;margin:6px 0 14px}
.paper .vl{margin:4px 0;color:var(--ink)}
.paper .hd{margin:8px 0 2px;font-size:13px;color:var(--brand);font-weight:600}
.vl{color:var(--ink)}
.muted{color:var(--ink3)}
.note{font-size:13px;color:var(--ink3);margin:6px 0}
.concl{background:var(--soft);border-left:3px solid var(--brand2);padding:9px 13px;border-radius:0 8px 8px 0;font-size:14px;color:var(--ink2);margin:10px 0}
.para{margin:6px 0 10px}
.todo{color:var(--hot);font-weight:600}
.redline{background:var(--hot-soft);border:1px solid #eccab8;border-radius:10px;padding:12px 15px;margin:10px 0 14px;font-size:14px;color:#7b2c22}
.fig{border-top:1px dashed var(--line2);margin-top:18px;padding-top:6px}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;margin:10px 0}
.flow.lanes-vertical .node{flex:1 1 100%}
.node{flex:1 1 220px;border:1px solid var(--line2);border-radius:10px;padding:9px 11px;background:#fbfcff;font-size:13.5px;color:var(--ink2)}
.node .nh{font-weight:700;color:var(--brand);margin-bottom:4px}
.node .code{float:right;font-size:12px;color:var(--ink3);font-weight:400}
.node ul{margin:4px 0 6px;padding-left:20px}
.node li{margin:2px 0}
.node .q{color:var(--ink);margin-top:4px}
.lanes{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.lane{background:var(--mine);border:1px solid #cfe0f7;border-radius:6px;padding:3px 9px;font-size:13px;color:var(--brand)}
.lane.grey{background:#f4f5f8;border-color:var(--line2);color:var(--ink2)}
.star{display:inline-block;margin-left:8px;font-size:12px;color:var(--hot);border:1px solid #eccab8;border-radius:6px;padding:0 6px}
.usage{background:var(--warn-soft);border:1px solid #f0dfc0;border-radius:10px;padding:10px 14px;font-size:13.5px;color:#7a5210;margin-top:14px}
.qstat{font-size:14px;font-weight:600;color:var(--brand);background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin-bottom:12px}
.qst{border-top:1px dashed var(--line2);padding-top:14px;margin-top:16px}
.qst:first-of-type{border-top:0;padding-top:0}
.q{font-weight:700;color:var(--ink)}
.q .no{color:var(--brand2)}
.kind{font-style:normal;font-size:12.5px;color:var(--ink3);font-weight:400;margin-left:6px}
.lbl{display:block;font-weight:700;font-size:13.5px;color:var(--brand);margin:10px 0 3px}
.lbl.z{color:var(--ink2)}
.lbl.fuk{color:var(--brand2)}
.ans{margin:4px 0 0}
.fu{margin:5px 0 0;font-size:14px}
.miss{margin:6px 0 0;padding-left:22px}
.st{display:inline-block;margin-top:10px;font-size:13px;font-weight:600;color:var(--ok)}
.st.warn{color:var(--warn)}
.st.danger{color:var(--hot)}
.how{font-size:13.5px;color:var(--ink2);margin-top:6px}
.totop{position:fixed;right:20px;bottom:24px;z-index:60;display:none;width:42px;height:42px;border-radius:50%;border:1px solid var(--line2);
background:#fff;color:var(--brand2);font-size:16px;cursor:pointer;box-shadow:0 6px 18px rgba(30,50,100,.14)}
.totop.show{display:block}
.tailnote{color:var(--warn);font-size:13px}
footer.ft{max-width:1080px;margin:0 auto;padding:0 22px 40px;color:var(--ink3);font-size:12.5px}
@media print{body{background:#fff}.top{position:static;background:#fff;border-bottom:0}
.modnav,.totop{display:none!important}.wrap{max-width:none;padding:0}
.card{break-inside:avoid;box-shadow:none;border-color:#d5dbe8;margin-bottom:12px}
.qst,.fig{break-inside:avoid}}
@media (max-width:860px){.node{flex:1 1 100%}}
"""

_JS = """
(function(){
  var links=[].slice.call(document.querySelectorAll('.modnav a'));
  var secs=links.map(function(a){return document.querySelector(a.getAttribute('href'));});
  var totop=document.getElementById('totop');
  function onScroll(){
    var y=window.pageYOffset+150,cur=0;
    for(var i=0;i<secs.length;i++){if(secs[i]&&secs[i].offsetTop<=y)cur=i;}
    links.forEach(function(a,j){a.classList.toggle('on',j===cur);});
    if(totop)totop.classList.toggle('show',window.pageYOffset>520);
  }
  window.addEventListener('scroll',onScroll);
  window.addEventListener('resize',onScroll);
  onScroll();
  if(totop)totop.addEventListener('click',function(){window.scrollTo(0,0);});
})();
"""


__all__ = ["FIGURE_TITLES", "TITLE", "render_portfolio_report_html"]
