"""组合档案的数据契约：四大节 + 「选中项目的逐字摘录」+ 表头那几个派生量。

与单项目那一族同一条第一原则：**逐字摘录一个字都不过模型**。这里唯一的区别是
摘录是**几段**——每个被选中的项目各一块，全部从 `parsed_json` 里切出来，
组合层的任何一句"这三个项目的共同骨架是……"都不能反过来改写它们。

表头那一排（组合评分 / 组合难度 / 项目数 / 单项目均分）里，
**只有"单项目均分"是一个可能整格留空的数**：它取的是已经跑过且给得出分的单项目分析，
一份都没跑过时写的是 `AVERAGE_ABSENT_NOTE`（那句人话），不是 0、不是猜、不是模型自报。

第四节（跨项目面试 12 题）与单项目那一族同一条形状：前三节一次跑完，
第四节按按钮再跑，所以 `questions` 也有三态——没生成、这一份出局所以不出、生成好了。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.portfolio_report_rubric import average_of
from app.services.project_report_schema import build_project_excerpt, raw_entry_text

# 第四节三态（与单项目那一族同一套词，前端与机检都按这三态判断）。
QUESTIONS_NOT_GENERATED = "not_generated"
QUESTIONS_DEFERRED = "deferred"
QUESTIONS_READY = "ready"

# 组合最少要几个项目。少于这个数不是"组合"，接口层直接拒（不是红线，是请求不成立：
# 一条永远不会在合法输入上命中的规则不配当门）。
MIN_PROJECTS = 2

# 命中红线的后果（对外一句人话，不写"门禁/阈值"那类机制字眼）。
EXCLUDED_NOTE = "这一份组合分析不给总分与等级：下面几条里有一条踩中了，几个项目叠在一起的意义本身就不作数了。"

# 出局那份不许续跑第四节，接口层给的那一句（与 EXCLUDED_NOTE 是同一件事的两个场合）。
EXCLUDED_NO_QUESTIONS_MESSAGE = "这一份命中了一条一票否决，按口径不出跨项目的题：先把那一条解开，这一节才有价值。"

QUESTIONS_DEFERRED_NOTE = (
    "这一节先不出题。这一组项目踩中了一条一票否决——面试官把几个项目放在一起看时，"
    "顺着任何一个话头问下去都会回到同一个洞，此时背十二段口述稿记住的是话术而不是内容。"
    "先把上面点到的那一条解开：把重复的那个项目换成真有差异的那一个，"
    "把不是本人主导的部分改回原样——这一节再做价值更大。"
)

# 表头「单项目均分」那一格在一份都没跑过时的措辞。
AVERAGE_ABSENT_NOTE = "还没跑过单项目分析，这一格空着"

# 候选人视图里不许出现的内部键（证据与被拒清单只对内，沿用报告那一族的口径）。
_INTERNAL_KEYS = (
    "provenance",
    "stage_errors",
    "red_line_rejected",
    "compare_rejected",
    "capability_rejected",
    "diagram_rejected",
    "advice_rejected",
    "questions_rejected",
    "per_project_metric_gaps",
    "stack_reuse",
    "duplicate_evidence",
    "peer_scores",
    "shared_stack_dropped",
)


def project_code(project_index: int) -> str:
    return f"PJ-{int(project_index) + 1:02d}"


def project_label(excerpt: dict[str, Any]) -> str:
    """表头与对比表列名用的那一句："项目 2 · 金融合规"。"""
    name = str(excerpt.get("name") or "").strip() or f"项目经历 {int(excerpt.get('rank') or 1)}"
    return f"项目 {int(excerpt.get('rank') or 1)} · {name}"


def combo_signature(indices: list[int]) -> str:
    """(人, 简历, 选中了哪几个项目) 的规范化键——顺序无关，重复去掉。"""
    return ",".join(str(int(i)) for i in sorted({int(i) for i in indices}))


def build_portfolio_excerpts(entries: list[dict[str, Any]], indices: list[int]) -> list[dict[str, Any]]:
    """按简历里的顺序（不是勾选顺序）把选中项目各切一块逐字摘录。"""
    out: list[dict[str, Any]] = []
    for index in sorted({int(i) for i in indices}):
        out.append(build_project_excerpt(entries[index] if index < len(entries) else None, index))
    return out


def universe_text(excerpts: list[dict[str, Any]]) -> str:
    """被选项目原文的并集——红线证据、共用栈与"逐字命中"那根被检串都在这里。"""
    parts: list[str] = []
    for excerpt in excerpts:
        for section in excerpt.get("sections") or []:
            parts.extend(section.get("lines") or [])
    return "\n".join(parts)


def raw_entries_text(entries: list[dict[str, Any]], indices: list[int]) -> str:
    """选中项目的**全部**可引用原文（含技术栈、角色、项目名），给逐字校验当全集。"""
    return "\n".join(raw_entry_text(entries[i]) for i in sorted({int(x) for x in indices}) if i < len(entries))


@dataclass
class PortfolioReport:
    """一份组合档案。四大节字段全在这，对内证据另走 `_INTERNAL_KEYS` 那一批。"""

    resume_id: int
    project_indices: list[int] = field(default_factory=list)
    user_id: int | None = None
    jd_id: int | None = None
    target_position: str = ""
    report_date: str = ""

    # 表头那一排与每个被选项目的逐字摘录。
    summary: dict[str, Any] = field(default_factory=dict)
    projects: list[dict[str, Any]] = field(default_factory=list)

    # 一、组合档案
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    total_score: int | None = None
    grade: str | None = None
    grade_desc: str = ""
    grade_scale: str = ""
    excluded_by: list[dict[str, Any]] = field(default_factory=list)
    difficulty: dict[str, Any] = field(default_factory=dict)
    compare: dict[str, Any] = field(default_factory=dict)
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    risks: list[dict[str, Any]] = field(default_factory=list)

    # 二、三、四节。
    diagrams: dict[str, Any] | None = None
    advice: dict[str, Any] | None = None
    questions: dict[str, Any] | None = None

    # 对内
    provenance: dict[str, Any] = field(default_factory=dict)
    stage_errors: dict[str, str] = field(default_factory=dict)
    red_line_rejected: list[dict[str, Any]] = field(default_factory=list)
    compare_rejected: list[dict[str, Any]] = field(default_factory=list)
    capability_rejected: list[dict[str, Any]] = field(default_factory=list)
    diagram_rejected: list[dict[str, Any]] = field(default_factory=list)
    advice_rejected: list[dict[str, Any]] = field(default_factory=list)
    questions_rejected: list[dict[str, Any]] = field(default_factory=list)
    per_project_metric_gaps: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    stack_reuse: dict[str, Any] = field(default_factory=dict)
    duplicate_evidence: list[dict[str, Any]] = field(default_factory=list)
    peer_scores: list[dict[str, Any]] = field(default_factory=list)
    shared_stack_dropped: list[str] = field(default_factory=list)

    @property
    def project_count(self) -> int:
        return len(self.project_indices)

    @property
    def combo_key(self) -> str:
        """这一份是"哪几个项目叠在一起"的规范化键——作业去重与日志都按它。"""
        return combo_signature(self.project_indices)

    def is_excluded(self) -> bool:
        return bool(self.excluded_by)

    def questions_state(self) -> str:
        if self.questions is None:
            return QUESTIONS_NOT_GENERATED
        if self.questions.get(QUESTIONS_DEFERRED):
            return QUESTIONS_DEFERRED
        return QUESTIONS_READY

    def score_cell(self) -> str:
        """合计那一格对外显示什么。命中红线时**不给数字**——一份既写着出局又写着 94 分的表，
        候选人不知道该信哪一个。"""
        if self.is_excluded():
            return "不作数"
        return "未评分" if self.total_score is None else str(self.total_score)

    def average_cell(self) -> str:
        """表头「单项目均分」那一格：有就跑出数来，一份都没有就写那句人话。"""
        known = [row.get("total") for row in self.peer_scores if row.get("total") is not None]
        if not known:
            return AVERAGE_ABSENT_NOTE
        value = average_of(known)
        if value is None:
            return AVERAGE_ABSENT_NOTE
        scored = f"{value:g}"
        if len(known) < self.project_count:
            return f"{scored}（只有 {len(known)}/{self.project_count} 个跑过单项目分析）"
        return scored

    def to_public_dict(self) -> dict[str, Any]:
        data = self.to_internal_dict()
        return {key: value for key, value in data.items() if key not in _INTERNAL_KEYS}

    def to_internal_dict(self) -> dict[str, Any]:
        known = [row.get("total") for row in self.peer_scores if row.get("total") is not None]
        return {
            "resume_id": self.resume_id,
            "project_indices": list(self.project_indices),
            "project_count": self.project_count,
            "combo_key": combo_signature(self.project_indices),
            "jd_id": self.jd_id,
            "target_position": self.target_position,
            "report_date": self.report_date,
            "summary": self.summary,
            "projects": self.projects,
            "dimensions": self.dimensions,
            "total_score": None if self.is_excluded() else self.total_score,
            "grade": None if self.is_excluded() else self.grade,
            "grade_desc": self.grade_desc,
            "grade_scale": self.grade_scale,
            "score_cell": self.score_cell(),
            "average_score": average_of(known) if known else None,
            "average_cell": self.average_cell(),
            "excluded_by": self.excluded_by,
            "excluded": self.is_excluded(),
            "excluded_note": EXCLUDED_NOTE if self.is_excluded() else "",
            "difficulty": self.difficulty,
            "compare": self.compare,
            "capabilities": self.capabilities,
            "risks": self.risks,
            "diagrams": self.diagrams,
            "advice": self.advice,
            "questions": self.questions,
            "questions_state": self.questions_state(),
            "provenance": self.provenance,
            "stage_errors": self.stage_errors,
            "red_line_rejected": self.red_line_rejected,
            "compare_rejected": self.compare_rejected,
            "capability_rejected": self.capability_rejected,
            "diagram_rejected": self.diagram_rejected,
            "advice_rejected": self.advice_rejected,
            "questions_rejected": self.questions_rejected,
            "per_project_metric_gaps": self.per_project_metric_gaps,
            "stack_reuse": self.stack_reuse,
            "duplicate_evidence": self.duplicate_evidence,
            "peer_scores": self.peer_scores,
            "shared_stack_dropped": self.shared_stack_dropped,
        }


def _capability_cells_int_keys(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 1.3 那几行的格子键从字符串还原成整数。

    JSON 的键只能是字符串：入库前 `cells` 是 `{0: "重点覆盖"}`，取出来变成 `{"0": ...}`，
    而渲染器与机检都按**项目序号**（int）取格子。这一处不还原，2.1 那张矩阵在
    "下载 / 轮询"这条路上会整片画成空白，机检 then 报 KeyError（2026-10-14 作业链测试照出来的）。
    """
    out: list[dict[str, Any]] = []
    for row in rows or []:
        data = dict(row)
        cells = data.get("cells") or {}
        data["cells"] = {int(key): value for key, value in cells.items()}
        out.append(data)
    return out


def report_from_dict(data: dict[str, Any]) -> PortfolioReport:
    """把库里那份候选人视图还原回来（下载 HTML 与前端二次生成都走它）。

    对内那一批键本来就没入库，所以这里不需要清字段，也不需要防它漏出去。
    """
    report = PortfolioReport(
        resume_id=int(data.get("resume_id") or 0),
        project_indices=[int(i) for i in (data.get("project_indices") or [])],
        jd_id=data.get("jd_id"),
        target_position=data.get("target_position") or "",
        report_date=data.get("report_date") or "",
        summary=data.get("summary") or {},
        projects=data.get("projects") or [],
        dimensions=data.get("dimensions") or [],
        grade_desc=data.get("grade_desc") or "",
        grade_scale=data.get("grade_scale") or "",
        excluded_by=data.get("excluded_by") or [],
        difficulty=data.get("difficulty") or {},
        compare=data.get("compare") or {},
        capabilities=_capability_cells_int_keys(data.get("capabilities") or []),
        risks=data.get("risks") or [],
        diagrams=data.get("diagrams"),
        advice=data.get("advice"),
        questions=data.get("questions"),
    )
    report.total_score = data.get("total_score")
    report.grade = data.get("grade")
    return report


__all__ = [
    "AVERAGE_ABSENT_NOTE",
    "EXCLUDED_NO_QUESTIONS_MESSAGE",
    "EXCLUDED_NOTE",
    "MIN_PROJECTS",
    "QUESTIONS_DEFERRED",
    "QUESTIONS_DEFERRED_NOTE",
    "QUESTIONS_NOT_GENERATED",
    "QUESTIONS_READY",
    "PortfolioReport",
    "build_portfolio_excerpts",
    "combo_signature",
    "project_code",
    "project_label",
    "raw_entries_text",
    "report_from_dict",
    "universe_text",
]
