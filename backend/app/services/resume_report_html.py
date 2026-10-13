"""把一份 Report 渲染成自包含 HTML（`docs/resume-report-spec.md` §8）。

三条不从代码上读就看不出来的约束：

* **所有来自候选人和模型的文本都先 `html.escape`**，结构标签由本模块自己发。
  批改稿的主体是别人写的简历，`<script>` 之类的东西进不了这一页。
* **产出前过一遍 `report_html_lint`**：渲染器与机检同源，坏掉的那一份不落盘，
  而不是让人下载一个打开才发现少一节的文件。
* 样式与页内脚本全部内联，零外部资源——离线双击可开是这份交付物的定义。
"""

from __future__ import annotations

import html
import re
from typing import Any

from app.services.report_html_lint import MODULES, format_issues, lint_report_html
from app.services.resume_report_schema import (
    STAT_MODE_CHANGES,
    Redline,
    Report,
)

_TITLE = "简历评估报告"
_TODO = re.compile(r"(【待补[^】]*】)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=False)


def _todo_markup(value: Any) -> str:
    """转义之后再给 `【待补：…】` 上标记，保证候选人看得见"这里还欠一个实测值"。"""
    return _TODO.sub(r'<span class="todo">\1</span>', _e(value))


def _inline(value: Any) -> str:
    escaped = _e(value)
    return _BOLD.sub(r"<b>\1</b>", escaped.replace("\n", "<br>"))


def _sep() -> str:
    return '<span class="sep">|</span>'


def _pills(report: Report) -> str:
    grade = report.grade or "—"
    total = "未评分" if report.total_score is None else f"{report.total_score}/100"
    direction = _e(report.verdict.get("direction") or "未定")
    level = _e(report.verdict.get("target_level") or "未定")
    return (
        f'<span class="pill grade">评级 <b>{grade}</b> · {_e(total)}</span>'
        f'<span class="pill">目标等级 {level}</span>'
        f'<span class="pill">方向 {_e(_short(direction, 22))}</span>'
    )


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _summary(report: Report) -> str:
    verdict = report.verdict
    parts = [
        f"方向定位：{_e(verdict.get('direction') or '未定')}",
        _sep(),
        f"目标等级：{_e(verdict.get('target_level') or '未定')}"
        + (f"（{_e(verdict.get('level_basis'))}）" if verdict.get("level_basis") else ""),
        _sep(),
        "评级："
        + (
            f'<b class="g">{_e(report.grade or "未知")}'
            + ("（未评分）" if report.total_score is None else f"（{report.total_score}/100）")
            + "</b>"
        ),
        _sep(),
        f"日期：{_e(report.report_date)}",
    ]
    return (
        '<section class="card" id="m-summary">\n<div class="verdict">\n      '
        + "\n      ".join(parts)
        + "\n    </div>\n  </section>"
    )


def _score_table(report: Report) -> str:
    rows = []
    for row in report.dimensions:
        score = "—" if row["score"] is None else str(row["score"])
        # 待优化点里点名到具体位置，是这一栏的定义；没写就明说没写，不拿通用建议顶上。
        note = (
            _todo_markup(row["note"]) if row["note"] else '<span class="muted">本次分析没有为这一维写出待优化点</span>'
        )
        klass = ' class="hot"' if row["score"] is None or (row["full"] and row["score"] / row["full"] <= 0.7) else ""
        rows.append(
            f"<tr{klass}>\n<td><b>{_e(row['label'])}</b></td>"
            f'<td class="n"><b>{_e(score)}</b></td>'
            f'<td class="n"><b>{row["full"]}</b></td>'
            f"<td>{note}</td>\n</tr>"
        )
    total = "—" if report.total_score is None else str(report.total_score)
    rows.append(
        '<tr class="total">\n<td>合计</td>'
        f'<td class="n">{_e(total)}</td><td class="n">100</td>'
        f"<td>{_e(report.grade or '未知')}</td>\n</tr>"
    )
    gap = ""
    if report.to_next_grade:
        gap = "<br>距上一档还差：" + "；".join(_todo_markup(item) for item in report.to_next_grade)
    conclusion = (
        '<p class="concl">等级：'
        + _e(report.grade_scale)
        + "。分数代表的是现在这份简历的竞争力，不是你的能力上限。"
        + (_e(report.grade_desc) if report.grade and report.grade_desc else "")
        + gap
        + "</p>"
    )
    return (
        '<section class="card" id="m-score">\n'
        '<h2 class="ct">一、评分概览（七维 100 分）</h2>\n'
        '<table class="tbl"><thead><tr><th>维度</th><th class="n">得分</th><th class="n">满分</th><th>待优化点</th></tr></thead>'
        f"<tbody>\n{chr(10).join(rows)}\n</tbody></table>\n{conclusion}\n  </section>"
    )


def _fit(report: Report) -> str:
    verdict = report.verdict
    competition = report.competition
    basis = f"——{_e(verdict.get('direction_basis'))}" if verdict.get("direction_basis") else ""
    items = []
    for label, key in (("能打的牌", "cards"), ("要补的短板", "gaps"), ("针对性建议", "advice")):
        for item in competition.get(key) or []:
            items.append(f"<li><b>{label}</b>：{_todo_markup(item)}</li>")
    if competition.get("salary_note"):
        items.append(f"<li><b>期望薪资</b>：{_e(competition['salary_note'])}</li>")
    badge = _e(competition.get("positioning_badge") or "未给出档位")
    note = _e(competition.get("positioning_note") or "本次分析未给出定位说明")
    fallback = "<li>本次分析未给出可打的牌与要补的短板</li>"
    return (
        '<section class="card" id="m-fit">\n<h2 class="ct">二、竞争分析</h2>\n'
        + f'<p class="fitline"><b>方向定位</b>：{_e(verdict.get("direction") or "未定")}{basis}</p>\n'
        + f'<p class="fitline" style="margin-top:12px"><b>竞争力分析</b>：<span class="badge">{badge}</span>——{note}'
        + "（这一档评的是背景在同类人里站哪，与上面那格的「这份简历做得好不好」不是一回事）</p>\n"
        + '<ul class="bul">\n'
        + (chr(10).join(items) or fallback)
        + "\n</ul>\n  </section>"
    )


def _paper_block(block: dict[str, Any], by_id: dict[str, Any]) -> str:
    text = block["text"]
    row = by_id.get(block["block_id"])
    if row is None or not row.edits:
        return f"<p>{_todo_markup(text)}</p>"
    pieces = []
    cursor = 0
    for edit in sorted(row.edits, key=lambda e: e.mark):
        at = text.find(edit.del_text, cursor)
        if at < 0:
            continue
        pieces.append(_todo_markup(text[cursor:at]))
        star = " key" if edit.key else ""
        pieces.append(
            f"<del>{_e(edit.del_text)}</del>"
            + (f"<ins>{_todo_markup(edit.ins_text)}</ins>" if edit.ins_text else "")
            + f'<sup class="mk{star}">{edit.mark}</sup>'
        )
        cursor = at + len(edit.del_text)
    pieces.append(_todo_markup(text[cursor:]))
    return "<p>" + "".join(pieces) + "</p>"


def _redline(report: Report) -> str:
    redline: Redline | None = report.redline
    if redline is None:
        return (
            '<section class="card" id="m-resume">\n'
            '<h2 class="ct">三、修改建议<span class="tip">这一节这次没能生成，其余各节不受影响</span></h2>\n'
            '<p class="muted">批改稿暂时没有可用结果。可以先照着第二节的待优化点自己过一遍，稍后重跑这一节。</p>\n  </section>'
        )

    by_id = {block.block_id: block for block in redline.blocks}
    sections = report.sections or [{"block_id": b.block_id, "label": b.label, "text": b.text} for b in redline.blocks]
    paper = []
    for block in sections:
        paper.append(f'<div class="blk"><span class="lb">{_e(block["label"])}</span>')
        paper.append(_paper_block(block, by_id))
        paper.append("</div>")

    notes = []
    for block in redline.blocks:
        for edit in block.edits:
            klass = "note key" if edit.key else "note"
            tag = '<span class="tag">关键</span>' if edit.key else ""
            notes.append(
                f'<div class="{klass}"><span class="mk">{edit.mark}</span>{_todo_markup(edit.note)}{tag}</div>'
            )
    if redline.mode != STAT_MODE_CHANGES and redline.free_note:
        notes.append(f'<div class="note">{_e(redline.free_note)}</div>')
    if not notes:
        notes.append('<div class="note">这一版没有需要动手改的地方，保持原样投出去就行。</div>')

    stat = redline.stat_sentence()
    stat_html = (
        f'<span class="rvstat">共 <b>{redline.total}</b> 处改动，其中 <b>{redline.key_total}</b> 处是关键项（改完并补齐【待补】数据就能投）</span>'
        if redline.mode == STAT_MODE_CHANGES
        else f'<span class="rvstat">{_e(stat)}</span>'
    )
    todos = any("【待补" in (edit.ins_text + edit.note) for edit in redline.edits)
    warn = (
        '<div class="warnbox">带 <span class="todo">【待补：…】</span> 的地方需要按报告里给的路径跑一遍、填上真实数据后再投。'
        "<b>要一份干净、可直接投递的版本</b>：点「复制净稿」一键拿走，或切到「仅看改后净稿」后再打印 / 导出 PDF。</div>"
        if todos
        else '<div class="warnbox"><b>要一份干净、可直接投递的版本</b>：点「复制净稿」一键拿走，或切到「仅看改后净稿」后再打印 / 导出 PDF。</div>'
    )

    return (
        '<section class="card" id="m-resume">\n'
        '<h2 class="ct">三、修改建议<span class="tip">在你原简历上直接批改：红色删除线 = 建议改掉的原话，'
        "蓝色下划线 = 建议改成的内容，右栏批注说明每处为什么这么改；没标注的句子保持原样就能用。"
        "带「关键」的是必改项，先做这几处</span></h2>\n"
        f'<div class="rvbar">{stat_html}'
        '<button class="rvbtn" type="button" id="rv-toggle" aria-pressed="false">仅看改后净稿</button>'
        '<button class="rvbtn primary" type="button" id="rv-copy" title="复制出来的是一份干净、可直接投递的简历文本（不含删除线、批注与编号）">复制净稿</button>'
        "</div>\n"
        '<p class="print-only">说明：本页印出的是批改稿（含红色删除线、蓝色下划线、编号与右栏批注）。'
        "如果只需要改后的版本，请先在页面上点「仅看改后净稿」，再打印或导出 PDF。</p>\n"
        '<div class="rv"><div class="paper">' + "\n".join(paper) + "</div>"
        '<aside class="rvside">' + "\n".join(notes) + "</aside></div>\n" + warn + "\n  </section>"
    )


def _interview(report: Report) -> str:
    interview = report.interview
    if interview is None:
        return (
            '<section class="card" id="m-interview">\n<h2 class="ct">四、面试预演<span class="tip">这一节这次没能生成</span></h2>\n'
            '<p class="muted">面试预演暂时没有可用结果，把第三节改完再重跑这一节，性价比更高。</p>\n  </section>'
        )
    if interview.get("deferred"):
        return (
            '<section class="card" id="m-interview">\n<h2 class="ct">四、面试预演<span class="tip">这一节现在做价值不大</span></h2>\n'
            f"<p>{_e(interview.get('note'))}</p>\n  </section>"
        )

    distribution = interview.get("distribution") or {}
    by_kind = distribution.get("by_kind") or {}
    kind_text = " / ".join(f"{kind} {count}" for kind, count in by_kind.items())
    by_project = distribution.get("by_project") or {}
    project_text = "、".join(f"{name} {count} 题" for name, count in by_project.items())
    blocks = []
    for question in interview.get("questions") or []:
        parts = [f'<p><span class="no">Q{question["no"]}</span> · {_e(question["question"])}</p>']
        parts.append('<span class="lbl">【标准答案】</span>')
        parts.append(f"<p>{_todo_markup(question['answer'])}</p>")
        for index, follow in enumerate(question.get("followups") or [], start=1):
            label = follow.get("kind") or ""
            parts.append(f'<span class="lbl z">【追问 {index}】（{_e(label)}）</span>')
            parts.append(f"<p>{_todo_markup(follow.get('text'))}</p>")
        if question.get("status") == "需补强":
            missing = "、".join(_e(item) for item in question.get("missing") or [])
            parts.append(f'<span class="st warn">状态：⚠️ 需补强（缺：{missing or "未点名"}）</span>')
        else:
            parts.append('<span class="st">状态：✅ 可答</span>')
        blocks.append('<div class="q">' + "\n".join(parts) + "</div>")

    return (
        '<section class="card" id="m-interview">\n'
        f'<h2 class="ct">四、面试预演（含追问与标准答案）<span class="tip">共 {distribution.get("total", 0)} 题；'
        f"题型分布：{kind_text or '未分类'}；{project_text or '未分组'}；"
        f'需补强 {distribution.get("weak", 0)} 题。每题的标准答案与追问都是按第一人称写的口述稿，照着念就行</span></h2>\n'
        + "\n".join(blocks)
        + "\n  </section>"
    )


def _boss_table(lines: list[str]) -> str:
    head = [cell.strip() for cell in lines[0].strip().strip("|").split("|")]
    body = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in lines[2:] if row.strip().strip("|")]
    cells = "".join(f"<th>{_inline(cell)}</th>" for cell in head)
    rows = "".join("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>" for row in body)
    return f'<table class="tbl"><thead><tr>{cells}</tr></thead><tbody>{rows}</tbody></table>'


def _boss_fillins(report: Report) -> str:
    """§7 那两处填空。内容来自 `build_personalization`，渲染器不自己算——
    应用内那一页与这份 HTML 必须读到同一句话。"""
    label = report.personalization.get("one_line_label") or ""
    opener = report.personalization.get("opener") or ""
    parts = []
    if label:
        parts.append(
            "<p><b>在线简历一句话标签</b>（引第三节你写下的那句，别另起一句）：</p>"
            f'<p class="muted quoted-resume">{_todo_markup(label)}</p>'
        )
    if opener:
        parts.append(
            "<p><b>打招呼第一句里的项目亮点</b>：开场就说这句 —— "
            f'<span class="muted quoted-resume">{_todo_markup(opener)}</span>'
            "。话术模板里那几处【】保持原样不要填死，投递时按每条 JD 改 2–3 个词。</p>"
        )
    if not parts:
        return ""
    return '<div class="boss-blk"><h3>本报告的两处填空</h3>' + "".join(parts) + "</div>"


def _boss(report: Report) -> str:
    strategy = report.apply_strategy
    if strategy is None:
        return (
            '<section class="card" id="m-boss">\n<h2 class="ct">五、投递策略</h2>\n'
            '<p class="muted">这一节的定稿文本没能读出来，报告里没有替代内容。</p>\n  </section>'
        )
    blocks = []
    for chapter in strategy.get("chapters") or []:
        inner = []
        pending_table: list[str] = []
        for paragraph in chapter.get("paragraphs") or []:
            lines = paragraph.splitlines()
            if lines and lines[0].lstrip().startswith("|"):
                pending_table.extend(lines)
                continue
            if pending_table:
                inner.append(_boss_table(pending_table))
                pending_table = []
            inner.append(f"<p>{_inline(paragraph)}</p>")
        if pending_table:
            inner.append(_boss_table(pending_table))
        blocks.append(f'<div class="boss-blk"><h3>{_inline(chapter["title"])}</h3>' + "\n".join(inner) + "</div>")
    return (
        f'<section class="card" id="m-boss">\n<h2 class="ct">五、投递策略<span class="tip">BOSS 直聘 · 通用投递建议</span></h2>\n'
        f"{chr(10).join(blocks)}\n{_boss_fillins(report)}\n  </section>"
    )


def _nav() -> str:
    links = "".join(f'<a href="#{anchor}">{_e(label)}</a>' for anchor, label in MODULES)
    return f'<nav class="modnav" aria-label="报告模块快速导航">{links}</nav>'


def render_report_html(report: Report) -> str:
    """渲染并自检。不合格的那一份不落盘——`RuntimeError` 带上机检给出的每一条原因。"""
    name = report.verdict.get("candidate_name") or ""
    title = f"{_TITLE} · {_e(name)}" if name else _TITLE
    document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="topbar">
  <div class="tb">
    <div class="tb-row">
      <div class="brand">{_TITLE}<em>{_e(name)}</em></div>
      <div class="tb-right">{_pills(report)}</div>
    </div>
    {_nav()}
  </div>
</header>
<main class="wrap">
  {_summary(report)}
  {_score_table(report)}
  {_fit(report)}
  {_redline(report)}
  {_interview(report)}
  {_boss(report)}
</main>
<footer class="ft">报告生成日期：{_e(report.report_date)}　·　本报告基于你提交的简历文本评估，不含任何未经确认的补充信息。</footer>
<button class="totop" id="totop" title="回到顶部" aria-label="回到顶部">↑</button>
<script>{_JS}</script>
</body>
</html>
"""
    issues = lint_report_html(document)
    if issues:
        raise RuntimeError(f"报告未通过交付前机检：\n{format_issues(issues)}")
    return document


_CSS = """
:root{--bg:#f4f6fa;--card:#fff;--ink:#1e2430;--ink2:#5a6478;--ink3:#8b94a8;--line:#e6eaf2;--line2:#d9e2f2;
--brand:#2f6df6;--brand2:#1b4fd8;--brand-soft:#edf3ff;--hot:#d81b47;--hot-soft:#fff5f7;--ok:#0f9960;
--warn:#b5730a;--warn-soft:#fff8ec}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
.topbar{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.95);backdrop-filter:saturate(180%) blur(10px);border-bottom:1px solid var(--line)}
.tb{max-width:1000px;margin:0 auto;padding:12px 22px 0}
.tb-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.brand{font-size:17px;font-weight:700;letter-spacing:.2px}
.brand em{font-style:normal;color:var(--ink3);font-weight:500;font-size:13px;margin-left:6px}
.tb-right{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}
.pill{display:inline-flex;align-items:center;gap:5px;padding:3px 11px;border-radius:999px;font-size:12.5px;font-weight:600;background:#f2f5fb;color:var(--ink2);border:1px solid var(--line)}
.pill.grade{background:var(--brand-soft);color:var(--brand2);border-color:#d5e3ff}
.pill.grade b{font-size:13.5px}
.modnav{display:flex;gap:6px;overflow-x:auto;padding:9px 0 11px;margin-top:1px;scrollbar-width:none}
.modnav::-webkit-scrollbar{display:none}
.modnav a{flex:0 0 auto;padding:6px 13px;border-radius:999px;font-size:13px;color:var(--ink2);text-decoration:none;border:1px solid transparent;white-space:nowrap}
.modnav a:hover,.modnav a.on{background:var(--brand);color:#fff;border-color:var(--brand)}
.wrap{max-width:1000px;margin:0 auto;padding:20px 22px 90px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px 26px;margin-bottom:18px;scroll-margin-top:112px;box-shadow:0 1px 2px rgba(20,30,60,.04)}
h2.ct{display:block;margin:0 0 16px;padding-left:13px;font-size:19px;line-height:1.5;border-left:4px solid var(--brand);color:var(--ink)}
h2.ct span.tip{display:block;font-size:13px;font-weight:400;color:var(--ink3);margin-top:2px}
h4.sub2{font-size:14.5px;margin:16px 0 8px;color:var(--ink2)}
p{margin:9px 0}.muted{color:var(--ink3);font-size:13px}
.verdict{background:var(--brand-soft);border:1px solid var(--line2);border-left:4px solid var(--brand);border-radius:12px;padding:15px 18px;font-size:15px;line-height:1.95}
.verdict .sep{color:#b7c4de;padding:0 7px}.verdict b.g{color:var(--brand2)}
.tbl{width:100%;border-collapse:collapse;font-size:14px}
.tbl th,.tbl td{border:1px solid var(--line);padding:9px 11px;vertical-align:top;text-align:left}
.tbl thead th{background:#f7f9fd;font-size:13px;color:var(--ink2);font-weight:600}
.tbl td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tbl tr.hot td{background:var(--hot-soft)}.tbl tr.hot td:first-child{color:var(--hot)}
.tbl tr.total td{background:#f7f9fd;font-weight:700}
.concl{margin-top:13px;font-size:14px;color:var(--ink2);line-height:1.85}
.fitline{font-size:15px;margin:0 0 4px}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:13px;font-weight:700;background:var(--brand-soft);color:var(--brand2);border:1px solid #d5e3ff}
ul.bul{margin:8px 0 0;padding-left:20px}ul.bul li{margin:5px 0}ul.bul li b{color:var(--ink)}
.rvbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 14px}
.rvstat{font-size:13.5px;color:var(--ink2)}.rvstat b{color:var(--hot)}
.rvbtn{padding:6px 15px;border-radius:999px;cursor:pointer;font:inherit;font-size:13px;font-weight:600;color:var(--brand2);background:var(--brand-soft);border:1px solid #d5e3ff}
.rvbtn:first-of-type{margin-left:auto}.rvbtn:hover{background:#e2ecff}
.rvbtn.primary{background:var(--brand);color:#fff;border-color:var(--brand)}
.rvbtn.copied{color:#0f7a4d;background:#eaf8f1;border-color:#bfe6d3}
.rv{display:grid;grid-template-columns:minmax(0,1fr) 268px;gap:20px;align-items:start}
.rvside{position:sticky;top:122px;max-height:calc(100vh - 165px);overflow:auto;padding-right:2px}
.paper{background:#fcfdff;border:1px dashed #cbd8ef;border-radius:12px;padding:20px 22px}
.paper .blk{margin:14px 0 0}.paper .blk .lb{font-weight:700;font-size:14px;color:var(--brand2)}
del{color:var(--hot);background:var(--hot-soft);text-decoration:line-through;text-decoration-thickness:1.5px;padding:0 3px;border-radius:3px}
ins{color:var(--brand2);background:var(--brand-soft);text-decoration:underline;text-underline-offset:3px;text-decoration-thickness:1.5px;padding:0 3px;border-radius:3px}
sup.mk{display:inline-block;min-width:17px;height:17px;line-height:17px;text-align:center;margin-left:4px;padding:0 2px;border-radius:9px;vertical-align:3px;background:#e8edf8;color:var(--ink2);font-size:11px;font-weight:700}
sup.mk.key{background:var(--hot);color:#fff}
.note{background:#fffdf3;border:1px solid #efe3c4;border-left:3px solid #ddb44e;border-radius:9px;padding:9px 12px;font-size:12.5px;line-height:1.7;color:#6b5420;margin:0 0 9px}
.note .mk{display:inline-block;min-width:18px;height:18px;line-height:18px;text-align:center;border-radius:9px;background:#ddb44e;color:#fff;font-size:11px;font-weight:700;margin-right:5px}
.note.key{background:var(--hot-soft);border-color:#f2c8d2;border-left-color:var(--hot);color:#8a1732}
.note.key .mk{background:var(--hot)}
.note .tag{display:inline-block;margin-left:6px;padding:0 6px;border-radius:5px;font-size:11px;font-weight:700;background:#fff;border:1px solid currentColor}
.print-only{display:none}
body.rg-only del,body.rg-only sup.mk,body.rg-only .rvside{display:none}
body.rg-only ins{background:none;color:inherit;text-decoration:none;padding:0}
body.rg-only .rv{grid-template-columns:minmax(0,1fr)}
.todo{color:var(--hot);font-weight:600}
.warnbox{background:var(--warn-soft);border:1px solid #f0dfc0;border-radius:10px;padding:11px 15px;font-size:13.5px;color:#7a5210;margin-top:12px}
.q{border-top:1px dashed var(--line2);padding-top:15px;margin-top:16px}.q:first-of-type{border-top:0;padding-top:0;margin-top:0}
.q .no{font-weight:700;color:var(--brand2)}
.lbl{display:block;font-weight:700;font-size:13.5px;color:var(--brand);margin:11px 0 4px}
.lbl.z{color:var(--ink2)}.q p{margin:5px 0 0}
.st{display:inline-block;margin-top:10px;font-size:13px;font-weight:600;color:var(--ok)}
.st.warn{color:var(--warn)}
.boss-blk{margin-bottom:16px}.boss-blk h3{margin:0 0 6px;font-size:15px;color:var(--ink)}
.boss-blk p{margin:4px 0;color:var(--ink2);font-size:14px}
.boss-blk .tbl{margin:8px 0}
.totop{position:fixed;right:20px;bottom:24px;z-index:60;display:none;width:42px;height:42px;border-radius:50%;border:1px solid var(--line2);background:#fff;color:var(--brand2);font-size:16px;cursor:pointer;box-shadow:0 6px 18px rgba(30,50,100,.14)}
.totop.show{display:block}
footer.ft{max-width:1000px;margin:0 auto;padding:0 22px 40px;color:var(--ink3);font-size:12.5px}
@media print{body{background:#fff}.topbar{position:static;background:#fff;border-bottom:0}
.modnav,.totop,.rvbtn{display:none!important}.wrap{max-width:none;padding:0}
.card{break-inside:avoid;box-shadow:none;border-color:#d5dbe8;margin-bottom:12px;scroll-margin-top:0}
.q{break-inside:avoid}.rv{grid-template-columns:1fr}
.rvside{position:static;max-height:none;overflow:visible;margin-top:14px}
.print-only{display:block;margin:0 0 10px;font-size:12.5px;color:#8a93a6}
body.rg-only .print-only{display:none}}
@media (max-width:860px){.rv{grid-template-columns:1fr}.rvside{position:static;max-height:none;overflow:visible;margin-top:14px}
.rvbtn:first-of-type{margin-left:0}.rvbar{gap:8px}}
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
  var tg=document.getElementById('rv-toggle');
  if(tg){tg.addEventListener('click',function(){
    var on=document.body.classList.toggle('rg-only');
    tg.textContent=on?'显示批改痕迹':'仅看改后净稿';
    tg.setAttribute('aria-pressed',on?'true':'false');
  });}
  var cp=document.getElementById('rv-copy');
  if(cp){cp.addEventListener('click',function(){
    var src=document.querySelector('#m-resume .paper'),txt='';
    if(src){
      var clone=src.cloneNode(true);
      [].forEach.call(clone.querySelectorAll('del,sup.mk'),function(n){n.parentNode.removeChild(n);});
      [].forEach.call(clone.querySelectorAll('ins'),function(n){n.parentNode.replaceChild(document.createTextNode(n.textContent),n);});
      clone.style.cssText='position:absolute;left:-99999px;top:0;width:640px';
      document.body.appendChild(clone);
      txt=(clone.innerText||clone.textContent||'').replace(/\\n{3,}/g,'\\n\\n').trim();
      document.body.removeChild(clone);
    }
    var done=function(){var old=cp.textContent;cp.textContent='已复制 ✓';cp.classList.add('copied');
      setTimeout(function(){cp.textContent=old;cp.classList.remove('copied');},1600);};
    var fallback=function(){var ta=document.createElement('textarea');ta.value=txt;ta.setAttribute('readonly','');
      ta.style.cssText='position:absolute;left:-99999px;top:0';document.body.appendChild(ta);ta.select();
      try{document.execCommand('copy');}catch(e){}document.body.removeChild(ta);done();};
    if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(txt).then(done,fallback);}else{fallback();}
  });}
})();
"""


__all__ = ["render_report_html"]
