"""评估报告的数据契约：六个模块 + 批改稿的可应用接口。

为什么批改稿要自己算"改后整块文本"（`Redline.edits_for_apply`）而不是让前端拼：
应用那一步走的仍是 `apply_block_edits` 那条既有链路——快照、撤销、重算匹配分、
`expected_original` 防过期锚点全在那一侧，句级记号只是**另一种寻址方式**，
不是第二条写入路径。开第二条写入路径就等于给"改简历"这件事两个权威。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services import resume_report_rubric as rubric

# §4 计数三档。措辞照成品，机检认的就是这几个词。
STAT_MODE_CHANGES = "changes"
STAT_MODE_OPTIONAL = "optional"
STAT_MODE_UNCHANGED = "unchanged"

# §6：总分不达标时第四模块整块换成这一段。对外不得出现机制字眼，所以这里只说价值与顺序。
INTERVIEW_DEFERRED_NOTE = (
    "这一节先不生成。现在这份简历的七维合计还没到能让面试官顺着你的描述往下问的水平，"
    "此时准备二十道题的口述稿，记住的是话术而不是内容，面试里一追就散。"
    "先把第三节里标了「关键」的几处改完、把【待补】的数跑出来，这一节再做价值更大。"
)

# 候选人视图里不许出现的内部键（同一个量只留一个权威；被拒条目里可能带模型原文）。
_INTERNAL_KEYS = ("model_reported_total", "provenance", "stage_errors", "redline_rejected", "interview_rejected")


@dataclass
class RedlineEdit:
    """一处就地批改：`del_text` 是原话，`ins_text` 是建议改成的内容。"""

    mark: int
    block_id: str
    del_text: str
    ins_text: str
    note: str
    key: bool = False

    def to_html(self, paper_text: str) -> str:
        """渲染成 `…<del>原话</del><ins>改后</ins><sup class="mk">N</sup>…` 里的那一段。

        调用方负责转义；这里只保证顺序与 class 名与成品一致（机检按 class 名数编号）。
        """
        star = " key" if self.key else ""
        return f'<del>{self.del_text}</del><ins>{self.ins_text}</ins><sup class="mk{star}">{self.mark}</sup>'


@dataclass
class RedlineBlock:
    block_id: str
    label: str
    text: str
    edits: list[RedlineEdit] = field(default_factory=list)
    # False = 这一栏是字段值（基本信息、经历抬头、技术栈、教育背景），
    # 批改照样标出来，但不走"采纳"那条写入路径，见 `build_report_sections`。
    editable: bool = True


@dataclass
class Redline:
    blocks: list[RedlineBlock]
    mode: str = STAT_MODE_CHANGES
    free_note: str = ""

    @property
    def edits(self) -> list[RedlineEdit]:
        return [edit for block in self.blocks for edit in block.edits]

    @property
    def total(self) -> int:
        return len(self.edits)

    @property
    def key_total(self) -> int:
        return sum(1 for edit in self.edits if edit.key)

    def stat_sentence(self) -> str:
        if self.mode == STAT_MODE_UNCHANGED:
            return "这一版可以原样用，无需改动"
        if self.mode == STAT_MODE_OPTIONAL:
            return f"共 {self.total} 处可选优化，没有必改项"
        return f"共 {self.total} 处改动，其中 {self.key_total} 处是关键项（改完并补齐【待补】数据就能投）"

    def edits_for_apply(self, accepted_marks: list[int] | None = None) -> list[dict[str, Any]]:
        """把选中的句级批改折成整块 `原文 → 改后`，交给 `apply_block_edits`。

        `accepted_marks=None` 表示全部；传子集时按 `mark` 挑。顺序按块内编号。
        `editable: False` 的块（基本信息、经历抬头、技术栈、教育背景）直接跳过——
        那一栏的改动要候选人在简历文件里自己落笔，`parsed_json` 里没有对应的可写字段。
        """
        out: list[dict[str, Any]] = []
        for block in self.blocks:
            if not block.editable:
                continue
            chosen = [e for e in block.edits if accepted_marks is None or e.mark in accepted_marks]
            if not chosen:
                continue
            text = block.text
            for edit in sorted(chosen, key=lambda e: e.mark):
                replaced = text.replace(edit.del_text, edit.ins_text, 1)
                if replaced == text:
                    continue
                text = replaced
            if text != block.text:
                out.append(
                    {
                        "block_id": block.block_id,
                        "expected_original": block.text,
                        "proposed_text": text,
                    }
                )
        return out


@dataclass
class Report:
    resume_id: int
    user_id: int | None = None
    jd_id: int | None = None
    target_position: str = ""
    report_date: str = ""
    verdict: dict[str, Any] = field(default_factory=dict)
    dimensions: list[dict[str, Any]] = field(default_factory=list)
    total_score: int | None = None
    grade: str | None = None
    grade_desc: str = ""
    grade_scale: str = ""
    to_next_grade: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    competition: dict[str, Any] = field(default_factory=dict)
    model_reported_total: int | None = None
    redline: Redline | None = None
    interview: dict[str, Any] | None = None
    apply_strategy: dict[str, Any] | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    stage_errors: dict[str, str] = field(default_factory=dict)
    # 批改稿的版面（含不可写回的信息块），渲染器按它铺原文；被复核拒掉的清单只对内。
    sections: list[dict[str, Any]] = field(default_factory=list)
    redline_rejected: list[dict[str, Any]] = field(default_factory=list)
    interview_rejected: list[dict[str, Any]] = field(default_factory=list)
    # §7 那两处个性化。算在数据层而不是算在 HTML 渲染器里：应用内那一页与下载的
    # 那一份是同一件事的两个形态，各算一处迟早长得不一样。
    personalization: dict[str, str] = field(default_factory=dict)

    def interview_allowed(self) -> bool:
        return rubric.interview_allowed(self.total_score)

    def to_public_dict(self) -> dict[str, Any]:
        """候选人视图：对内证据一律不上屏。"""
        data = self.to_internal_dict()
        return {key: value for key, value in data.items() if key not in _INTERNAL_KEYS}

    def to_internal_dict(self) -> dict[str, Any]:
        return {
            "resume_id": self.resume_id,
            "jd_id": self.jd_id,
            "target_position": self.target_position,
            "report_date": self.report_date,
            "verdict": self.verdict,
            "dimensions": self.dimensions,
            "total_score": self.total_score,
            "grade": self.grade,
            "grade_desc": self.grade_desc,
            "grade_scale": self.grade_scale,
            "to_next_grade": self.to_next_grade,
            "missing_keywords": self.missing_keywords,
            "competition": self.competition,
            "model_reported_total": self.model_reported_total,
            "redline": None if self.redline is None else _redline_dict(self.redline),
            "interview": self.interview,
            "interview_deferred": self.interview is not None and self.interview.get("deferred", False),
            "apply_strategy": self.apply_strategy,
            "sections": self.sections,
            "personalization": self.personalization,
            "provenance": self.provenance,
            "stage_errors": self.stage_errors,
            "redline_rejected": self.redline_rejected,
            "interview_rejected": self.interview_rejected,
        }


def _redline_dict(redline: Redline) -> dict[str, Any]:
    return {
        "mode": redline.mode,
        "stat": redline.stat_sentence(),
        "total": redline.total,
        "key_total": redline.key_total,
        "free_note": redline.free_note,
        "blocks": [
            {
                "block_id": block.block_id,
                "label": block.label,
                "text": block.text,
                "editable": block.editable,
                "edits": [
                    {
                        "mark": edit.mark,
                        "block_id": edit.block_id,
                        "del": edit.del_text,
                        "ins": edit.ins_text,
                        "note": edit.note,
                        "key": edit.key,
                    }
                    for edit in block.edits
                ],
            }
            for block in redline.blocks
        ],
    }


__all__ = [
    "INTERVIEW_DEFERRED_NOTE",
    "STAT_MODE_CHANGES",
    "STAT_MODE_OPTIONAL",
    "STAT_MODE_UNCHANGED",
    "Redline",
    "RedlineBlock",
    "RedlineEdit",
    "Report",
]
