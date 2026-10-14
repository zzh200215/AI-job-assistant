"""交付前机检：一份单项目分析合不合格（`docs/project-report-spec.md` §9）。

十二条，每一条都对应一个"这文档会让人误信"的具体形状：
导航与四大节一一对、合计等于六维相加、出局那份不许同时出现分数、
摘录逐字、省略写法、机制字眼、反推件的示例值没替换干净、
题数声明与实际题数一致、每题两轮追问且标签合法、每张图配深挖点且出处点到原文、
零外部资源。

**HTML 注释先整段剥掉再扫**（与七维那族同一条理由：规范原文里逐字写着禁词）。
候选人原文（`.paper` 与红线证据 `.vl`）在机制字眼那一条上豁免：
里面出现"人工兜底"这类词是候选人自己写在简历上的，收拾的是用词，不是机检。
"""

from __future__ import annotations

import re

from app.services.project_report_schema import ProjectReport, excerpt_text
from app.services.report_html_lint import (
    FOLLOWUP_ATOMS,
    MOCK_MARK,
    NOTE_ABSENT,
    LintIssue,
    ellipsis_hits,
    is_anchored_note,
)

# 反推用的成品里那些具体值，一份真实生成的报告里出现就是"没替换完"。
PROJECT_FORBIDDEN_SAMPLE_VALUES: tuple[str, ...] = ("法审通", "LegalGraph", "合同审查GraphRAG", "PL-02", "CD-01")

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")
_NAV_LINK = re.compile(r'<a\s+href="#([^"]+)"')
_SECTION = re.compile(r'<section\s+class="card"\s+id="([^"]+)"')
_SCORE_TOTAL = re.compile(r'<b id="score-total">([^<]*)</b>')
_PAPER = re.compile(r'<div class="paper" id="paper">.*?</div>', re.S)
_PAPER_LINE = re.compile(r'<p class="vl">(.*?)</p>', re.S)
_QSTAT = re.compile(r'<div class="qstat"([^>]*)>')
_QST = re.compile(r'<div class="qst" data-no="(\d+)" data-status="([^"]*)"')
_FU = re.compile(r'<p class="fu"><span class="lbl fuk">([^<]*)</span>', re.S)
_MISS = re.compile(r'<ul class="miss">')
_FIG = re.compile(r'<div class="fig" data-fig="([^"]+)">')
_EXT = re.compile(r'(?:src|href)\s*=\s*"(?:https?:)?//|@import|url\(\s*["\']?https?:', re.I)

# 四大节的锚点与导航文案，顺序即交付顺序。权威放在机检这一侧（与七维那族同一条形状：
# `report_html_lint.MODULES` 也是机检持有、渲染器 import），渲染器少画一节就会被这里拦住。
SECTIONS: tuple[tuple[str, str], ...] = (
    ("p-profile", "一、项目档案"),
    ("p-diagrams", "二、项目图解"),
    ("p-advice", "三、使用建议"),
    ("p-questions", "四、面试准备"),
)

_CODE_LABELS = {"可答": "answerable", "需补强": "weak", "高危": "high"}


def _visible(html: str) -> str:
    return _TAG.sub(" ", html or "")


def _attr(attrs: str, name: str) -> str:
    found = re.search(rf'{name}="([^"]*)"', attrs or "")
    return found.group(1) if found else ""


def narrative_text(html: str) -> str:
    """报告自己说的话 = 全文 − 候选人原文那块 − 每一处逐字引文。"""
    body = _PAPER.sub(" ", html)
    body = re.sub(r'<span class="vl">.*?</span>', " ", body, flags=re.S)
    return _visible(body)


def lint_project_html(document: str, report: ProjectReport, *, allow_mock_samples: bool = False) -> list[LintIssue]:
    """返回问题清单；空清单 = 合格。`allow_mock_samples` 是夹具通道，不是后门。"""
    html = _COMMENT.sub(" ", document)
    issues: list[LintIssue] = []
    visible = _visible(html)
    readable = visible.replace("\u200b", "")

    issues += _check_navigation(html)
    issues += _check_sections(html)
    issues += _check_scorecard(html, report)
    issues += _check_excluded_shape(html, report)
    issues += _check_excerpt(html, report)
    issues += _check_language(html, report)
    if not (allow_mock_samples or MOCK_MARK in readable):
        hits = [word for word in PROJECT_FORBIDDEN_SAMPLE_VALUES if word in readable]
        if hits:
            issues.append(LintIssue("unreplaced-sample", f"成品反推件里的示例值没有替换干净：出现 {hits[:5]}"))
    issues += _check_questions(html, report)
    issues += _check_figures(html)
    if _EXT.search(html):
        issues.append(LintIssue("external-resource", "引用了外部资源：这一份必须离线双击就能打开"))
    return issues


def _check_navigation(html: str) -> list[LintIssue]:
    links = _NAV_LINK.findall(html)
    sections = _SECTION.findall(html)
    issues: list[LintIssue] = []
    order = [anchor for anchor, _label in SECTIONS]
    if links != sections:
        issues.append(LintIssue("navigation", f"导航项与页面里的节不一致：导航 {links} / 实际 {sections}"))
    if any(link not in order for link in links):
        issues.append(
            LintIssue("navigation", f"导航里有不在四大节表里的锚点：{[link for link in links if link not in order]}")
        )
    if links != [anchor for anchor in order if anchor in links]:
        issues.append(LintIssue("navigation", f"导航顺序与四大节的定义顺序不一致：{links}"))
    return issues


def _check_sections(html: str) -> list[LintIssue]:
    """每一节"非空"的定义不一样，逐节点名要看到什么。

    一条通用的"有标题就行"会把空壳放过去：第四节本来就允许只有那段"先不出题"的话，
    而第三节五张表里少画两张是渲染器写坏了，不是内容少。
    """
    issues: list[LintIssue] = []
    if 'id="p-profile"' not in html:
        issues.append(LintIssue("section-missing", "一、项目档案那一节不在页面上"))
    blocks = dict(re.findall(r'<section class="card" id="([^"]+)">(.*?)</section>', html, re.S))
    requirements = {
        "p-profile": ('class="tbl scorecard"', '<div class="paper" id="paper">'),
        "p-diagrams": ("<h3>2.1 项目背景", "<h3>2.2 核心需求"),
        "p-advice": ("<h3>3.1 课程教学建议", "<h3>3.5 引用红线"),
        "p-questions": ('class="qstat"', '<p class="concl">'),
    }
    for anchor, needles in requirements.items():
        body = blocks.get(anchor)
        if body is None:
            continue
        if not any(needle in body for needle in needles):
            issues.append(
                LintIssue("section-empty", f"{anchor} 这一节是空壳：应有的 " + " / ".join(needles) + " 都不在")
            )
    return issues


def _check_scorecard(html: str, report: ProjectReport) -> list[LintIssue]:
    found = _SCORE_TOTAL.search(html)
    if not found:
        return [LintIssue("score-total", "页面上找不到合计那一格")]
    shown = found.group(1).strip()
    issues: list[LintIssue] = []
    if shown != report.score_cell():
        issues.append(LintIssue("score-total", f"合计那一格显示 {shown}，服务端算的是 {report.score_cell()}"))
    if not report.is_excluded() and report.total_score is not None:
        rows = [row for row in report.dimensions if row["score"] is not None]
        if sum(int(row["score"]) for row in rows) != report.total_score:
            issues.append(LintIssue("score-total", "六维逐行相加与合计那一格不是同一个数"))
    # 那句"这一栏空着"的标记出现在页面上 = 有一维给了分却没写扣分理由。
    # 与七维那族同一条口径：判据是"给了分却没写"，不是"没给分"；空栏标记本身是同一句权威。
    empty = html.count(NOTE_ABSENT)
    if empty:
        issues.append(LintIssue("note-missing", f"有 {empty} 维给了分却没写出扣分理由，这一份下不了盘"))
    return issues


def _check_excluded_shape(html: str, report: ProjectReport) -> list[LintIssue]:
    issues: list[LintIssue] = []
    if report.is_excluded():
        if 'id="redline-banner"' not in html:
            issues.append(
                LintIssue("excluded-shape", "命中红线却没有把命中那一栏铺出来：候选人会只看到一个没有解释的空位")
            )
        if _QST.search(html):
            issues.append(LintIssue("excluded-shape", "这一份命中红线，页面里却出现了出题的正文"))
    elif "redline-banner" in html:
        issues.append(LintIssue("excluded-shape", "没有命中红线却挂着红线栏"))
    return issues


def _check_excerpt(html: str, report: ProjectReport) -> list[LintIssue]:
    universe = excerpt_text(report.excerpt)
    paper = _PAPER.search(html)
    if not paper:
        return [LintIssue("excerpt-missing", "1.2 那块逐字摘录不在页面上")]
    issues: list[LintIssue] = []
    for line in _PAPER_LINE.findall(paper.group(0)):
        text = _visible(line).strip()
        if text and text not in universe:
            issues.append(LintIssue("excerpt-not-verbatim", f"摘录栏里出现了一行不在项目原文里的文字：{text[:40]}"))
    return issues


def _check_language(html: str, report: ProjectReport) -> list[LintIssue]:
    from app.services.report_html_lint import FORBIDDEN_MECHANISM_WORDS

    text = narrative_text(html)
    issues: list[LintIssue] = []
    words = [word for word in FORBIDDEN_MECHANISM_WORDS if word in text]
    if words:
        issues.append(LintIssue("mechanism-word", f"正文出现内部机制字眼：{words[:5]}"))
    hits = ellipsis_hits(text)
    if hits:
        issues.append(LintIssue("ellipsis", f"用了省略写法，候选人会拿到半份稿子：{hits[:5]}"))
    return issues


def _check_questions(html: str, report: ProjectReport) -> list[LintIssue]:
    payload = report.questions or {}
    items = payload.get("questions") or []
    if not items:
        if _QST.search(html):
            return [LintIssue("question-count", "页面里有题目，这一份的数据里没有")]
        return []

    issues: list[LintIssue] = []
    stat = _QSTAT.search(html)
    if not stat:
        return [LintIssue("question-count", "第四节没有那道统计条")]
    attrs = stat.group(1)
    got = _QST.findall(html)
    declared = {name: _attr(attrs, name) for name in ("data-total", "data-answerable", "data-weak", "data-high")}
    if declared["data-total"] != str(len(got)):
        issues.append(LintIssue("question-count", f"声明共 {declared['data-total']} 题，页面里数出来 {len(got)} 题"))
    counted = {"answerable": 0, "weak": 0, "high": 0}
    for _no, status in got:
        key = _CODE_LABELS.get(status)
        if key is None:
            issues.append(LintIssue("question-status", f"题目状态不在三态里：{status}"))
            continue
        counted[key] += 1
    for key, name in (("answerable", "data-answerable"), ("weak", "data-weak"), ("high", "data-high")):
        if declared[name] != str(counted[key]):
            issues.append(LintIssue("question-count", f"{name} 声明 {declared[name]}，实际 {counted[key]}"))
    numbers = [int(no) for no, _ in got]
    if numbers != list(range(1, len(numbers) + 1)):
        issues.append(LintIssue("question-numbering", f"题号不连续：{numbers[:24]}"))

    for match in _QST.finditer(html):
        no, status = match.group(1), match.group(2)
        end = html.find('<div class="qst"', match.end())
        tail = html.find('<p class="concl">题型分布', match.end())
        stop = min(x for x in (end, tail, len(html)) if x > 0)
        body = html[match.end() : stop]
        labels = _FU.findall(body)
        if len(labels) != 2:
            issues.append(LintIssue("followup-count", f"Q{no} 有 {len(labels)} 条追问，定义是两轮"))
        atoms = [atom.strip() for label in labels for atom in re.split(r"[/、]", label) if atom.strip()]
        bad = [atom for atom in atoms if atom not in FOLLOWUP_ATOMS]
        if bad:
            issues.append(LintIssue("followup-kind", f"Q{no} 的追问类型标签不在白名单里：{bad[:4]}"))
        if status == "可答" and _MISS.search(body):
            issues.append(LintIssue("question-status", f"Q{no} 标着可答却列了缺什么"))
        if status in ("需补强", "高危") and not _MISS.search(body):
            issues.append(LintIssue("question-status", f"Q{no} 是 {status} 却没点名缺什么"))
    return issues


def _check_figures(html: str) -> list[LintIssue]:
    issues: list[LintIssue] = []
    blocks = re.findall(
        r'<div class="fig" data-fig="([^"]+)">(.*?)</div>\s*(?=<div class="fig"|<p class="usage">|</section>)',
        html,
        re.S,
    )
    for name, body in blocks:
        rows = re.findall(r"<tbody>(.*?)</tbody>", body, re.S)
        if not rows:
            issues.append(LintIssue("deep-dive-missing", f"{name} 这张图没有配深挖点表：图就只是图，没人能顺着问"))
            continue
        cells = re.findall(r"<td>(.*?)</td>", rows[-1], re.S)
        sources = [_visible(cell).strip() for cell in cells[2::3]]
        if len(sources) < 2:
            issues.append(LintIssue("deep-dive-thin", f"{name} 的深挖点只有 {len(sources)} 行"))
        unanchored = [source for source in sources if source and not is_anchored_note(source)]
        if unanchored:
            issues.append(LintIssue("deep-dive-unanchored", f"{name} 的出处没点到原文位置：{unanchored[:3]}"))
    if not blocks:
        issues.append(LintIssue("figure-missing", "第二节里一张图都没有"))
    return issues


def format_issues(issues: list[LintIssue]) -> str:
    return "\n".join(f"  [{index + 1}] {issue}" for index, issue in enumerate(issues))


__all__ = [
    "PROJECT_FORBIDDEN_SAMPLE_VALUES",
    "SECTIONS",
    "LintIssue",
    "format_issues",
    "lint_project_html",
    "narrative_text",
]
