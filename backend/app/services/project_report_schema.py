"""单项目分析的数据契约：四大节 + 「逐字摘录」那一节的构造。

1.2 那一节**不过模型**——它是候选人自己写的项目原文，让模型"摘录"只会引入改写与编造，
而这一节的定义恰恰是"逐字、未作润色"。切段用的是原文里的栏目标题（项目描述 / 核心职责 /
项目成果），标题一个都不在就整段铺出来并明写"这份简历里没有分栏标题"，不硬凑三栏。

第四节（面试准备 20 题）是同一条作业上的**第二次模型调用**：他点的口径是"前三节一次跑，
20 题按按钮再跑"，所以 `questions` 有三态——没生成、这一份出局所以不出、生成好了。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# 第四节三态。`deferred` 是命中红线那一份的合法终态，不是失败。
QUESTIONS_NOT_GENERATED = "not_generated"
QUESTIONS_DEFERRED = "deferred"
QUESTIONS_READY = "ready"

# 命中红线的后果措辞（对外一句人话，不写"门禁/阈值"那类机制字眼）。
EXCLUDED_NOTE = "这一份项目分析不给总分与等级：下面六条里有一条踩中了，项目分本身就不再作数。"

# 第四节在这一份里的合法终态：命中红线所以不出题（不是失败，也不许写成"模型出错了"）。
QUESTIONS_DEFERRED_NOTE = (
    "这一节先不出题。这个项目踩中了一条一票否决，面试官顺着任何一个话头问下去都会回到同一个洞，"
    "此时背二十段口述稿记住的是话术而不是内容。先把上面点到的那条解开——"
    "把缺的实测值跑出来、把不是本人主导的部分改回原样——这一节再做价值更大。"
)

# 命中红线那份，接口层拒绝续跑第四节时给的那一句（同一件事的另一种场合，措辞只有一处权威）。
EXCLUDED_NO_QUESTIONS_MESSAGE = "这一份命中了一条一票否决，按口径不出二十道题：先解开那条红线，这一节才有价值。"

# 1.2 的三栏标题词表。
_SECTION_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("项目描述", ("项目描述", "项目简介", "项目概述", "项目背景")),
    ("个人职责", ("个人职责", "核心职责", "主要职责", "职责分工", "工作内容", "责任描述", "职责")),
    ("项目成果", ("项目成果", "量化成果", "项目业绩", "业绩", "成果")),
)

_LEADING_BULLET = re.compile(r"^\s*(?:[-•*·]|\d+[.)、]|[（(]\d+[)）])\s*")
_COLON = re.compile(r"^[：:]")

# 候选人视图里不许出现的内部键（证据与被拒清单只对内，沿用报告那一族的口径）。
_INTERNAL_KEYS = (
    "provenance",
    "stage_errors",
    "red_line_rejected",
    "diagram_rejected",
    "advice_rejected",
    "questions_rejected",
    "metric_gap_evidence",
    "stack_footprint",
    "peer_totals",
)


def clean_line(line: str) -> str:
    """剥掉行首的项目符号与编号，正文一字不动。

    只剥最外层前缀（`"1. 负责……"` → `"负责……"`），剥完仍是原文的子串，
    所以"逐字命中"这条校验不会因为剥前缀而失效。
    """
    return _COLON.sub("", _LEADING_BULLET.sub("", (line or "").strip()).strip()).strip()


def _marker_of(line: str) -> tuple[str, str] | None:
    """这一行是不是栏目标题；是的话返回 (栏名, 标题后面跟着的正文)。

    只认"标题 + 冒号"或"整行就是标题"两种形状——不然一句"成果展示平台负责……"
    会因为开头撞见"成果"两个字就被当成栏目切换，正文反而丢了。
    """
    for label, words in _SECTION_MARKERS:
        for word in words:
            if line == word:
                return label, ""
            if line.startswith(word) and line[len(word)] in "：:":
                return label, _COLON.sub("", line[len(word) :]).strip()
    return None


def build_project_excerpt(entry: dict[str, Any] | None, project_index: int) -> dict[str, Any]:
    """把简历里那一条项目读成 1.2 那张表 + 分栏原文，全程不碰模型。"""
    data = entry if isinstance(entry, dict) else {}
    desc = str(data.get("desc") or "").strip()
    tech = [str(t).strip() for t in (data.get("tech") or data.get("tech_stack") or []) if str(t).strip()]
    period = " - ".join(x for x in (str(data.get("start") or "").strip(), str(data.get("end") or "").strip()) if x)

    ordered: list[str] = []
    buckets: dict[str, list[str]] = {}
    unassigned: list[str] = []
    current = ""
    for raw_line in desc.splitlines():
        line = clean_line(raw_line)
        if not line:
            continue
        hit = _marker_of(line)
        if hit:
            label, tail = hit
            current = label
            if label not in buckets:
                buckets[label] = []
                ordered.append(label)
            if len(tail) >= 4:
                buckets[label].append(tail)
            continue
        if current:
            buckets[current].append(line)
        else:
            unassigned.append(line)

    sections: list[dict[str, Any]] = []
    if unassigned:
        sections.append({"label": "项目原文（这份简历里没有分栏标题）", "lines": unassigned})
    for label in ordered:
        if buckets[label]:
            sections.append({"label": label + "（简历原文）", "lines": buckets[label]})
    if not sections and desc:
        sections.append({"label": "项目原文（简历原文）", "lines": [desc]})

    return {
        "project_index": project_index,
        "rank": project_index + 1,
        "code": f"PJ-{project_index + 1:02d}",
        "name": str(data.get("name") or "").strip(),
        "role": str(data.get("role") or "").strip(),
        "period": period,
        "tech": tech,
        "sections": sections,
    }


def excerpt_text(excerpt: dict[str, Any]) -> str:
    """把分栏原文摊成一段纯文本——红线证据与"逐字命中"的那根被检串。"""
    lines: list[str] = []
    for section in excerpt.get("sections") or []:
        lines.extend(section.get("lines") or [])
    return "\n".join(lines)


def raw_entry_text(entry: dict[str, Any] | None) -> str:
    """一条项目条目里所有可引用的原文（描述 + 技术栈 + 角色 + 时间），给逐字校验当全集。"""
    data = entry if isinstance(entry, dict) else {}
    parts = [str(data.get("desc") or "")]
    parts.append("、".join(str(t) for t in (data.get("tech") or data.get("tech_stack") or [])))
    parts.append(str(data.get("role") or ""))
    parts.append(str(data.get("name") or ""))
    return "\n".join(parts)


@dataclass
class ProjectReport:
    """一份单项目分析。四大节的字段全在这，对内证据另走 `_INTERNAL_KEYS` 那一批。"""

    resume_id: int
    project_index: int
    user_id: int | None = None
    jd_id: int | None = None
    target_position: str = ""
    report_date: str = ""

    # 表头那一行（项目画像：垂类 · 场景 · 技术主线 · 组件）与 1.2 的原文。
    portrait: dict[str, Any] = field(default_factory=dict)
    excerpt: dict[str, Any] = field(default_factory=dict)

    # 一、项目档案
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    total_score: int | None = None
    grade: str | None = None
    grade_desc: str = ""
    grade_scale: str = ""
    excluded_by: list[dict[str, Any]] = field(default_factory=list)
    difficulty: dict[str, Any] = field(default_factory=dict)
    highlights: list[dict[str, Any]] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)
    contribution: dict[str, Any] = field(default_factory=dict)

    # 二、三、四节。前两周是"跑没跑出来"，第四节还多一个"按按钮才跑"。
    diagrams: dict[str, Any] | None = None
    advice: dict[str, Any] | None = None
    questions: dict[str, Any] | None = None

    # 对内
    provenance: dict[str, Any] = field(default_factory=dict)
    stage_errors: dict[str, str] = field(default_factory=dict)
    red_line_rejected: list[dict[str, Any]] = field(default_factory=list)
    diagram_rejected: list[dict[str, Any]] = field(default_factory=list)
    advice_rejected: list[dict[str, Any]] = field(default_factory=list)
    questions_rejected: list[dict[str, Any]] = field(default_factory=list)
    metric_gap_evidence: list[dict[str, str]] = field(default_factory=list)
    stack_footprint: dict[str, Any] = field(default_factory=dict)
    peer_totals: list[dict[str, Any]] = field(default_factory=list)

    def is_excluded(self) -> bool:
        return bool(self.excluded_by)

    def questions_state(self) -> str:
        if self.questions is None:
            return QUESTIONS_NOT_GENERATED
        if self.questions.get(QUESTIONS_DEFERRED):
            return QUESTIONS_DEFERRED
        return QUESTIONS_READY

    def score_cell(self) -> str:
        """合计那一格对外显示什么。命中红线时**不给数字**——一份既写着出局又写着 85 分的表，
        候选人不会知道该信哪一个，这正是"口径自洽"最先崩的地方。"""
        if self.is_excluded():
            return "不作数"
        return "未评分" if self.total_score is None else str(self.total_score)

    def to_public_dict(self) -> dict[str, Any]:
        data = self.to_internal_dict()
        return {key: value for key, value in data.items() if key not in _INTERNAL_KEYS}

    def to_internal_dict(self) -> dict[str, Any]:
        return {
            "resume_id": self.resume_id,
            "project_index": self.project_index,
            "jd_id": self.jd_id,
            "target_position": self.target_position,
            "report_date": self.report_date,
            "portrait": self.portrait,
            "excerpt": self.excerpt,
            "dimensions": self.dimensions,
            "total_score": None if self.is_excluded() else self.total_score,
            "grade": None if self.is_excluded() else self.grade,
            "grade_desc": self.grade_desc,
            "grade_scale": self.grade_scale,
            "score_cell": self.score_cell(),
            "excluded_by": self.excluded_by,
            "excluded": self.is_excluded(),
            "excluded_note": EXCLUDED_NOTE if self.is_excluded() else "",
            "difficulty": self.difficulty,
            "highlights": self.highlights,
            "hooks": self.hooks,
            "risks": self.risks,
            "contribution": self.contribution,
            "diagrams": self.diagrams,
            "advice": self.advice,
            "questions": self.questions,
            "questions_state": self.questions_state(),
            "provenance": self.provenance,
            "stage_errors": self.stage_errors,
            "red_line_rejected": self.red_line_rejected,
            "diagram_rejected": self.diagram_rejected,
            "advice_rejected": self.advice_rejected,
            "questions_rejected": self.questions_rejected,
            "metric_gap_evidence": self.metric_gap_evidence,
            "stack_footprint": self.stack_footprint,
            "peer_totals": self.peer_totals,
        }


def report_from_dict(data: dict[str, Any]) -> ProjectReport:
    """把库里那份候选人视图还原回来（下载 HTML 与前端二次生成都走它）。

    对内那一批键本来就没入库，所以这里不需要清字段，也不需要防它漏出去。
    """
    report = ProjectReport(
        resume_id=int(data.get("resume_id") or 0),
        project_index=int(data.get("project_index") or 0),
        jd_id=data.get("jd_id"),
        target_position=data.get("target_position") or "",
        report_date=data.get("report_date") or "",
        portrait=data.get("portrait") or {},
        excerpt=data.get("excerpt") or {},
        dimensions=data.get("dimensions") or [],
        grade_desc=data.get("grade_desc") or "",
        grade_scale=data.get("grade_scale") or "",
        excluded_by=data.get("excluded_by") or [],
        difficulty=data.get("difficulty") or {},
        highlights=data.get("highlights") or [],
        hooks=data.get("hooks") or [],
        risks=data.get("risks") or [],
        contribution=data.get("contribution") or {},
        diagrams=data.get("diagrams"),
        advice=data.get("advice"),
        questions=data.get("questions"),
    )
    report.total_score = data.get("total_score")
    report.grade = data.get("grade")
    return report


__all__ = [
    "EXCLUDED_NO_QUESTIONS_MESSAGE",
    "EXCLUDED_NOTE",
    "QUESTIONS_DEFERRED",
    "QUESTIONS_NOT_GENERATED",
    "QUESTIONS_READY",
    "ProjectReport",
    "build_project_excerpt",
    "clean_line",
    "excerpt_text",
    "raw_entry_text",
    "report_from_dict",
]
