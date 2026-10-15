"""组合分析的编排：前三节一次跑完，第四节（跨项目 12 题）按按钮再跑一次。

形状抄单项目那一族（作业行 + 租约 + 读路径自愈 + 阶段失败对候选人静默），
这一族特有的三件事：

* **一次要读几段原文**：选中的 2~N 个项目各一块逐字摘录，全部不过模型；
* **凡是能从清单里算出来的都不问模型**：表头的项目数与单项目均分、位次区间那一维、
  1.3 的「组合覆盖」那一列、2.3 的共用栈/差异栈——模型只能提名，服务端按格子与交集重算；
* **失败粒度跟着缺陷粒度走**（D236 那一轮的教训）：横向对比里一个数字只撤**那一格**，
  叙事主线里一条要点只撤**那一条**，不是一处不合格就让整节缺席。

红线里的「同一个项目换名字写了两遍」由服务端逐字比对（折叠后完全相同），
近似雷同只出证据不判出局——同一家公司两个项目共用一套栈是常态，判出局是必然误伤。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription, Resume
from app.models.project_report_job import STAGE_REPORT as PROJECT_STAGE_REPORT
from app.models.project_report_job import ProjectReportJob
from app.prompts.portfolio_report_advice import PORTFOLIO_REPORT_ADVICE_PROMPT
from app.prompts.portfolio_report_advice import PROMPT_VERSION as ADVICE_PROMPT_VERSION
from app.prompts.portfolio_report_diagrams import PORTFOLIO_REPORT_DIAGRAMS_PROMPT
from app.prompts.portfolio_report_diagrams import PROMPT_VERSION as DIAGRAMS_PROMPT_VERSION
from app.prompts.portfolio_report_profile import PORTFOLIO_REPORT_PROFILE_PROMPT
from app.prompts.portfolio_report_profile import PROMPT_VERSION as PROFILE_PROMPT_VERSION
from app.prompts.portfolio_report_questions import PORTFOLIO_REPORT_QUESTIONS_PROMPT
from app.prompts.portfolio_report_questions import PROMPT_VERSION as QUESTIONS_PROMPT_VERSION
from app.prompts.rendering import render_prompt
from app.services import portfolio_report_rubric as rubric
from app.services.llm_service import chat_json, get_llm_provenance, set_llm_trace_context
from app.services.portfolio_report_schema import (
    MIN_PROJECTS,
    QUESTIONS_DEFERRED,
    QUESTIONS_DEFERRED_NOTE,
    PortfolioReport,
    build_portfolio_excerpts,
    project_label,
    raw_entries_text,
    universe_text,
)
from app.services.report_html_lint import (
    FOLLOWUP_ATOMS,
    FORBIDDEN_MECHANISM_WORDS,
    ellipsis_hits,
    is_anchored_note,
)
from app.services.resume_report_service import invented_numbers, jd_text_for
from app.utils.service_access import get_owned_resume
from app.utils.time_helper import utc_now

logger = logging.getLogger(__name__)

TARGET_QUESTION_COUNT = rubric.TARGET_QUESTION_COUNT
MIN_ANSWER_CHARS = 120
FOLLOWUP_COUNT = 2
MIN_COMPARE_ROWS = 4
MIN_CAPABILITY_ROWS = 4
MIN_STAGE_POINTS = 3
MIN_RISK_ROWS = 3

_CODE_RED_LINES, _MODEL_RED_LINES = rubric.judged_red_line_keys()
_DIFFICULTY_NAMES = {row[0]: row[1] for row in rubric.DIFFICULTY_BANDS}
_TODO = re.compile(r"【待补[^】]*】")

# 横向对比里一格没过复核时上屏的那一句。**不是**"这一格空着"——一张缺格的对比表
# 会让人以为另一个项目没写这一项，而事实是模型在这一格里冒出了一个原文没有的数。
CELL_DROPPED_NOTE = "（这一格的说法里有一个不在项目原文里的数字，已撤下）"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _blocked(text: str) -> list[str]:
    return [word for word in FORBIDDEN_MECHANISM_WORDS if word in text] + ellipsis_hits(text)


def _fold(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _known(universe: str) -> str:
    return json.dumps({"entry": universe}, ensure_ascii=False)


# ------------------------------------------------------------------ 选中项目取数
def selected_indices(entries: list[dict[str, Any]], indices: list[int]) -> list[int]:
    """去重、排序、边界核一遍。少两个项目不是"组合"，多一个不存在的序号是请求不成立。"""
    clean = sorted({int(i) for i in indices})
    if len(clean) < MIN_PROJECTS:
        raise ValueError(f"组合分析至少要 {MIN_PROJECTS} 个项目（这次只给了 {len(clean)} 个）")
    for index in clean:
        if index < 0 or index >= len(entries):
            raise ValueError(f"没有第 {index + 1} 个项目（这份简历里共 {len(entries)} 个）")
    return clean


def peer_project_totals(db: Session, resume_id: int, indices: list[int], user_id: int | None) -> list[dict[str, Any]]:
    """表头「单项目均分」与 1.2 那一列的事实来源：**跑过就复用，没跑就明写没跑**。

    每个项目取"最新那一发完成的前三节"，不是最新那一发作业行——失败的行没有分数。
    """
    rows: list[dict[str, Any]] = []
    for index in sorted({int(i) for i in indices}):
        query = db.query(ProjectReportJob).filter(
            ProjectReportJob.resume_id == resume_id,
            ProjectReportJob.project_index == index,
            ProjectReportJob.stage == PROJECT_STAGE_REPORT,
            ProjectReportJob.status == "completed",
        )
        if user_id is not None:
            query = query.filter(ProjectReportJob.user_id == user_id)
        job = query.order_by(ProjectReportJob.id.desc()).first()
        if job is None:
            rows.append({"project_index": index, "total": None, "grade": None, "difficulty": None, "job_id": None})
            continue
        rows.append(
            {
                "project_index": index,
                "total": None if job.excluded else job.total_score,
                "grade": None if job.excluded else job.grade,
                "difficulty": job.difficulty,
                "job_id": job.id,
                "excluded": bool(job.excluded),
            }
        )
    return rows


def _jd_and_position(jd: JobDescription | None, target_position: str) -> tuple[str, str]:
    if jd is None:
        return (
            "未指定目标岗位，按这几个项目自己写到的技术栈判断方向。",
            target_position or "未指定（按项目原文识别方向）",
        )
    return jd_text_for(jd), target_position or jd.title or ""


def _projects_block(excerpts: list[dict[str, Any]]) -> str:
    """把选中项目的逐字原文摊成 prompt 里那一段（服务端切的，一个字不过模型）。"""
    parts: list[str] = []
    for excerpt in excerpts:
        index = int(excerpt.get("project_index") or 0)
        head = [
            f"【{project_label(excerpt)}】（project_index={index}，简历里第 {index + 1} 个）",
            f"担任角色：{_text(excerpt.get('role')) or '（原文没有写角色）'}",
            f"起止时间：{_text(excerpt.get('period')) or '（原文没有写起止时间）'}",
            f"技术栈（原文）：{'、'.join(excerpt.get('tech') or []) or '（原文没有单独列技术栈）'}",
        ]
        for section in excerpt.get("sections") or []:
            head.append(f"〔{section.get('label')}〕")
            head.extend(f"- {line}" for line in section.get("lines") or [])
        parts.append("\n".join(head))
    return "\n\n".join(parts)


def _facts_block(report: PortfolioReport, stack: dict[str, Any]) -> str:
    lines = [
        f"项目数：{report.project_count}（这一组占简历第 {rubric.span_of(report.project_indices)[0]}"
        f"~{rubric.span_of(report.project_indices)[1]} 位）",
        "各项目已跑过的单项目分析（没跑过的就写没跑过，不要替它猜一个分）：",
    ]
    by_index = {int(row["project_index"]): row for row in report.peer_scores}
    for excerpt in report.projects:
        index = int(excerpt.get("project_index") or 0)
        row = by_index.get(index) or {}
        if row.get("excluded"):
            detail = "跑过，但命中一票否决，那一份没有总分"
        elif row.get("total") is not None:
            detail = f"跑过：{row['total']} 分 / {row.get('grade') or '未落档'} / {row.get('difficulty') or '难度未定'}"
        else:
            detail = "还没跑过单项目分析"
        lines.append(f"- {project_label(excerpt)}：{detail}")
    if stack.get("shared"):
        lines.append("服务端从技术栈清单求交集得到的共用组件（前 12 个）：" + "、".join(stack["shared"][:12]))
    gaps = report.duplicate_evidence
    if gaps:
        lines.append("服务端逐字比对的雷同证据：" + json.dumps(gaps, ensure_ascii=False)[:400])
    return "\n".join(lines)


def _stack_block(report: PortfolioReport) -> str:
    stack = report.stack_reuse or {}
    lines = ["【共用栈（出现在两个以上项目的技术栈清单里）】"]
    lines.append("、".join(stack.get("shared") or []) or "（没有交集：这几个项目的技术栈一个都不重合）")
    lines.append("【差异栈（只在某一个项目里出现）】")
    by_index = {int(row.get("project_index") or 0): row for row in report.projects}
    for key, items in (stack.get("unique_by_index") or {}).items():
        excerpt = by_index.get(int(key)) or {}
        lines.append(f"- {project_label(excerpt)}：{'、'.join(items) if items else '（这一项没有独有组件）'}")
    return "\n".join(lines)


# ------------------------------------------------------------------ 一、组合档案
def validate_profile(
    payload: Any, indices: list[int], universe: str, stack: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rejected: list[dict[str, Any]] = []
    raw = _dict(payload)

    dimensions = rubric.read_dimensions(raw.get("dimensions"), indices)
    scored = [row for row in dimensions if not row["positional"] and row["score"] is not None]
    unanchored = [row["key"] for row in scored if not is_anchored_note(row["note"])]

    summary = _dict(raw.get("summary"))
    summary_out = {key: _text(summary.get(key)) for key in ("projects_line", "common_skeleton", "difference_line")}

    folded = _fold(universe)
    seen: set[str] = set()
    excluded_by: list[dict[str, Any]] = []
    for item in _list(raw.get("red_lines")):
        row = _dict(item)
        key, quote = _text(row.get("key")), _text(row.get("quote"))
        if key not in _MODEL_RED_LINES:
            rejected.append({"reason": "not_model_judged", "detail": key})
            continue
        if not quote:
            rejected.append({"reason": "empty_quote", "detail": key})
            continue
        if _fold(quote) not in folded:
            rejected.append({"reason": "quote_not_verbatim", "detail": key})
            continue
        if key in seen:
            rejected.append({"reason": "duplicate_red_line", "detail": key})
            continue
        seen.add(key)
        excluded_by.append(
            {"key": key, "label": rubric.red_line_label(key), "quote": quote, "why": _text(row.get("why"))}
        )

    difficulty = _dict(raw.get("difficulty"))
    level = _text(difficulty.get("level"))
    if not rubric.is_known_difficulty(level):
        rejected.append({"reason": "bad_difficulty_level", "detail": level})
        level = ""
    difficulty_out = {
        "level": level,
        "name": _DIFFICULTY_NAMES.get(level, ""),
        "reason": _text(difficulty.get("reason")),
    }

    # 1.2 横向对比：七行固定，一格一个数字问题只撤那一格。
    wanted = {int(i) for i in indices}
    compare_rows: dict[str, dict[str, Any]] = {}
    for item in _list(raw.get("compare")):
        row = _dict(item)
        key = _text(row.get("row"))
        if key not in rubric.COMPARE_ROW_LABELS:
            rejected.append({"reason": "compare_row_off_list", "detail": key[:40]})
            continue
        if key in compare_rows:
            rejected.append({"reason": "compare_row_duplicate", "detail": key})
            continue
        cells: dict[str, str] = {}
        for entry in _list(row.get("cells")):
            cell = _dict(entry)
            try:
                index = int(cell.get("project_index"))
            except (TypeError, ValueError):
                rejected.append({"reason": "compare_index_unreadable", "detail": key})
                continue
            if index not in wanted or str(index) in cells:
                rejected.append({"reason": "compare_index_out_of_list", "detail": f"{key}:{index}"})
                continue
            text = _text(cell.get("text"))
            if not text:
                rejected.append({"reason": "compare_cell_empty", "detail": f"{key}:{index}"})
                continue
            if _blocked(text):
                rejected.append({"reason": "compare_cell_forbidden_word", "detail": f"{key}:{index}"})
                cells[str(index)] = CELL_DROPPED_NOTE
                continue
            bad = invented_numbers(text, _known(universe))
            if bad:
                rejected.append(
                    {"reason": "compare_cell_invented_number", "detail": f"{key}:{index}", "numbers": bad[:3]}
                )
                cells[str(index)] = CELL_DROPPED_NOTE
                continue
            cells[str(index)] = text
        missing_columns = sorted(str(i) for i in wanted - {int(k) for k in cells})
        if missing_columns:
            for index in missing_columns:
                cells[index] = "（这一格没有写到，模型没有覆盖到这个项目）"
            rejected.append({"reason": "compare_cells_incomplete", "detail": f"{key}:{missing_columns}"})
        compare_rows[key] = {"key": key, "label": rubric.COMPARE_ROW_LABELS[key], "cells": cells}

    compare: list[dict[str, Any]] = []
    for key in rubric.COMPARE_ROW_KEYS:
        row = compare_rows.get(key)
        if row is None:
            rejected.append({"reason": "compare_row_absent", "detail": key})
            continue
        if all(value == CELL_DROPPED_NOTE for value in row["cells"].values()):
            rejected.append({"reason": "compare_row_all_dropped", "detail": key})
            continue
        compare.append(row)

    capabilities, capability_rejected = rubric.clean_capability_rows(raw.get("capabilities"), list(wanted))
    rejected.extend(capability_rejected)

    claim = rubric.model_claimed_shared([_text(x) for x in _list(raw.get("shared_stack"))], stack.get("shared") or [])
    rejected.extend({"reason": "shared_stack_dropped", "detail": item} for item in claim["dropped"])

    risks: list[dict[str, Any]] = []
    for item in _list(raw.get("risks")):
        row = _dict(item)
        point, detail, fix = _text(row.get("point")), _text(row.get("detail")), _text(row.get("fix"))
        if not (point and detail and fix):
            rejected.append({"reason": "incomplete_risk", "detail": point[:40]})
            continue
        if _blocked(f"{point}{detail}{fix}"):
            rejected.append({"reason": "forbidden_word", "detail": point[:40]})
            continue
        bad = invented_numbers(f"{point}{detail}{fix}", _known(universe))
        if bad:
            rejected.append({"reason": "risk_invented_number", "detail": point[:40], "numbers": bad[:3]})
            continue
        risks.append({"point": point, "detail": detail, "fix": fix})
    risks = risks[:6]

    if scored and len(unanchored) == len(scored):
        rejected.append({"reason": "all_notes_unanchored", "detail": [row["key"] for row in scored]})

    return (
        {
            "summary": summary_out,
            "dimensions": dimensions,
            "excluded_by": excluded_by,
            "difficulty": difficulty_out,
            "compare": compare,
            "capabilities": capabilities,
            "shared_stack_kept": claim["kept"],
            "shared_stack_dropped": claim["dropped"],
            "risks": risks,
            "anchor_stats": {"scored": len(scored), "unanchored_keys": unanchored},
        },
        rejected,
    )


def build_profile(
    resume: Resume,
    report: PortfolioReport,
    jd: JobDescription | None,
    target_position: str,
    quote_universe: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """一、组合档案那一发。`quote_universe` 是选中项目的全部可引用原文（含技术栈/角色/项目名），
    红线证据与逐字命中都拿它当全集——只用正文那几行会把"技术栈那一条"这种合法寻址判成编造。
    """
    jd_text, position = _jd_and_position(jd, target_position)
    prompt = render_prompt(
        PORTFOLIO_REPORT_PROFILE_PROMPT,
        jd_text=jd_text,
        projects_block=_projects_block(report.projects),
        server_facts_block=_facts_block(report, report.stack_reuse),
        rubric_block=rubric.rubric_prompt_block(),
        red_line_block=rubric.red_line_prompt_block(),
        difficulty_block=rubric.difficulty_prompt_block(),
        compare_row_keys="、".join(rubric.COMPARE_ROW_KEYS),
        capability_keys="、".join(rubric.CAPABILITY_KEYS),
    )
    set_llm_trace_context(
        {
            "source": f"portfolio_report_service.build_profile[{report.combo_key}]",
            "prompt_version": PROFILE_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    payload = chat_json(prompt, disable_thinking=True)
    profile, rejected = validate_profile(payload, report.project_indices, quote_universe, report.stack_reuse)
    profile["provenance"] = get_llm_provenance()
    profile["position"] = position
    return profile, rejected


# ------------------------------------------------------------------ 二、组合图解
def _points(value: Any, universe: str, stage_key: str, rejected: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for item in _list(value):
        text = _text(item if isinstance(item, str) else _dict(item).get("text"))
        if not text:
            rejected.append({"reason": "empty_point", "detail": stage_key})
            continue
        if _blocked(text):
            rejected.append({"reason": "point_forbidden_word", "detail": stage_key})
            continue
        bad = invented_numbers(text, _known(universe))
        if bad:
            rejected.append({"reason": "point_invented_number", "detail": stage_key, "numbers": bad[:3]})
            continue
        out.append(text)
    return out


def validate_diagrams(payload: Any, report: PortfolioReport) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """2.1 不在这里（它就是 1.3 的格子画成图）；这里只出 2.2 / 2.3 的解读 / 2.4。"""
    universe = universe_text(report.projects)
    raw = _dict(payload)
    rejected: list[dict[str, Any]] = []
    wanted = [int(i) for i in report.project_indices]

    narrative = _dict(raw.get("narrative"))
    labels = {int(excerpt.get("project_index") or 0): excerpt for excerpt in report.projects}
    stages: list[dict[str, Any]] = []
    used: set[int] = set()
    for item in _list(narrative.get("stages")):
        row = _dict(item)
        try:
            index = int(row.get("project_index"))
        except (TypeError, ValueError):
            rejected.append({"reason": "stage_index_unreadable"})
            continue
        if index not in wanted:
            rejected.append({"reason": "stage_index_out_of_list", "detail": index})
            continue
        if index in used:
            rejected.append({"reason": "stage_index_duplicate", "detail": index})
            continue
        used.add(index)
        stage_name = _text(row.get("stage_name"))
        points = _points(row.get("points"), universe, str(index), rejected)
        if len(points) < MIN_STAGE_POINTS:
            rejected.append({"reason": "stage_points_thin", "detail": f"{index}:{len(points)}"})
            continue
        stages.append(
            {
                "project_index": index,
                "code": f"PJ-{index + 1:02d}",
                "label": project_label(labels.get(index) or {}),
                "stage_name": stage_name or f"阶段 {len(stages) + 1}",
                "points": points,
                "core_question": _text(row.get("core_question")),
                "keywords": _text(row.get("keywords")),
            }
        )
    missing_stages = [index for index in wanted if index not in {int(row["project_index"]) for row in stages}]
    if missing_stages:
        rejected.append({"reason": "narrative_stages_missing", "detail": missing_stages})

    rounds: list[dict[str, Any]] = []
    seen_rounds: set[str] = set()
    for item in _list(raw.get("rounds")):
        row = _dict(item)
        key = _text(row.get("key"))
        if key not in rubric.INTERVIEW_ROUND_KEYS:
            rejected.append({"reason": "round_off_list", "detail": key})
            continue
        if key in seen_rounds:
            rejected.append({"reason": "round_duplicate", "detail": key})
            continue
        text = _text(row.get("text"))
        if not text or _blocked(text):
            rejected.append({"reason": "round_text_bad", "detail": key})
            continue
        bad = invented_numbers(text, _known(universe))
        if bad:
            rejected.append({"reason": "round_invented_number", "detail": key, "numbers": bad[:3]})
            continue
        seen_rounds.add(key)
        rounds.append(
            {
                "key": key,
                "label": rubric.INTERVIEW_ROUND_LABELS[key],
                "text": text,
                "decisive": key in rubric.DECISIVE_ROUNDS,
            }
        )
    missing_rounds = [key for key in rubric.INTERVIEW_ROUND_KEYS if key not in seen_rounds]
    if missing_rounds:
        rejected.append({"reason": "rounds_incomplete", "detail": missing_rounds})

    def check_text(value: Any, name: str) -> str:
        text = _text(value if isinstance(value, str) else "")
        if not text:
            rejected.append({"reason": "empty_field", "detail": name})
            return ""
        if _blocked(text):
            rejected.append({"reason": "field_forbidden_word", "detail": name})
            return ""
        bad = invented_numbers(text, _known(universe))
        if bad:
            rejected.append({"reason": "field_invented_number", "detail": name, "numbers": bad[:3]})
            return ""
        return text

    out: dict[str, Any] = {}
    if stages and len(missing_stages) == 0:
        out["narrative"] = {
            "title": check_text(narrative.get("title"), "narrative.title"),
            "stages": stages,
            "one_line": check_text(narrative.get("one_line"), "narrative.one_line"),
        }
    else:
        out["narrative"] = None
    if len(rounds) == len(rubric.INTERVIEW_ROUNDS):
        out["rounds"] = rounds
    else:
        out["rounds"] = None

    out["stack"] = report.stack_reuse
    out["reuse_read"] = check_text(raw.get("reuse_read"), "reuse_read")
    out["unique_read"] = check_text(raw.get("unique_read"), "unique_read")
    out["sameness_answer"] = check_text(raw.get("sameness_answer"), "sameness_answer")
    out["strategy"] = check_text(raw.get("strategy"), "strategy")
    out["usage"] = check_text(raw.get("usage"), "usage")

    if out["narrative"] is None and out["rounds"] is None:
        return None, rejected + [{"reason": "diagrams_both_absent"}]
    return out, rejected


# ------------------------------------------------------------------ 三、使用建议
def validate_advice(payload: Any, report: PortfolioReport) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    universe = universe_text(report.projects)
    raw = _dict(payload)
    rejected: list[dict[str, Any]] = []
    wanted = sorted(int(i) for i in report.project_indices)
    labels = {int(excerpt.get("project_index") or 0): excerpt for excerpt in report.projects}

    arrangements: list[dict[str, Any]] = []
    for item in _list(raw.get("arrangements")):
        row = _dict(item)
        order = []
        bad_order = ""
        for value in _list(row.get("project_indices")):
            try:
                order.append(int(value))
            except (TypeError, ValueError):
                bad_order = "unreadable"
                break
        if bad_order or sorted(order) != wanted or len(order) != len(set(order)):
            # 排列那一格由服务端渲染，前提是它真是被选项目的一个全排列。
            rejected.append({"reason": "arrangement_not_a_permutation", "detail": order})
            continue
        scenario, pros, cons = _text(row.get("scenario")), _text(row.get("pros")), _text(row.get("cons"))
        if not (scenario and pros and cons):
            rejected.append({"reason": "incomplete_arrangement", "detail": scenario[:40]})
            continue
        joined = f"{scenario}{pros}{cons}"
        if _blocked(joined):
            rejected.append({"reason": "arrangement_forbidden_word", "detail": scenario[:40]})
            continue
        bad = invented_numbers(joined, _known(universe))
        if bad:
            rejected.append({"reason": "arrangement_invented_number", "detail": scenario[:40], "numbers": bad[:3]})
            continue
        arrangements.append(
            {
                "order": order,
                "rendered": " → ".join(f"PJ-{index + 1:02d}" for index in order),
                "labels": " → ".join(project_label(labels.get(index) or {}) for index in order),
                "scenario": scenario,
                "pros": pros,
                "cons": cons,
            }
        )
    arrangements = arrangements[:6]

    default_choice = -1
    try:
        default_choice = int(_dict(raw).get("default_choice"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        rejected.append({"reason": "default_choice_unreadable"})
    if not (0 <= default_choice < len(arrangements)):
        if default_choice != -1:
            rejected.append({"reason": "default_choice_out_of_range", "detail": default_choice})
        default_choice = 0 if arrangements else -1

    asked: list[dict[str, str]] = []
    for item in _list(raw.get("asked_before")):
        row = _dict(item)
        question, answer = _text(row.get("asked")), _text(row.get("answer"))
        if not (question and answer):
            rejected.append({"reason": "incomplete_asked_before", "detail": question[:40]})
            continue
        if _blocked(f"{question}{answer}") or invented_numbers(f"{question}{answer}", _known(universe)):
            rejected.append({"reason": "asked_before_rejected", "detail": question[:40]})
            continue
        asked.append({"asked": question, "answer": answer})
    asked = asked[:8]

    strengthen: list[dict[str, str]] = []
    for item in _list(raw.get("strengthen")):
        row = _dict(item)
        gap, action, expected = _text(row.get("gap")), _text(row.get("action")), _text(row.get("expected"))
        if not (gap and action and expected):
            rejected.append({"reason": "incomplete_strengthen", "detail": gap[:40]})
            continue
        if not rubric.mentions_dimension(expected):
            rejected.append({"reason": "expected_no_dimension", "detail": expected[:40]})
            continue
        if _blocked(f"{gap}{action}{expected}") or invented_numbers(f"{gap}{action}", _known(universe)):
            rejected.append({"reason": "strengthen_rejected", "detail": gap[:40]})
            continue
        strengthen.append({"gap": gap, "action": action, "expected": expected})
    strengthen = strengthen[:6]

    citation = _dict(raw.get("citation"))
    citation_out = {key: _text(citation.get(key)) for key in ("borrow", "adapt", "breaks")}
    for key, value in list(citation_out.items()):
        if not value or _blocked(value) or invented_numbers(value, _known(universe)):
            rejected.append({"reason": "citation_field_rejected", "detail": key})
            citation_out.pop(key, None)

    if len(arrangements) < 2:
        return None, rejected + [{"reason": "arrangements_thin"}]
    if len(asked) < 3 or not strengthen or len(citation_out) < 3:
        return None, rejected + [{"reason": "advice_table_incomplete"}]

    return (
        {
            "arrangements": arrangements,
            "default_index": default_choice,
            "default_reason": _text(raw.get("default_reason")),
            "asked_before": asked,
            "strengthen": strengthen,
            "citation": citation_out,
        },
        rejected,
    )


def collect_todos(report: PortfolioReport) -> list[str]:
    """档案与图解里留下的 `【待补】` 原样摊出来给第三节，让它知道哪儿还欠实测值。"""
    out: list[str] = []
    blobs = [json.dumps(report.compare, ensure_ascii=False), json.dumps(report.risks, ensure_ascii=False)]
    if report.difficulty:
        blobs.append(json.dumps(report.difficulty, ensure_ascii=False))
    for blob in blobs:
        out.extend(match.group(0) for match in _TODO.finditer(blob))
    return list(dict.fromkeys(out))[:12]


def _score_block(report: PortfolioReport) -> str:
    lines = [f"组合评分：{report.score_cell()}（六维满分 100，服务端相加）"]
    if report.grade and not report.is_excluded():
        lines.append(f"评级：{report.grade} {report.grade_desc}")
    for row in report.dimensions:
        score = "未读出" if row["score"] is None else str(row["score"])
        lines.append(f"- {row['label']}：{score} / {row['full']}　{row['note']}")
    difficulty = report.difficulty or {}
    if difficulty.get("level"):
        lines.append(f"组合难度：{difficulty['level']} {difficulty.get('name', '')}　{difficulty.get('reason', '')}")
    return "\n".join(lines)


def _risk_block(risks: list[dict[str, Any]]) -> str:
    if not risks:
        return "（档案这一节没有留下组合层风险提示）"
    return "\n".join(
        f"{index + 1}. {row['point']}｜{row['detail']}｜补齐：{row['fix']}" for index, row in enumerate(risks)
    )


def _compare_block(report: PortfolioReport) -> str:
    rows = (report.compare or {}).get("rows") or []
    if not rows:
        return "（横向对比没有通过复核）"
    lines: list[str] = []
    for row in rows:
        lines.append(f"〔{row['label']}〕")
        for index in sorted(row["cells"], key=int):
            lines.append(f"- PJ-{int(index) + 1:02d}：{row['cells'][index]}")
    return "\n".join(lines)


# ------------------------------------------------------------------ 编排
def build_diagrams(resume: Resume, report: PortfolioReport) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    set_llm_trace_context(
        {
            "source": f"portfolio_report_service.build_diagrams[{report.combo_key}]",
            "prompt_version": DIAGRAMS_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    prompt = render_prompt(
        PORTFOLIO_REPORT_DIAGRAMS_PROMPT,
        projects_block=_projects_block(report.projects),
        score_block=_score_block(report),
        risk_block=_risk_block(report.risks),
        stack_block=_stack_block(report),
        round_keys="、".join(rubric.INTERVIEW_ROUND_KEYS),
    )
    payload = chat_json(prompt, disable_thinking=True)
    report.provenance["diagrams"] = get_llm_provenance()
    return validate_diagrams(payload, report)


def build_advice(resume: Resume, report: PortfolioReport) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    pending = collect_todos(report)
    set_llm_trace_context(
        {
            "source": f"portfolio_report_service.build_advice[{report.combo_key}]",
            "prompt_version": ADVICE_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    prompt = render_prompt(
        PORTFOLIO_REPORT_ADVICE_PROMPT,
        projects_block=_projects_block(report.projects),
        score_block=_score_block(report),
        risk_block=_risk_block(report.risks),
        pending_block="、".join(pending) if pending else "（档案里没有留下【待补】的数）",
        index_list="、".join(str(index) for index in report.project_indices),
    )
    payload = chat_json(prompt, disable_thinking=True)
    report.provenance["advice"] = get_llm_provenance()
    return validate_advice(payload, report)


def validate_questions(
    payload: Any, universe: str, risk_total: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    raw = _dict(payload)
    known = _known(universe)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for item in _list(raw.get("questions")):
        row = _dict(item)
        question, kind = _text(row.get("question")), _text(row.get("kind"))
        answer, status = _text(row.get("answer")), _text(row.get("status"))
        stamp = {"question": question[:40]}
        if not question:
            rejected.append({"reason": "empty_question"})
            continue
        if kind not in rubric.QUESTION_KINDS:
            rejected.append(stamp | {"reason": "bad_kind", "detail": kind})
            continue
        if len(answer) < MIN_ANSWER_CHARS:
            rejected.append(stamp | {"reason": "answer_too_short", "detail": len(answer)})
            continue
        bad = invented_numbers(answer, known)
        if bad:
            rejected.append(stamp | {"reason": "invented_number", "detail": bad[:5]})
            continue
        if _blocked(f"{question}{answer}"):
            rejected.append(stamp | {"reason": "forbidden_word", "detail": question[:40]})
            continue
        if status not in rubric.QUESTION_STATUSES:
            rejected.append(stamp | {"reason": "bad_status", "detail": status})
            continue
        missing = [_text(x) for x in _list(row.get("missing")) if _text(x)]
        if status != "可答" and not missing:
            rejected.append(stamp | {"reason": "missing_not_named"})
            continue

        followups: list[dict[str, str]] = []
        bad_followup = ""
        for follow in _list(row.get("followups")):
            frow = _dict(follow)
            label, body = _text(frow.get("kind")), _text(frow.get("text"))
            atoms = [part.strip() for part in label.replace("……", "").replace("。", "").split("/") if part.strip()]
            if not body:
                bad_followup = "empty_followup"
                break
            if not atoms or any(atom not in FOLLOWUP_ATOMS for atom in atoms):
                bad_followup = "bad_followup_kind"
                break
            followups.append({"kind": label, "text": body})
        if bad_followup:
            rejected.append(stamp | {"reason": bad_followup})
            continue
        if len(followups) != FOLLOWUP_COUNT:
            rejected.append(stamp | {"reason": "followup_count", "detail": len(followups)})
            continue

        try:
            risk_ref = int(row.get("risk_ref"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            risk_ref = 0
        if status == "高危":
            if not (1 <= risk_ref <= risk_total):
                rejected.append(stamp | {"reason": "risk_ref_out_of_range", "detail": risk_ref})
                status, risk_ref = "需补强", 0
        else:
            risk_ref = 0

        accepted.append(
            {
                "no": len(accepted) + 1,
                "question": question,
                "kind": kind,
                "answer": answer,
                "followups": followups,
                "status": status,
                "missing": missing if status != "可答" else [],
                "risk_ref": risk_ref,
            }
        )
    return accepted, questions_distribution(accepted), rejected


def questions_distribution(items: list[dict[str, Any]]) -> dict[str, Any]:
    """题数与各态数量在这里数出来；模型自报的那一个历来和实际题数对不上。"""
    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
    return {
        "total": len(items),
        "target": TARGET_QUESTION_COUNT,
        "by_kind": by_kind,
        "answerable": sum(1 for item in items if item["status"] == "可答"),
        "weak": sum(1 for item in items if item["status"] == "需补强"),
        "high_risk": sum(1 for item in items if item["status"] == "高危"),
    }


def practice_backfill(items: list[dict[str, Any]]) -> dict[str, str]:
    if not items:
        return {"must_practice": "", "high_risk": ""}
    need = [f"Q{item['no']}" for item in items if item["status"] != "可答"]
    high = [f"Q{item['no']}" for item in items if item["status"] == "高危"]
    return {
        "must_practice": "、".join(need[:6]) if need else "（这一轮的题都答得上，按顺序过一遍就行）",
        "high_risk": "、".join(high) if high else "无（没有一问就穿的题）",
    }


def build_questions(resume: Resume, report: PortfolioReport) -> dict[str, Any]:
    universe = universe_text(report.projects)
    if report.is_excluded():
        return {QUESTIONS_DEFERRED: True, "note": QUESTIONS_DEFERRED_NOTE, "questions": [], "distribution": None}
    set_llm_trace_context(
        {
            "source": f"portfolio_report_service.build_questions[{report.combo_key}]",
            "prompt_version": QUESTIONS_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    prompt = render_prompt(
        PORTFOLIO_REPORT_QUESTIONS_PROMPT,
        projects_block=_projects_block(report.projects),
        score_block=_score_block(report),
        risk_block=_risk_block(report.risks),
        risk_total=len(report.risks),
        compare_block=_compare_block(report),
        target_position=report.target_position or "未指定（按项目原文识别方向）",
        kind_block="\n".join(f"- {kind}" for kind in rubric.QUESTION_KINDS),
        followup_atoms="、".join(sorted(FOLLOWUP_ATOMS)),
    )
    payload = chat_json(prompt, disable_thinking=True)
    items, distribution, rejected = validate_questions(payload, universe, len(report.risks))
    report.provenance["questions"] = get_llm_provenance()
    report.questions_rejected = rejected
    if not items:
        return {QUESTIONS_DEFERRED: True, "note": "", "questions": [], "distribution": None, "failed": True}
    return {
        QUESTIONS_DEFERRED: False,
        "note": "",
        "questions": items,
        "distribution": distribution,
        "practice": practice_backfill(items),
    }


def generate_portfolio_report(
    db: Session,
    resume_id: int,
    project_indices: list[int],
    jd_id: int | None = None,
    target_position: str = "",
    user_id: int | None = None,
) -> PortfolioReport:
    """跑完前三节。第四节留给 `generate_portfolio_questions`。"""
    resume = get_owned_resume(db, resume_id, user_id) if user_id is not None else db.get(Resume, resume_id)
    if resume is None:
        raise ValueError("简历不存在或无权限")

    from app.services.project_report_service import project_entries

    entries = project_entries(resume.parsed_json)
    if not entries:
        raise ValueError("这份简历里没有项目经历，做不了组合分析")
    indices = selected_indices(entries, project_indices)

    jd: JobDescription | None = None
    if jd_id is not None:
        jd = db.get(JobDescription, jd_id)
        if jd is None:
            raise ValueError("目标岗位不存在")

    report = PortfolioReport(
        resume_id=resume_id,
        project_indices=indices,
        user_id=user_id,
        jd_id=jd_id,
        target_position=target_position,
        report_date=utc_now().strftime("%Y-%m-%d"),
        projects=build_portfolio_excerpts(entries, indices),
        peer_scores=peer_project_totals(db, resume_id, indices, user_id),
    )
    quote_universe = raw_entries_text(entries, indices)
    tech_by_index = {
        int(row.get("project_index") or 0): [str(t) for t in (row.get("tech") or [])] for row in report.projects
    }
    report.stack_reuse = rubric.stack_reuse(tech_by_index)
    text_by_index = {
        int(row.get("project_index") or 0): "\n".join(
            line for section in row.get("sections") or [] for line in section.get("lines") or []
        )
        for row in report.projects
    }
    report.duplicate_evidence = rubric.duplicate_pairs(text_by_index) + rubric.near_copy_pairs(text_by_index)
    report.per_project_metric_gaps = rubric.metric_gaps_by_project(text_by_index)

    # 红线 1：代码自算的那一条。完全相同 = 出局；近似雷同只进证据。
    code_hits: list[dict[str, Any]] = []
    for pair in report.duplicate_evidence:
        if pair.get("kind") != "identical":
            continue
        code_hits.append(
            {
                "key": "duplicate_projects",
                "label": rubric.red_line_label("duplicate_projects"),
                "quote": f"PJ-{int(pair['pair'][0]) + 1:02d} 与 PJ-{int(pair['pair'][1]) + 1:02d} 的正文逐字相同",
                "why": rubric.red_line_prompt_for("duplicate_projects"),
            }
        )

    # 阶段一：一、组合档案。这一发挂了后面没有意义（六维、红线、对比表是余下各节的输入）。
    profile, rejected = build_profile(resume, report, jd, target_position, quote_universe)
    report.summary = profile["summary"]
    report.dimensions = profile["dimensions"]
    report.excluded_by = code_hits + profile["excluded_by"]
    report.difficulty = profile["difficulty"]
    report.compare = {"rows": profile["compare"]}
    report.capabilities = profile["capabilities"]
    report.risks = profile["risks"]
    report.shared_stack_dropped = profile["shared_stack_dropped"]
    report.red_line_rejected = rejected
    report.provenance["profile"] = profile.get("provenance")
    report.target_position = profile.get("position") or target_position

    scored = [row for row in report.dimensions if not row["positional"] and row["score"] is not None]
    report.total_score = rubric.total_of(report.dimensions)
    report.grade = None if report.is_excluded() else rubric.grade_of(report.total_score)
    report.grade_desc = "" if report.is_excluded() else rubric.grade_desc_of(report.total_score)
    report.grade_scale = rubric.grade_scale_block()
    if len(scored) < len(rubric.DIMENSIONS) - 1:
        report.stage_errors["profile_partial"] = f"{len(rubric.DIMENSIONS) - 1 - len(scored)} 个维度没有读出分数"
    if scored and all(row["score"] is None or not is_anchored_note(row["note"]) for row in scored):
        report.stage_errors["profile_notes_unanchored"] = "五维的扣分点都没有点名项目原文里的位置"
    if len(report.risks) < MIN_RISK_ROWS:
        report.stage_errors["risks_thin"] = f"组合层风险提示只有 {len(report.risks)} 条"
    if len(profile["compare"]) < MIN_COMPARE_ROWS:
        report.stage_errors["compare_thin"] = (
            f"横向对比只留下 {len(profile['compare'])} 行（应有 {len(rubric.COMPARE_ROWS)} 行）"
        )
    if len(report.capabilities) < MIN_CAPABILITY_ROWS:
        report.stage_errors["capabilities_thin"] = f"能力覆盖只留下 {len(report.capabilities)} 行"

    # 阶段二：二、组合图解。挂了只缺这一节。
    try:
        diagrams, diagram_rejected = build_diagrams(resume, report)
        report.diagram_rejected = diagram_rejected
        report.diagrams = diagrams
        if diagrams is None:
            report.stage_errors["diagrams"] = "叙事主线与面试时序都没有通过复核"
    except Exception as exc:  # noqa: BLE001 - 一节挂了不影响其余各节
        logger.exception("组合图解阶段失败 resume=%s combo=%s", resume_id, report.combo_key)
        report.stage_errors["diagrams"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    # 阶段三：三、使用建议。
    try:
        advice, advice_rejected = build_advice(resume, report)
        report.advice_rejected = advice_rejected
        report.advice = advice
        if advice is None:
            report.stage_errors["advice"] = "使用建议的四张表没有通过复核"
    except Exception as exc:  # noqa: BLE001
        logger.exception("组合使用建议阶段失败 resume=%s", resume_id)
        report.stage_errors["advice"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    report.summary.setdefault("source_line", "用户提交")
    return report


def generate_portfolio_questions(db: Session, report: PortfolioReport, user_id: int | None = None) -> PortfolioReport:
    """第四节那一发：读路径上按按钮才跑，命中红线那份整块不出。"""
    resume = (
        get_owned_resume(db, report.resume_id, user_id) if user_id is not None else db.get(Resume, report.resume_id)
    )
    if resume is None:
        raise ValueError("简历不存在或无权限")
    report.questions = build_questions(resume, report)
    if (report.questions or {}).get("failed"):
        report.stage_errors["questions"] = "跨项目题目没有通过复核"
    return report


__all__ = [
    "CELL_DROPPED_NOTE",
    "FOLLOWUP_COUNT",
    "MIN_ANSWER_CHARS",
    "TARGET_QUESTION_COUNT",
    "build_advice",
    "build_diagrams",
    "build_profile",
    "build_questions",
    "collect_todos",
    "generate_portfolio_questions",
    "generate_portfolio_report",
    "peer_project_totals",
    "practice_backfill",
    "questions_distribution",
    "selected_indices",
    "validate_advice",
    "validate_diagrams",
    "validate_profile",
    "validate_questions",
]
