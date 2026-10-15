"""交付前机检：一份组合分析合不合格（`docs/portfolio-report-spec.md` §9）。

十五条，每一条都对应一个"这一份会让人误信"的具体形状：
导航与四大节一一对、合计等于六维相加、出局那份不许同时出现分数、
摘录逐字、省略写法、机制字眼、反推件的示例值没替换干净、
表头那一排的**项目数与单项目均分必须等于服务端算的那一个**、
横向对比每行每列都有格且不留空、**1.3 与 2.1 那一列「组合覆盖」必须等于按格子推出来的那一句**、
叙事主线的阶段数必须等于项目数且一个项目不重不漏、面试时序必须五轮、
题数声明与实际题数一致、每题两轮追问且标签合法、零外部资源。

**HTML 注释先整段剥掉再扫**（与另两族同一条理由：规范原文里逐字写着禁词）。
候选人原文（`.paper` 与红线证据 `.vl`）在机制字眼那一条上豁免：
里面出现"人工兜底"这类词是候选人自己写在简历上的，收拾的是用词，不是机检。
"""

from __future__ import annotations

import re
from typing import Any

from app.services import portfolio_report_rubric as rubric
from app.services.portfolio_report_schema import PortfolioReport, universe_text
from app.services.report_html_lint import (
    FOLLOWUP_ATOMS,
    MOCK_MARK,
    NOTE_ABSENT,
    LintIssue,
    ellipsis_hits,
)

# 反推用的成品《总分析》里那些具体值，一份真实生成的报告里出现就是"没替换完"。
PORTFOLIO_FORBIDDEN_SAMPLE_VALUES: tuple[str, ...] = (
    "法律智能体",
    "金融合规",
    "电网诊断",
    "合同审查GraphRAG",
    "法审通",
    "LegalGraph",
    "PL-02",
)

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_TAG = re.compile(r"<[^>]+>")
_NAV_LINK = re.compile(r'<a\s+href="#([^"]+)"')
_SECTION = re.compile(r'<section\s+class="card"\s+id="([^"]+)"')
_SCORE_TOTAL = re.compile(r'<b id="score-total">([^<]*)</b>')
_PAPER = re.compile(r'<div class="paper"[^>]*>.*?</div>', re.S)
_PAPER_LINE = re.compile(r'<p class="vl">(.*?)</p>', re.S)
_QSTAT = re.compile(r'<div class="qstat"([^>]*)>')
_QST = re.compile(r'<div class="qst" data-no="(\d+)" data-status="([^"]*)"')
_FU = re.compile(r'<p class="fu"><span class="lbl fuk">([^<]*)</span>', re.S)
_MISS = re.compile(r'<ul class="miss">')
_FIG = re.compile(r'<div class="fig" data-fig="([^"]+)">')
_PILL = re.compile(r'<span class="pill"><b>([^<]*)</b>([^<]*)</span>')
_STAGE = re.compile(r'<span class="code">(PJ-\d+)</span>')
_EXT = re.compile(r'(?:src|href)\s*=\s*"(?:https?:)?//|@import|url\(\s*["\']?https?:', re.I)

# 四大节的锚点与导航文案，顺序即交付顺序。权威放在机检这一侧（与另两族同一条形状），
# 渲染器少画一节就会被这里拦住。
SECTIONS: tuple[tuple[str, str], ...] = (
    ("c-profile", "一、组合档案"),
    ("c-diagrams", "二、组合图解"),
    ("c-advice", "三、使用建议"),
    ("c-questions", "四、跨项目面试"),
)

_CODE_LABELS = {"可答": "answerable", "需补强": "weak", "高危": "high"}


def _visible(html: str) -> str:
    return _TAG.sub(" ", html or "")


def _attr(attrs: str, name: str) -> str:
    found = re.search(rf'{name}="([^"]*)"', attrs or "")
    return found.group(1) if found else ""


def narrative_text(html: str) -> str:
    """报告自己说的话 = 全文 − 候选人原文那几块 − 每一处逐字引文。"""
    body = _PAPER.sub(" ", html)
    body = re.sub(r'<span class="vl">.*?</span>', " ", body, flags=re.S)
    return _visible(body)


def _tables(html: str) -> list[list[list[str]]]:
    """把页面里每张表的行取出来（每行 = 若干单元格纯文本）。

    表标签上可以多带属性（窄屏地板宽就是这么给的），但一层套一层的表这里不支持——
    页面里本来也没有表套表。
    """
    out: list[list[list[str]]] = []
    for table in re.findall(r'<table class="tbl[^"]*"[^>]*>.*?</table>', html, re.S):
        rows: list[list[str]] = []
        for block in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            cells = [_visible(cell).strip() for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", block, re.S)]
            rows.append(cells)
        out.append(rows)
    return out


def lint_portfolio_html(document: str, report: PortfolioReport, *, allow_mock_samples: bool = False) -> list[LintIssue]:
    """返回问题清单；空清单 = 合格。`allow_mock_samples` 是夹具通道，不是后门。"""
    html = _COMMENT.sub(" ", document)
    issues: list[LintIssue] = []
    visible = _visible(html)
    readable = visible.replace("​", "")

    issues += _check_navigation(html)
    issues += _check_sections(html)
    issues += _check_scorecard(html, report)
    issues += _check_header_pills(html, report)
    issues += _check_excluded_shape(html, report)
    issues += _check_excerpt(html, report)
    issues += _check_language(html)
    issues += _check_compare(html, report)
    issues += _check_wide_tables(html, report)
    issues += _check_coverage(html, report)
    issues += _check_figures(html, report)
    if not (allow_mock_samples or MOCK_MARK in readable):
        hits = [word for word in PORTFOLIO_FORBIDDEN_SAMPLE_VALUES if word in readable]
        if hits:
            issues.append(LintIssue("unreplaced-sample", f"成品反推件里的示例值没有替换干净：出现 {hits[:5]}"))
    issues += _check_questions(html, report)
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
    """每一节"非空"的定义不一样，逐节点名要看到什么。"""
    issues: list[LintIssue] = []
    if 'id="c-profile"' not in html:
        issues.append(LintIssue("section-missing", "一、组合档案那一节不在页面上"))
    blocks = dict(re.findall(r'<section class="card" id="([^"]+)">(.*?)</section>', html, re.S))
    requirements = {
        "c-profile": ('class="tbl scorecard"', "<h3>1.4 整体风险提示", '<div class="paper"'),
        "c-diagrams": ('data-fig="coverage"', 'data-fig="narrative"', 'data-fig="rounds"'),
        "c-advice": ("<h3>3.1 项目排列建议", "<h3>3.4 引用红线"),
        "c-questions": ('class="qstat"', 'id="deferred-note"'),
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


def _check_scorecard(html: str, report: PortfolioReport) -> list[LintIssue]:
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
    empty = html.count(NOTE_ABSENT)
    if empty:
        issues.append(LintIssue("note-missing", f"有 {empty} 维给了分却没写出扣分理由，这一份下不了盘"))
    return issues


def _check_header_pills(html: str, report: PortfolioReport) -> list[LintIssue]:
    """表头那一排里，「项目数」与「单项目均分」两格必须等于服务端算的那一个。

    这两格是这一族最容易被写成"模型说什么就显示什么"的地方——
    一个组合报告顶着头重的两个数，读者不会去核对正文。
    """
    pills = {name.strip(): value.strip() for name, value in _PILL.findall(html)}
    issues: list[LintIssue] = []
    count_text = pills.get("项目数", "")
    if f"{report.project_count} 个" not in count_text:
        issues.append(
            LintIssue("header-stat", f"表头「项目数」写的是「{count_text}」，服务端数出来是 {report.project_count} 个")
        )
    average_text = pills.get("单项目均分", "")
    if average_text != report.average_cell():
        issues.append(
            LintIssue(
                "header-stat", f"表头「单项目均分」写的是「{average_text}」，服务端算的是「{report.average_cell()}」"
            )
        )
    return issues


def _check_excluded_shape(html: str, report: PortfolioReport) -> list[LintIssue]:
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


def _check_excerpt(html: str, report: PortfolioReport) -> list[LintIssue]:
    universe = universe_text(report.projects)
    papers = _PAPER.findall(html)
    if not papers:
        return [LintIssue("excerpt-missing", "1.5 那块逐字摘录不在页面上")]
    issues: list[LintIssue] = []
    if len(papers) != report.project_count:
        issues.append(LintIssue("excerpt-count", f"摘录块有 {len(papers)} 块，选中的项目是 {report.project_count} 个"))
    for paper in papers:
        for line in _PAPER_LINE.findall(paper):
            text = _visible(line).strip()
            if text and text not in universe:
                issues.append(LintIssue("excerpt-not-verbatim", f"摘录栏里出现了一行不在项目原文里的文字：{text[:40]}"))
    return issues


def _check_language(html: str) -> list[LintIssue]:
    from app.services.report_html_lint import FORBIDDEN_MECHANISM_WORDS

    text = narrative_text(html)
    issues: list[LintIssue] = []
    words = [word for word in FORBIDDEN_MECHANISM_WORDS if word in text]
    if words:
        issues.append(LintIssue("mechanism-word", f"正文出现内部机制字眼：{words[:5]}"))
    hits = ellipsis_hits(text)
    if hits:
        issues.append(LintIssue("ellipsis", f"用了省略写法，候选人会拿到半份稿子：{hits[:5]}"))
    if "**" in text or re.search(r"(?<!\w)_(?=\S)", text):
        issues.append(LintIssue("markdown-leak", "正文里漏出了 markdown 记号，这一份是直接给人看的"))
    return issues


def _check_compare(html: str, report: PortfolioReport) -> list[LintIssue]:
    """1.2 那张表：行数、列数、不许留空。"""
    rows_expected = (report.compare or {}).get("rows") or []
    issues: list[LintIssue] = []
    tables = [table for table in _tables(html) if table and table[0][0] == "对比项"]
    if not rows_expected:
        return issues
    if not tables:
        return [LintIssue("compare-missing", "一、组合档案声明有横向对比，页面上却没有那张表")]
    table = tables[0]
    body = table[1:]
    if len(body) != len(rows_expected):
        issues.append(LintIssue("compare-rows", f"横向对比画了 {len(body)} 行，数据里是 {len(rows_expected)} 行"))
    columns = report.project_count
    if len(table[0]) != columns + 1:
        issues.append(
            LintIssue("compare-columns", f"横向对比表头有 {len(table[0]) - 1} 个项目列，选中项目是 {columns} 个")
        )
    for position, row in enumerate(body):
        if len(row) != columns + 1:
            issues.append(
                LintIssue("compare-columns", f"横向对比第 {position + 1} 行有 {len(row)} 格，应为 {columns + 1} 格")
            )
            continue
        blanks = [cell for cell in row[1:] if not cell]
        if blanks:
            issues.append(LintIssue("compare-blank", f"横向对比第 {position + 1} 行有空格：{blanks[:2]}"))
    return issues


def _check_wide_tables(html: str, report: PortfolioReport) -> list[LintIssue]:
    """列数随项目数长的那两张表：既要有滚动容器，也要带上按项目数重算出来的地板宽。

    这条是从活页量出来的，不是拍的：400px 视口下没套容器时，一格压到 36px、一个项目名换三行，
    五个项目那一版还把整页顶出 86px 的横向滚动条。判据拿服务端的 `wide_table_min_px` 重算一遍再比，
    所以把 N 或那三个宽改了却忘了同步渲染，红的是这条。
    """
    wanted: list[tuple[str, int]] = []
    if ((report.compare or {}).get("rows") or []) and report.project_count:
        wanted.append(("对比项", rubric.wide_table_min_px(report.project_count)))
    if report.capabilities:
        wanted.append(("能力维度", rubric.wide_table_min_px(report.project_count, with_tail=True)))
    issues: list[LintIssue] = []
    for label, min_px in wanted:
        total = len(re.findall(r'<table class="tbl[^"]*"[^>]*><thead><tr class="hd"><th>' + label + "</th>", html))
        wrapped = len(
            re.findall(
                f'<div class="tscroll"><table class="tbl[^"]*" style="min-width:{min_px}px">'
                f'<thead><tr class="hd"><th>{label}</th>',
                html,
            )
        )
        if total != wrapped:
            issues.append(
                LintIssue(
                    "wide-table-scroll",
                    f"「{label}」那张表页面上有 {total} 处，只有 {wrapped} 处套了地板宽 {min_px}px 的横向滚动容器",
                )
            )
    return issues


def _check_coverage(html: str, report: PortfolioReport) -> list[LintIssue]:
    """那一列「组合覆盖」必须等于**按格子推出来的那一句**，两处（1.3 与 2.1）都要对。

    这是这一族最硬的一条：组合层最容易自我表扬的一句话就是"三个项目全覆盖"。
    """
    issues: list[LintIssue] = []
    tables = [table for table in _tables(html) if table and table[0][0] == "能力维度"]
    if not report.capabilities:
        return issues
    if not tables:
        return [LintIssue("coverage-missing", "数据里有能力覆盖矩阵，页面上没有那张表")]
    marks = {rubric.COVER_FULL: "●", rubric.COVER_PARTIAL: "○", rubric.COVER_NONE: ""}
    for table in tables:
        body = table[1:]
        if len(body) != len(report.capabilities):
            issues.append(
                LintIssue("coverage-rows", f"覆盖矩阵画了 {len(body)} 行，数据里是 {len(report.capabilities)} 行")
            )
            continue
        for position, (rendered, row) in enumerate(zip(body, report.capabilities, strict=False), start=1):
            cells = [cell.replace("​", "").strip() for cell in rendered[1:-1]]
            # 两条腿各判一件事：
            # ① 那一行的格子是不是数据里的那几个；
            # ② 结论那一格是不是**按画出来的格子**推出来的那一句。
            # 只写②不够（渲染器坏了会把两栏一起改对），只写①也不够——
            # 改了格子没改结论的那一种，①报的是格子、②才报出"结论与页面自己也对不上"。
            from_page = {
                index: (
                    rubric.COVER_FULL if mark == "●" else rubric.COVER_PARTIAL if mark == "○" else rubric.COVER_NONE
                )
                for index, mark in zip(sorted(int(k) for k in row["cells"]), cells, strict=False)
            }
            if len(from_page) == report.project_count:
                derived = rubric.coverage_verdict(from_page, report.project_count)
                derived_text = f"{derived['word']}（{derived['detail']}）"
                if rendered[-1] != derived_text:
                    issues.append(
                        LintIssue(
                            "coverage-verdict",
                            f"第 {position} 行「组合覆盖」写的是「{rendered[-1]}」，按画出来的格子推出来应是「{derived_text}」",
                        )
                    )
            for index, mark in zip(sorted(int(k) for k in row["cells"]), cells, strict=False):
                if mark != marks[row["cells"][index]]:
                    issues.append(
                        LintIssue(
                            "coverage-cell",
                            f"第 {position} 行 PJ-{index + 1:02d} 那一格画的是「{mark}」，数据里是 {row['cells'][index]}",
                        )
                    )
    return issues


def marks_row(row: dict[str, Any], project_count: int) -> list[str]:
    """数据里那一行的格子应该画成什么（渲染器与机检共用这一句，避免两份写法漂移）。"""
    marks = {rubric.COVER_FULL: "●", rubric.COVER_PARTIAL: "○", rubric.COVER_NONE: ""}
    return [marks[row["cells"][index]] for index in sorted(int(k) for k in row["cells"])]


def _check_figures(html: str, report: PortfolioReport) -> list[LintIssue]:
    issues: list[LintIssue] = []
    figures = _FIG.findall(html)
    if not figures:
        issues.append(LintIssue("figure-missing", "第二节里一张图都没有"))
    blocks = dict(re.findall(r'<div class="fig" data-fig="([^"]+)">(.*?)(?=<div class="fig"|</section>)', html, re.S))

    narrative = (report.diagrams or {}).get("narrative") or {}
    stages = narrative.get("stages") or []
    if stages:
        codes = _STAGE.findall(blocks.get("narrative", ""))
        if len(codes) != report.project_count:
            issues.append(
                LintIssue("narrative-stages", f"叙事主线画了 {len(codes)} 段，选中的项目是 {report.project_count} 个")
            )
        if len(set(codes)) != len(codes):
            issues.append(LintIssue("narrative-stages", f"叙事主线里有项目被讲了不止一次：{codes}"))

    rounds = (report.diagrams or {}).get("rounds") or []
    if rounds:
        table = [t for t in _tables(blocks.get("rounds", "")) if t and t[0][0] == "轮次"]
        if not table or len(table[0]) - 1 != len(rubric.INTERVIEW_ROUNDS):
            got = len(table[0]) - 1 if table else 0
            issues.append(
                LintIssue("rounds-count", f"跨项目面试时序画了 {got} 轮，定义是 {len(rubric.INTERVIEW_ROUNDS)} 轮")
            )

    stack = report.stack_reuse or {}
    shared = stack.get("shared") or []
    if shared and "stack" in blocks:
        lanes = re.findall(r'<span class="lane">([^<]*)</span>', blocks["stack"])
        missing = [name for name in shared if name not in lanes]
        if missing:
            issues.append(LintIssue("stack-shared", f"共用栈那一栏漏了服务端算出来的组件：{missing[:5]}"))
    return issues


def _check_questions(html: str, report: PortfolioReport) -> list[LintIssue]:
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


def format_issues(issues: list[LintIssue]) -> str:
    return "\n".join(f"  [{index + 1}] {issue}" for index, issue in enumerate(issues))


__all__ = [
    "PORTFOLIO_FORBIDDEN_SAMPLE_VALUES",
    "SECTIONS",
    "LintIssue",
    "format_issues",
    "lint_portfolio_html",
    "narrative_text",
]
