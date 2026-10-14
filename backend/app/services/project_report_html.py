"""把一份单项目分析渲染成自包含 HTML（`docs/project-report-spec.md` §8）。

三条与简历评估报告同源、但这一族各自成立的约束：

* **所有来自候选人与模型的文本都先 `html.escape`**，结构标签由本模块自己发；
* **产出前过一遍 `project_report_html_lint`**：坏掉的那一份不落盘，
  而不是等人下载了才发现少一节；
* 样式与页内脚本全部内联，零外部资源——离线双击可开是这份交付物的定义。

第四节还没生成时**整块缺席**（导航里也不留那一栏），页脚写一句"这一份下载时第四节还没生成"：
给候选人一个空壳的"四、面试准备"比不给更坏，他会以为系统看过了、只是没写。
"""

from __future__ import annotations

import html
import re
from typing import Any

from app.services import project_report_rubric as rubric
from app.services.project_report_html_lint import SECTIONS, format_issues, lint_project_html
from app.services.project_report_schema import (
    EXCLUDED_NOTE,
    QUESTIONS_DEFERRED,
    QUESTIONS_NOT_GENERATED,
    QUESTIONS_READY,
    ProjectReport,
)
from app.services.report_html_lint import NOTE_ABSENT

TITLE = "单项目分析"
_TODO = re.compile(r"(【待补[^】]*】)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")

FIGURE_TITLES = {
    "function_arch": "2.3 产品功能架构",
    "core_flow": "2.4 核心流程",
    "system_arch": "2.5 系统架构",
    "sequence": "2.6 任务时序",
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
    # 声明过的行**一律画出来**，值空着就空着：这一族的两份形态（下载那份 HTML 与应用内那一页）
    # 必须行行对得上。少了某一行的 HTML 会让人以为"这一栏不需要填"，而 Vue 那一页还留着那一行。
    rows = [_row([_cell(f"<b>{_e(key)}</b>"), _cell(_inline(value))]) for key, value in pairs]
    return _table(["项", "内容"], rows)


# ------------------------------------------------------------------ 表头与导航
def _nav(present: list[str]) -> str:
    links = "".join(f'<a href="#{anchor}">{_e(label)}</a>' for anchor, label in SECTIONS if anchor in present)
    return f'<nav class="modnav" id="modnav">{links}</nav>'


def _pills(report: ProjectReport) -> str:
    portrait = report.portrait or {}
    contribution = report.contribution or {}
    share = contribution.get("share")
    share_text = "算不出来（同简历其它项目没读全）" if share is None else f"{share}%"
    score = report.score_cell()
    picture = " · ".join(
        _e(portrait.get(key)) for key in ("domain", "scene", "main_line", "components") if portrait.get(key)
    )
    items = [
        ("项目", report.excerpt.get("name") or f"项目经历 {report.project_index + 1}"),
        ("项目画像", picture),
        (
            "贡献定位",
            f"简历第 {contribution.get('rank', report.project_index + 1)} 个项目 · 系数 {contribution.get('coefficient', '—')} · 占这份简历 {share_text}",
        ),
        ("难度", report.difficulty.get("level") or "未定级"),
        ("评分", f"{score}/100" if score not in ("不作数", "未评分") else score),
        ("代号", report.excerpt.get("code") or ""),
    ]
    return "".join(f'<span class="pill"><b>{_e(name)}</b>{_e(value)}</span>' for name, value in items if value)


def _header(report: ProjectReport) -> str:
    persuasion = (report.contribution or {}).get("persuasion")
    line = f'<div class="ttl">{TITLE}｜{_e(report.excerpt.get("name") or "")}</div>'
    if persuasion is not None:
        line += f'<div class="sub">这份简历的项目说服力（六维分 × 位次系数 ÷ 10）：{persuasion}</div>'
    return f'<header class="top">{line}<div class="pills">{_pills(report)}</div></header>'


# ------------------------------------------------------------------ 一、项目档案
def _band(row: dict[str, Any], rank: int) -> str:
    if row.get("positional"):
        # 落档那一格写的是**排第几**，不是这一维拿了几分：第 1 位得 5 分，
        # 拿分数当位次会打成"第 5 位"（2026-10-14 活页量出来的第一处，两棵树同时错）。
        return f"第 {rank} 位"
    if row["score"] is None:
        return "未读出来"
    ratio = row["score"] / row["full"] if row["full"] else 0
    return "优" if ratio >= 0.9 else "良" if ratio >= 0.75 else "中" if ratio >= 0.6 else "弱"


def _scorecard(report: ProjectReport) -> str:
    rank = int((report.contribution or {}).get("rank") or (report.project_index + 1))
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
                    _cell(_e(_band(row, rank))),
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
    scale = f'<p class="concl" id="grade-scale">评级档位：{_e(report.grade_scale)}。这一档说的是这一个项目，不是这份简历。</p>'
    return (
        "<h3>1.1 六维评分卡</h3>"
        + _table(["维度", "得分", "满分", "落档", "主要扣分理由"], rows, "tbl scorecard")
        + scale
    )


def _redline_banner(report: ProjectReport) -> str:
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
        '<div class="redline" id="redline-banner"><b>这一份不给总分与等级。</b>'
        f"{_e(EXCLUDED_NOTE)}" + _table(["命中的红线", "逐字证据（出自下面的原文）", "一问就穿在哪里"], rows) + "</div>"
    )


def _excerpt(report: ProjectReport) -> str:
    data = report.excerpt or {}
    meta = _kv_table(
        [
            ("简历项目名", data.get("name") or "（原文没有写项目名）"),
            ("担任角色", data.get("role")),
            ("起止时间", data.get("period")),
            ("技术栈（原文）", "、".join(data.get("tech") or []) or "（原文没有单独列技术栈）"),
            ("文档内代号", data.get("code")),
        ]
    )
    body = []
    for section in data.get("sections") or []:
        lines = "".join(f'<p class="vl">{_e(line)}</p>' for line in section.get("lines") or [])
        body.append(f'<h4 class="sl">{_e(section["label"])}</h4>{lines}')
    paper = "".join(body) or '<p class="muted">这一条项目没有正文。</p>'
    return (
        "<h3>1.2 简历原始档案</h3>"
        '<p class="note">以下逐字摘录自简历中该项目条目，未作改写、未作润色；'
        "仅公司名 / 客户名 / 真实人名按脱敏规则处理。</p>"
        f'{meta}<div class="paper" id="paper">{paper}</div>'
    )


def _highlights(report: ProjectReport) -> str:
    rows = [
        _row([_cell(f"<b>{_e(item['metric'])}</b>"), _cell(_todo(item["value"])), _cell(_inline(item["basis"]))])
        for item in report.highlights
    ]
    table = _table(["指标", "数值", "口径"], rows)
    if not table:
        return '<h3>1.3 亮点指标（已脱敏）</h3><p class="muted">这一份项目原文里没有可摘出来的量化亮点。</p>'
    return "<h3>1.3 亮点指标（已脱敏）</h3>" + table


def _hooks(report: ProjectReport) -> str:
    if not report.hooks:
        return '<h3>1.4 面试钩子（可深挖的技术决策点）</h3><p class="muted">没有给出可深挖的技术决策点。</p>'
    return (
        '<h3>1.4 面试钩子（可深挖的技术决策点）</h3><ul class="hooks">'
        + "".join(f"<li>{_inline(text)}</li>" for text in report.hooks)
        + "</ul>"
    )


def _difficulty(report: ProjectReport) -> str:
    level = report.difficulty.get("level") or ""
    if not level:
        return '<h3>1.5 难度分级</h3><p class="muted">这一份没有定级。</p>'
    return f"<h3>1.5 难度分级</h3><p class=\"concl\">{_e(level)}——{_e(report.difficulty.get('name'))}：{_e(report.difficulty.get('reason'))}</p>"


def _foot_notes(report: ProjectReport) -> str:
    """代码逐字扫出来的两类证据：缺基线的条目、技术栈没有落点的组件。

    它们**不参与判分也不判出局**（判据会把成品自己判出局），只把"一问就穿在哪"落到原文级。
    """
    out = []
    gaps = report.metric_gap_evidence or []
    if gaps:
        words = {"no_number": "全凭形容词", "single_number": "只有一个方向值"}
        listed = "；".join(f"{_e(row['clause'])}（{words.get(row['kind'], row['kind'])}）" for row in gaps[:6])
        out.append(f'<p class="note" id="gap-evidence">逐字扫出来的缺基线条目：{listed}</p>')
    foot = report.stack_footprint or {}
    if foot.get("missing"):
        out.append(
            f'<p class="note" id="footprint-evidence">技术栈里在项目正文没有落点的：{_e("、".join(foot["missing"]))}'
            f"（共 {foot.get('total', 0)} 项）</p>"
        )
    return "".join(out)


def _risks(report: ProjectReport) -> str:
    rows = [
        _row([_cell(f"<b>{_e(row['point'])}</b>"), _cell(_inline(row["detail"])), _cell(_todo(row["fix"]))])
        for row in report.risks
    ]
    head = "<h3>1.6 风险提示（哪里一问就穿）</h3>"
    if not rows:
        return head + '<p class="muted">这一份没有写出"哪里一问就穿"。</p>' + _foot_notes(report)
    return head + _table(["风险点", "说明", "补齐建议"], rows) + _foot_notes(report)


def _profile_section(report: ProjectReport) -> str:
    parts = [
        _scorecard(report),
        _redline_banner(report),
        _excerpt(report),
        _highlights(report),
        _hooks(report),
        _difficulty(report),
        _risks(report),
    ]
    return '<section class="card" id="p-profile"><h2 class="ct">一、项目档案</h2>' + "".join(parts) + "</section>"


# ------------------------------------------------------------------ 二、项目图解
def _layer_rows(layers: list[dict[str, Any]]) -> str:
    rows = []
    for layer in layers:
        mark = ' <span class="mine">★ 我负责</span>' if layer.get("mine") else ""
        cells = "<br>".join(
            f"<b>{_e(cell['title'])}</b>" + "".join(f"<br>{_inline(line)}" for line in cell.get("lines") or [])
            for cell in layer.get("cells") or []
        )
        rows.append(_row([_cell(f"<b>{_e(layer['name'])}</b>{mark}"), _cell(cells)]))
    return _table(["层", "这一层里有什么"], rows)


def _deep_dive(rows: list[dict[str, str]]) -> str:
    body = [
        _row([_cell(f"<b>{_e(row['where'])}</b>"), _cell(_inline(row["point"])), _cell(_e(row["source"]))])
        for row in rows
    ]
    return _table(["看哪里", "深挖点（面试官会顺着图问）", "出处"], body)


def _figure(report: ProjectReport) -> str:
    data = report.diagrams or {}
    out = [f'<h3>2.1 项目背景</h3><p class="para">{_inline(data.get("background"))}</p>']
    needs = data.get("needs") or {}
    items = "".join(f"<li><b>{_e(row['title'])}</b>——{_inline(row['detail'])}</li>" for row in needs.get("items") or [])
    out.append(
        "<h3>2.2 核心需求</h3>"
        f'<ul class="needs">{items}</ul>'
        + _kv_table(
            [
                ("使用角色", needs.get("roles")),
                ("交付形态", needs.get("delivery")),
                ("约束条件", needs.get("constraints")),
            ]
        )
    )

    arch = data.get("function_arch")
    if arch:
        out.append(
            f'<div class="fig" data-fig="function_arch"><h3>{FIGURE_TITLES["function_arch"]}</h3>'
            + _layer_rows(arch["layers"])
            + f'<p class="concl">{_inline(arch["boundary"])}</p>'
            + _deep_dive(arch["deep_dive"])
            + "</div>"
        )

    flow = data.get("core_flow")
    if flow:
        chips = [
            f'<div class="node"><b>{_e(flow["input"]["title"])}</b>'
            + "".join(f"<br>{_inline(line)}" for line in flow["input"]["lines"])
            + "</div>"
        ]
        chips += [
            f'<div class="node"><b>{row["no"]} {_e(row["title"])}</b>'
            + "".join(f"<br>{_inline(line)}" for line in row["lines"])
            + "</div>"
            for row in flow["nodes"]
        ]
        chips.append(
            f'<div class="node exit"><b>{_e(flow["exit"]["title"])}</b>'
            + "".join(f"<br>{_inline(line)}" for line in flow["exit"]["lines"])
            + "</div>"
        )
        fallbacks = "".join(f"<li>{_inline(text)}</li>" for text in flow["fallbacks"])
        out.append(
            f'<div class="fig" data-fig="core_flow"><h3>{FIGURE_TITLES["core_flow"]}</h3><div class="flow">'
            + "".join(chips)
            + "</div>"
            f'<p class="concl">{_inline(flow["state"])}</p><p class="note">虚线为回退路径：</p><ul class="fb">{fallbacks}</ul>'
            + _deep_dive(flow["deep_dive"])
            + "</div>"
        )

    system = data.get("system_arch")
    if system:
        rows = []
        for layer in system["layers"]:
            comps = "<br>".join(
                f"<b>{_e(comp['title'])}</b>" + (f"：{_inline(comp['line'])}" if comp["line"] else "")
                for comp in layer["components"]
            )
            principle = (
                f'<br><span class="muted">分界原则：{_inline(layer["principle"])}</span>' if layer["principle"] else ""
            )
            rows.append(_row([_cell(f"<b>{_e(layer['name'])}</b>"), _cell(comps + principle)]))
        out.append(
            f'<div class="fig" data-fig="system_arch"><h3>{FIGURE_TITLES["system_arch"]}</h3>'
            + _table(["层", "层内并列组件，层间为调用与被调关系"], rows)
            + _deep_dive(system["deep_dive"])
            + "</div>"
        )

    seq = data.get("sequence")
    if seq:
        lanes = "".join(f'<span class="lane">{_e(lane)}</span>' for lane in seq["lanes"])
        steps = [
            _row([_cell(f"{_e(row['from'])} → {_e(row['to'])}"), _cell(_inline(row["text"]))])
            for row in seq["messages"]
        ]
        branches = "".join(f"<li>{_inline(text)}</li>" for text in seq["branches"])
        artifacts = _kv_table(
            [
                ("任务标识", seq["artifacts"].get("task")),
                ("过程产物", seq["artifacts"].get("process")),
                ("控制字段", seq["artifacts"].get("control")),
            ]
        )
        out.append(
            f'<div class="fig" data-fig="sequence"><h3>{FIGURE_TITLES["sequence"]}</h3><div class="lanes">{lanes}</div>'
            + _table(["这一步", "带着什么过去"], steps)
            + f'<p class="note">虚线为失败分支：</p><ul class="fb">{branches}</ul>{artifacts}'
            + _deep_dive(seq["deep_dive"])
            + "</div>"
        )

    if data.get("reading_note"):
        out.append(f'<p class="usage">{_inline(data["reading_note"])}</p>')
    return '<section class="card" id="p-diagrams"><h2 class="ct">二、项目图解</h2>' + "".join(out) + "</section>"


# ------------------------------------------------------------------ 三、使用建议
def _advice_section(report: ProjectReport) -> str:
    data = report.advice or {}
    teaching = data.get("teaching") or {}
    reuse = data.get("reuse") or {}
    practice = dict(data.get("practice") or {})
    citation = data.get("citation") or {}
    backfill = ((report.questions or {}).get("practice") or {}) if report.questions else {}
    practice["must_practice"] = backfill.get("must_practice") or ""
    practice["high_risk"] = backfill.get("high_risk") or ""
    pending_note = (
        "这两行由第四节生成完回填；这一份还没生成，所以先空着。" if not backfill else "这两行由第四节生成完回填。"
    )

    level = data.get("level") or ""
    level_text = f"{level}——{data.get('level_reason')}" if level else ""
    parts = [
        "<h3>3.1 课程教学建议</h3>"
        + _kv_table(
            [
                ("难度级别", level_text),
                ("适合讲什么", teaching.get("suitable")),
                ("可拆几步", teaching.get("steps")),
                ("实操切入点", teaching.get("entry")),
                ("适配环节", teaching.get("stage")),
            ]
        ),
        "<h3>3.2 简历复用建议</h3>"
        + _kv_table(
            [
                ("可借鉴的结构", reuse.get("structure")),
                ("可迁移的表述", reuse.get("expression")),
                ("需要替换的内容", reuse.get("replace")),
                ("反例提示", reuse.get("counterexample")),
            ]
        ),
        "<h3>3.3 面试陪练建议</h3>"
        + _kv_table(
            [
                ("必练题（按重要性）", practice["must_practice"]),
                ("高危题", practice["high_risk"]),
                ("练习方法", practice.get("method")),
                ("追问预演", practice.get("rehearsal")),
                ("时间分配", practice.get("timing")),
            ]
        )
        + f'<p class="note">{_e(pending_note)}</p>',
        "<h3>3.4 补强路径</h3>"
        + _table(
            ["缺口", "补齐动作", "补齐后预计"],
            [
                _row([_cell(_inline(row["gap"])), _cell(_todo(row["action"])), _cell(_e(row["expected"]))])
                for row in data.get("strengthen") or []
            ],
        )
        + '<p class="note">需实测的数字一律标 <span class="todo">【待补：按 X 路径跑一遍得到实测值】</span>——不替使用者编数字。</p>',
        "<h3>3.5 引用红线</h3>"
        + _table(
            ["类别", "内容"],
            [
                _row([_cell(f"<b>{_e(key)}</b>"), _cell(_inline(value))])
                for key, value in [
                    ("✅ 可借鉴", citation.get("borrow")),
                    ("⚠️ 需改造", citation.get("adapt")),
                    ("🔴 一抄就穿", citation.get("breaks")),
                ]
                if value
            ],
        ),
    ]
    return '<section class="card" id="p-advice"><h2 class="ct">三、使用建议</h2>' + "".join(parts) + "</section>"


# ------------------------------------------------------------------ 四、面试准备
def _questions_section(report: ProjectReport) -> str:
    payload = report.questions or {}
    if report.questions_state() == QUESTIONS_DEFERRED:
        note = payload.get("note") or ""
        return (
            '<section class="card" id="p-questions"><h2 class="ct">四、面试准备</h2>'
            + f'<p class="concl">{_e(note)}</p></section>'
        )

    items = payload.get("questions") or []
    distribution = payload.get("distribution") or {}
    head = (
        f'<div class="qstat" data-total="{distribution.get("total", 0)}" data-answerable="{distribution.get("answerable", 0)}" '
        f'data-weak="{distribution.get("weak", 0)}" data-high="{distribution.get("high_risk", 0)}">'
        f'共 {distribution.get("total", 0)} 题 · 可答 {distribution.get("answerable", 0)} · 需补强 {distribution.get("weak", 0)} · 高危 {distribution.get("high_risk", 0)}'
        "</div>"
    )
    body = []
    for item in items:
        status = item["status"]
        klass = "st" if status == "可答" else "st danger" if status == "高危" else "st warn"
        mark = {"可答": "✅ 可答", "需补强": "⚠️ 需补强", "高危": "🔴 高危"}[status]
        followups = "".join(
            f'<p class="fu"><span class="lbl fuk">{_e(row["kind"])}</span>{_inline(row["text"])}</p>'
            for row in item.get("followups") or []
        )
        missing = "".join(f"<li>{_todo(text)}</li>" for text in item.get("missing") or [])
        diagram = item.get("diagram") or {}
        diagram_html = ""
        if diagram:
            cards = "".join(
                f'<div class="dcard"><b>{_e(card["title"])}</b>'
                + "".join(f"<br>{_inline(line)}" for line in card["lines"])
                + "</div>"
                for card in diagram["cards"]
            )
            note = f'<p class="concl">{_inline(diagram["note"])}</p>' if diagram.get("note") else ""
            diagram_html = (
                f'<div class="qdiagram"><p class="lbl">本题配图｜{_e(diagram["title"])}</p><div class="dcards">{cards}</div>'
                f"{note}<p class=\"how\">{_inline(diagram['how_to_draw'])}</p></div>"
            )
        body.append(
            f'<div class="qst" data-no="{item["no"]}" data-status="{_e(status)}">'
            f'<p class="q"><span class="no">Q{item["no"]}</span> {_e(item["question"])} <em class="kind">{_e(item["kind"])}</em></p>'
            f'<p class="lbl">【标准答案】</p><p class="ans">{_inline(item["answer"])}</p>'
            f"{diagram_html}{followups}"
            + (f'<p class="lbl z">缺的是</p><ul class="miss">{missing}</ul>' if missing else "")
            + f'<span class="{klass}">{_e(mark)}</span></div>'
        )
    kinds = "、".join(f"{name} {count}" for name, count in sorted((distribution.get("by_kind") or {}).items()))
    tail = f'<p class="concl">题型分布：{_e(kinds)}。</p>' if kinds else ""
    return (
        '<section class="card" id="p-questions"><h2 class="ct">四、面试准备（每题含标准答案与两轮追问）</h2>'
        + head
        + "".join(body)
        + tail
        + "</section>"
    )


# ------------------------------------------------------------------ 组装
def _sections_present(report: ProjectReport) -> list[str]:
    present = ["p-profile"]
    if report.diagrams:
        present.append("p-diagrams")
    if report.advice:
        present.append("p-advice")
    if report.questions_state() in (QUESTIONS_READY, QUESTIONS_DEFERRED):
        present.append("p-questions")
    return present


def render_project_report_html(report: ProjectReport) -> str:
    present = _sections_present(report)
    parts = [_header(report), _nav(present), '<main class="wrap">', _profile_section(report)]
    if report.diagrams:
        parts.append(_figure(report))
    if report.advice:
        parts.append(_advice_section(report))
    if report.questions_state() in (QUESTIONS_READY, QUESTIONS_DEFERRED):
        parts.append(_questions_section(report))
    parts.append("</main>")

    missing_note = (
        '<p class="tailnote" id="tail-note">这一份下载的时候第四节还没生成：点页面上那个按钮才会出题，'
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
        + "这一份用的是<b>项目那把六维尺</b>（含位次），与整份简历报告用的七维尺不是同一把，两个分数不能直接比。"
        + "</footer>"
        + '<button class="totop" id="totop" type="button" aria-label="回顶部">↑</button>'
    )

    document = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{TITLE}｜{_e(report.excerpt.get('name') or '')}</title>"
        f"<style>{_CSS}</style></head><body>" + "\n".join(parts) + f"<script>{_JS}</script></body></html>"
    )
    issues = lint_project_html(document, report)
    if issues:
        raise RuntimeError("单项目分析未通过交付前机检：\n" + format_issues(issues))
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
.wrap{max-width:1000px;margin:0 auto;padding:18px 22px 40px}
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
.paper{border:1px solid var(--line2);border-radius:10px;padding:12px 16px;background:#fcfdff;margin:6px 0 14px}
.paper .vl{margin:4px 0;color:var(--ink)}
.vl{color:var(--ink)}
.muted{color:var(--ink3)}
.note{font-size:13px;color:var(--ink3);margin:6px 0}
.concl{background:var(--soft);border-left:3px solid var(--brand2);padding:9px 13px;border-radius:0 8px 8px 0;font-size:14px;color:var(--ink2);margin:10px 0}
.para{margin:6px 0 10px}
.todo{color:var(--hot);font-weight:600}
.mine{color:var(--brand2);font-weight:700;font-size:12.5px}
.redline{background:var(--hot-soft);border:1px solid #eccab8;border-radius:10px;padding:12px 15px;margin:10px 0 14px;font-size:14px;color:#7b2c22}
ul.hooks,ul.needs,ul.fb,ul.miss{margin:6px 0 10px;padding-left:22px}
ul.hooks li,ul.needs li{margin:4px 0}
.fig{border-top:1px dashed var(--line2);margin-top:18px;padding-top:6px}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;margin:10px 0}
.node{flex:1 1 180px;border:1px solid var(--line2);border-radius:10px;padding:9px 11px;background:#fbfcff;font-size:13.5px;color:var(--ink2)}
.node.exit{background:var(--soft);border-color:var(--brand2)}
.lanes{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.lane{background:var(--mine);border:1px solid #cfe0f7;border-radius:6px;padding:3px 9px;font-size:13px;color:var(--brand)}
.usage{background:var(--warn-soft);border:1px solid #f0dfc0;border-radius:10px;padding:10px 14px;font-size:13.5px;color:#7a5210;margin-top:14px}
.qstat{font-size:14px;font-weight:600;color:var(--brand);background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin-bottom:12px}
.qst{border-top:1px dashed var(--line2);padding-top:14px;margin-top:16px}
.qst:first-of-type{border-top:0;padding-top:0}
.q{font-weight:700;color:var(--ink)}
.q .no{color:var(--brand2)}
.kind{font-style:normal;font-size:12.5px;color:var(--ink3);font-weight:400;margin-left:6px}
.lbl{display:block;font-weight:700;font-size:13.5px;color:var(--brand);margin:10px 0 3px}
.lbl.z{color:var(--ink2)}
.ans{margin:4px 0 0}
.fu{margin:5px 0 0;font-size:14px}
.st{display:inline-block;margin-top:10px;font-size:13px;font-weight:600;color:var(--ok)}
.st.warn{color:var(--warn)}
.st.danger{color:var(--hot)}
.qdiagram{background:#fbfcff;border:1px solid var(--line2);border-radius:10px;padding:10px 13px;margin:10px 0}
.dcards{display:flex;flex-wrap:wrap;gap:7px;margin:6px 0}
.dcard{flex:1 1 150px;border:1px solid var(--line);border-radius:8px;padding:7px 9px;font-size:13px;background:#fff}
.how{font-size:13.5px;color:var(--ink2);margin-top:6px}
.totop{position:fixed;right:20px;bottom:24px;z-index:60;display:none;width:42px;height:42px;border-radius:50%;border:1px solid var(--line2);
background:#fff;color:var(--brand2);font-size:16px;cursor:pointer;box-shadow:0 6px 18px rgba(30,50,100,.14)}
.totop.show{display:block}
.tailnote{color:var(--warn);font-size:13px}
footer.ft{max-width:1000px;margin:0 auto;padding:0 22px 40px;color:var(--ink3);font-size:12.5px}
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
  window.addEventListener('scroll',onScroll,{passive:true});
  window.addEventListener('resize',onScroll);
  onScroll();
  if(totop){totop.addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'});});}
})();
"""


__all__ = ["FIGURE_TITLES", "TITLE", "render_project_report_html"]
