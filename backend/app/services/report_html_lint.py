"""交付前机检：一份报告 HTML 合不合格（`docs/resume-report-spec.md` §9）。

成品报告背后那套技能原本带一个 `scripts/report_html_lint.py`，只在技能目录里跑。
这里把它移植成仓库的守卫：渲染器产出的每一份 HTML 在落盘前都要过一遍，
`tests/test_report_html_lint.py` 用一份人工确认过的成品当夹具钉住"合格报告能过"，
再用一组变异钉住"每发变异只红它自己那一条"。

三条是成品没有、本仓库必须加的：
* **不引用任何外部资源**——离线双击可开是这份交付物的定义，不是一个偏好；
* **合计行必须等于七维之和**——总分有两个来源（表里逐维相加、合计行另写一个）就是 A4 在匹配分上踩过的那个坑；
* **追问的类型标签必须在白名单里**——类型是题型分布统计的分组键，飘出去的那个标签会让分布数与题数对不上。

**HTML 注释先整段剥掉再扫**：成品文件顶部那段注释就是技能自己的写作规范，
里面逐字写着"门禁""可面试水位"和三个必须换掉的示例值——不剥注释的话，
一份完全合格的报告会因为带着规范原文而被判不合格。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 六个模块：锚点 id 与导航文案，顺序即交付顺序（§1）。
MODULES: tuple[tuple[str, str], ...] = (
    ("m-summary", "小结"),
    ("m-score", "一、评分概览"),
    ("m-fit", "二、竞争分析"),
    ("m-resume", "三、修改建议"),
    ("m-interview", "四、面试预演"),
    ("m-boss", "五、投递策略"),
)
MODULE_IDS: tuple[str, ...] = tuple(mid for mid, _label in MODULES)

# §5 措辞红线：这些是内部机制的叫法，出现在给候选人看的正文里就是不合格。
FORBIDDEN_MECHANISM_WORDS: tuple[str, ...] = (
    "兜底",
    "总分兜底",
    "不低于 65",
    "严格制",
    "软下限",
    "门禁",
    "可面试水位",
    "硬条件",
    "双轴",
    "收敛",
    "档内区分项",
)

# §5：技能自己那份示例里的具体值，一份真实报告里出现即"没替换完"。
FORBIDDEN_SAMPLE_VALUES: tuple[str, ...] = ("李明", "81/100", "企业知识库问答助手")

# §4：省略写法。命中就说明候选人拿到的是半份稿子。
FORBIDDEN_ELLIPSIS: tuple[str, ...] = ("同上", "以此类推", "其余项目照此", "此处省略", "同样处理")

# §6：追问的类型标签白名单（同时是题型分布的分组依据）。
# 这份词表是按成品报告实际用到的标签校正出来的，不是先验拟的：成品里出现了
# 「场景」「预期指标」两类，最初反推的那版把它们判成了非法标签。
FOLLOWUP_ATOMS: frozenset[str] = frozenset(
    {"为什么", "权衡", "代价", "边界", "对比", "数据", "踩坑", "如果", "场景", "预期指标"}
)

MOCK_MARK = "（mock）"

# §3 那条"每维的待优化点必须点名这份简历里的具体位置"的可判形式。
# 判据不是先验拟的：2026-10-13 用真 provider 跑了四份不同成色的简历（84 / 41 / 34 / 21 分），
# 28 条 note **全部**命中下面两条之一；反过来，改造前那一族通用建议
# （"建议量化项目成果，补充岗位关键词"）五条**一条都不命中**。
# 两条分别管"逐字引原文"与"指出是哪一块"——只留前者会把合法输出判死（四份里就有一条没带引号），
# 只留后者会放过通用建议（那种句子本来就写着"项目"两个字）。
_NOTE_QUOTE = re.compile(r"['\"“”「」『』]([^'\"“”「」『』]{2,60})['\"“”「」『』]")
_NOTE_POINTER = re.compile(
    r"(技能区|技能清单|技能列表|工作经历|项目经验|项目里|项目中|该项目|自我评价|优势段|个人优势|教育背景|求职意向|"
    r"第\s*\d+\s*[条个段]|这[两三四]\s*条|那[条个]|这一[条处段句]|.{1,12}项目(里|中)|负责的那一[段块]|抬头)"
)

# 渲染器在某一维没写出待优化点时打的那句（不是候选人的话，是"这一栏空着"的标记）。
_NOTE_ABSENT = "本次分析没有为这一维写出待优化点"


def is_anchored_note(text: str) -> bool:
    """一条待优化点有没有"点名具体位置"。

    有逐字引用，或指出了是哪一块/哪一条，算锚定；只有形容词与通用建议的不算。
    """
    return bool(_NOTE_QUOTE.search(text or "")) or bool(_NOTE_POINTER.search(text or ""))


_COMMENT = re.compile(r"<!--.*?-->", re.S)
_NAV_BLOCK = re.compile(r'<nav[^>]*class="[^"]*modnav[^"]*"[^>]*>(.*?)</nav>', re.S)
_NAV_LINK = re.compile(r'<a\s+href="#([^"]+)"[^>]*>(.*?)</a>', re.S)
_SECTION_ID = re.compile(r'<section\s+class="[^"]*card[^"]*"\s+id="([^"]+)"')
_SUP_MARK = re.compile(r'<sup\s+class="mk([^"]*)"[^>]*>\s*(\d+)\s*</sup>')
_NOTE_MARK = re.compile(r'<span\s+class="mk"[^>]*>\s*(\d+)\s*</span>')
_RVSTAT = re.compile(r'class="rvstat"[^>]*>(.*?)</span>', re.S)
_TAG = re.compile(r"<[^>]+>")
_FOLLOWUP_LABEL = re.compile(r"【追问\s*\d+】(?:（([^（）]*)）)?")


@dataclass(frozen=True)
class LintIssue:
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _strip_tags(html: str) -> str:
    return _TAG.sub(" ", html)


def _text(html: str) -> str:
    """剥注释、去标签、压空白后剩下的就是候选人读到的字。"""
    without_comments = _COMMENT.sub(" ", html)
    return re.sub(r"\s+", " ", _strip_tags(without_comments))


def _section_bodies(html: str) -> dict[str, str]:
    """按 `<section ... id="m-x">` 切出六个模块的正文。"""
    positions = [(m.group(1), m.start()) for m in _SECTION_ID.finditer(html)]
    bodies: dict[str, str] = {}
    for index, (anchor, start) in enumerate(positions):
        end = positions[index + 1][1] if index + 1 < len(positions) else len(html)
        bodies[anchor] = html[start:end]
    return bodies


def _word_check(words: tuple[str, ...], code: str, text: str, why: str) -> list[LintIssue]:
    hits = [word for word in words if word in text]
    return [LintIssue(code, f"{why}：出现 {hits[:5]}")] if hits else []


def _paper_region(html: str) -> str:
    """批改稿左栏那块"候选人原文"（含 del/ins 引文）。

    机制字眼那道扫描要跳过它：里面的"人工兜底"这类词是候选人自己写在简历上的，
    不是报告在解释自己的给分机制。真要收拾的是候选人的用词，不是机检。
    """
    start = re.search(r'<div\s+class="paper"[^>]*>', html)
    end = re.search(r'<aside\s+class="rvside"', html)
    if not start or not end or end.start() <= start.start():
        return ""
    return html[start.start() : end.start()]


# 报告在别处引用候选人原文时用的标记（第五节那两处填空就是）。同 `_paper_region` 一条理由。
# 惰性匹配不吃嵌套同名标签——这两处是叶子 `<p>`，没有嵌套；真要往里塞段落就别用这个类名。
_QUOTED_RESUME = re.compile(r'<([a-z]+)\b[^>]*class="[^"]*quoted-resume[^"]*"[^>]*>.*?</\1>', re.S | re.I)


def _narrative_text(body: str) -> str:
    """报告自己说的话 = 全文 − 被引用的候选人原文。"""
    without_paper = body.replace(_paper_region(body), " ")
    return _text(_QUOTED_RESUME.sub(" ", without_paper))


def lint_report_html(html: str, *, allow_mock_samples: bool = False) -> list[LintIssue]:
    """返回问题清单；空清单 = 合格。"""
    issues: list[LintIssue] = []
    body = _COMMENT.sub(" ", html)
    readable = _text(html)
    narrative = _narrative_text(body)
    is_mock = MOCK_MARK in readable

    issues += _check_navigation(html)
    issues += _check_sections(body)
    issues += _check_redline_counts(body)
    issues += _check_followup_labels(readable)
    issues += _check_total_row_matches_dimensions(body)
    issues += _check_dimension_notes(body)
    issues += _check_no_external_resources(html)
    issues += _word_check(FORBIDDEN_ELLIPSIS, "ellipsis", readable, "批改稿用了省略写法，候选人会拿到半份稿子")
    issues += _word_check(FORBIDDEN_MECHANISM_WORDS, "mechanism-word", narrative, "正文出现内部机制字眼")
    if not (allow_mock_samples and is_mock):
        issues += _word_check(FORBIDDEN_SAMPLE_VALUES, "unreplaced-sample", readable, "示例内容没有被替换干净")
    return issues


def _check_navigation(html: str) -> list[LintIssue]:
    nav = _NAV_BLOCK.search(html)
    if not nav:
        return [LintIssue("navigation", "顶部没有 .modnav 导航条")]

    links = [(href, _strip_tags(label).strip()) for href, label in _NAV_LINK.findall(nav.group(1))]
    expected = list(MODULES)
    if links != expected:
        return [
            LintIssue(
                "navigation",
                f"导航与模块不是一一对应：导航 {links}，期望 {expected}",
            )
        ]

    ids = _section_ids(html)
    missing = [mid for mid in MODULE_IDS if mid not in ids]
    if missing:
        return [LintIssue("navigation", f"导航指向的锚点在页面里不存在：{missing}")]
    return []


def _section_ids(html: str) -> list[str]:
    return [m.group(1) for m in _SECTION_ID.finditer(html)]


def _check_sections(body: str) -> list[LintIssue]:
    issues: list[LintIssue] = []
    ids = _section_ids(body)
    if ids != list(MODULE_IDS):
        issues.append(LintIssue("module-order", f"模块顺序或数量不对：{ids}，期望 {list(MODULE_IDS)}"))
    bodies = _section_bodies(body)
    for anchor, _label in MODULES:
        chunk = bodies.get(anchor)
        if chunk is None:
            continue
        if len(_text(chunk).strip()) < 20:
            issues.append(LintIssue("empty-module", f"模块 {anchor} 是空的"))
    return issues


def _check_redline_counts(body: str) -> list[LintIssue]:
    """编号 ↔ 批注一一对应，且 .rvstat 声明的数量与正文实际一致（§4）。"""
    paper = _section_bodies(body).get("m-resume")
    if paper is None:
        return []

    aside = re.search(r'<aside\s+class="rvside"[^>]*>(.*?)</aside>', paper, re.S)
    if not aside:
        # 没有右栏就不是一份批改稿（例如整块换成了"这一版可以原样用"），但仍要能自证。
        if _SUP_MARK.search(paper):
            return [LintIssue("redline-marks", "正文有改动编号，右栏批注却整块不见了")]
        return []

    body_marks = _SUP_MARK.findall(paper)
    note_marks = _NOTE_MARK.findall(aside.group(1))
    issues: list[LintIssue] = []

    body_numbers = [int(number) for _cls, number in body_marks]
    note_numbers = [int(number) for number in note_marks]
    if sorted(body_numbers) != list(range(1, len(body_numbers) + 1)):
        issues.append(LintIssue("redline-numbering", f"正文编号不连续：{sorted(body_numbers)}"))
    if sorted(note_numbers) != sorted(body_numbers):
        issues.append(
            LintIssue(
                "redline-numbering",
                f"编号与批注不是一一对应：正文 {sorted(body_numbers)}，批注 {sorted(note_numbers)}",
            )
        )

    key_marks = sum(1 for cls, _number in body_marks if "key" in cls)
    key_notes = len(re.findall(r'<div\s+class="note key"', aside.group(1)))
    if key_marks != key_notes:
        issues.append(LintIssue("redline-numbering", f"标了「关键」的正文 {key_marks} 处，批注 {key_notes} 条"))

    declared = _RVSTAT.search(paper)
    if not declared:
        issues.append(LintIssue("redline-count", "批改稿顶部没有 .rvstat 那一句计数"))
        return issues
    statement = _strip_tags(declared.group(1))
    if "无需改动" in statement:
        if body_marks:
            issues.append(LintIssue("redline-count", "声明「无需改动」，正文却还有改动编号"))
        return issues
    numbers = [int(n) for n in re.findall(r"\d+", statement)]
    if not numbers:
        issues.append(LintIssue("redline-count", f".rvstat 里没有数字：{statement!r}"))
        return issues
    if numbers[0] != len(body_marks):
        issues.append(LintIssue("redline-count", f"声明共 {numbers[0]} 处，正文实际 {len(body_marks)} 处"))
    if len(numbers) > 1 and numbers[1] != key_marks:
        issues.append(LintIssue("redline-count", f"声明关键 {numbers[1]} 处，正文实际 {key_marks} 处"))
    if "可选优化" in statement and key_marks:
        issues.append(LintIssue("redline-count", "声明「没有必改项」，正文却有关键项编号"))
    return issues


def _check_followup_labels(readable: str) -> list[LintIssue]:
    """追问标签可以是「权衡/代价」这种复合写法，但每个成分都必须在词表里。

    类型是题型分布统计的分组键：飘出去的那一个不会报错，只会在分布里数不到，
    于是标题上写"项目深挖 9 题"而屏上是 10 题。
    """
    unknown: set[str] = set()
    for label in {kind for kind in _FOLLOWUP_LABEL.findall(readable) if kind}:
        for atom in label.replace("……", "").replace("。", "").split("/"):
            atom = atom.strip()
            if atom and atom not in FOLLOWUP_ATOMS:
                unknown.add(atom)
    if unknown:
        return [LintIssue("followup-kind", f"追问类型标签不在词表里：{sorted(unknown)}（题型分布会数不到它们）")]
    return []


def _numeric_cells(row_html: str) -> list[int]:
    """一行里 `<td class="n">` 那种纯数字单元格（得分列、满分列）。

    只取这两列：待优化点那一栏的正文里全是数字（"92%、800 条、50 案例"），
    连它一起扫的话，这份检查第一个就把合格报告判成不合格。
    """
    values: list[int] = []
    for cell in re.findall(r'<td\s+class="n"[^>]*>(.*?)</td>', row_html, re.S):
        text = _strip_tags(cell).strip()
        if re.fullmatch(r"\d+", text):
            values.append(int(text))
    return values


def _table_rows(html: str) -> list[str]:
    """整行连开标签一起返回。只返回内部内容的话，`class="total"` 就丢了，
    合计行会被当成一条普通维度行加进求和里——那道检查于是永远不跑。"""
    return re.findall(r"<tr[^>]*>.*?</tr>", html, re.S)


def _check_total_row_matches_dimensions(body: str) -> list[LintIssue]:
    """合计行必须等于逐维相加：总分有两个来源就是两个权威。"""
    score_section = _section_bodies(body).get("m-score")
    if not score_section:
        return []

    scores: list[int] = []
    fulls: list[int] = []
    declared: tuple[int, int] | None = None
    for row_html in _table_rows(score_section):
        cells = _numeric_cells(row_html)
        if 'class="total"' in row_html:
            if len(cells) >= 2:
                declared = (cells[0], cells[1])
            continue
        if "<th" in row_html or len(cells) < 2:
            continue
        scores.append(cells[0])
        fulls.append(cells[1])

    if declared is None or len(scores) < 2:
        return []
    summed_scores = sum(scores)
    summed_fulls = sum(fulls)
    if (summed_scores, summed_fulls) != declared:
        return [
            LintIssue(
                "total-authority",
                f"合计行写 {declared[0]}/{declared[1]}，逐维相加是 {summed_scores}/{summed_fulls}——总分只能有一个来源",
            )
        ]
    return []


def _check_dimension_notes(body: str) -> list[LintIssue]:
    """§3 的交付门：待优化点这一栏不能空，也不能整表都是通用建议。

    两条都刻意留了余地：
    * **没评分的那一维跳过**——那一行本来就该是"未评分"，不是"待优化点没写"，
      把"未知"当成不合格会推翻 D230 定的那条"缺维度不等于 0 分"的口径；
    * **单条飘出去只数不拦**（拦的是整表都没锚点）。四份真样本 28 条里有一条合法地没带引号，
      按单条硬拦会把合格报告判死；而"整表通用"是改造前那一族的确定形状，判死不会冤枉。
      飘出去的那一条由 `Report.note_anchor_stats` 数出来，对内可查。
    """
    score_section = _section_bodies(body).get("m-score")
    if not score_section:
        return []

    issues: list[LintIssue] = []
    scored = 0
    anchored = 0
    for row_html in _table_rows(score_section):
        if 'class="total"' in row_html or "<th" in row_html:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
        if len(cells) < 4:
            continue
        score_text = _strip_tags(cells[1]).strip()
        if not re.fullmatch(r"\d+", score_text):
            continue  # 未评分那一行不参与这条判断
        scored += 1
        note = _strip_tags(cells[3]).strip()
        if not note or _NOTE_ABSENT in note:
            issues.append(
                LintIssue("note-missing", f"{_strip_tags(cells[0]).strip()}：给了 {score_text} 分却没写待优化点")
            )
            continue
        if is_anchored_note(note):
            anchored += 1

    if scored and anchored == 0:
        issues.append(
            LintIssue(
                "notes-unanchored",
                f"七维的待优化点没有一条点名到简历里的具体位置（{scored} 条都是通用建议）——这一份是改造前那种写法",
            )
        )
    return issues


def _check_no_external_resources(html: str) -> list[LintIssue]:
    """纯内联 CSS/JS、无 CDN、无字体、无图片：离线双击可开是这份交付物的定义。

    注释要先剥掉——成品文件顶部那段规范原文里写着"无 CDN、无字体、无图片"这句话本身。
    """
    code = _COMMENT.sub(" ", html)
    offenders: list[str] = []
    for match in re.finditer(r"<(?:script|link|img|iframe)\b[^>]*>", code, re.I):
        tag = match.group(0)
        if re.search(r'(?:src|href)\s*=\s*["\']\s*(?:https?:|//|ftp:|file:)', tag, re.I):
            offenders.append(tag[:80])
    if re.search(r'@import|url\(\s*["\']?(?:https?:)?//', code):
        offenders.append("@import 或 url(//…)")
    if offenders:
        return [LintIssue("external-resource", f"引用了外部资源，报告必须离线双击可开：{offenders[:3]}")]
    return []


def format_issues(issues: list[LintIssue]) -> str:
    return "\n".join(str(issue) for issue in issues)


__all__ = [
    "FOLLOWUP_ATOMS",
    "FORBIDDEN_ELLIPSIS",
    "FORBIDDEN_MECHANISM_WORDS",
    "MODULES",
    "MODULE_IDS",
    "LintIssue",
    "format_issues",
    "lint_report_html",
]
