"""单项目分析的编排：前三节一次跑完，第四节（20 题）按按钮再跑一次。

形状抄简历评估报告那一族（作业行 + 租约 + 读路径自愈 + 阶段失败对候选人静默），
不抄它的模块划分：这一份的量程是**一个项目**，六维尺与整份简历那把七维尺不是一把尺。

四条这一族特有的界：
* **1.2 那一节一个字都不过模型**——`build_project_excerpt` 从 `parsed_json` 里逐字切出来；
* **红线只能被提名**：模型给的 `quote` 必须逐字落在项目原文里，命不中就整条作废并记对内；
  代码能逐字核的那两条（无基线、技术栈无落点）只出证据与计数，**不单独判出局**——
  判据在成品那份 85 分的项目原文上验过，"≥1 即出局"会把成品自己判出局，那是必然事件不是门；
* **总分、等级、位次、占比、说服力、题数分布全部由服务端算**，模型自报的那一个进不了候选人的屏；
* **图与表里的数字必须来自项目原文**：新数字按"哪一张图/哪一格里冒出来"定位，
  坏的那一张整张缺席（不是整份缺席），好的那几张照上屏。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription, Resume
from app.prompts.project_report_advice import PROJECT_REPORT_ADVICE_PROMPT
from app.prompts.project_report_advice import PROMPT_VERSION as ADVICE_PROMPT_VERSION
from app.prompts.project_report_diagrams import PROJECT_REPORT_DIAGRAMS_PROMPT
from app.prompts.project_report_diagrams import PROMPT_VERSION as DIAGRAMS_PROMPT_VERSION
from app.prompts.project_report_profile import PROJECT_REPORT_PROFILE_PROMPT
from app.prompts.project_report_profile import PROMPT_VERSION as PROFILE_PROMPT_VERSION
from app.prompts.project_report_questions import PROJECT_REPORT_QUESTIONS_PROMPT
from app.prompts.project_report_questions import PROMPT_VERSION as QUESTIONS_PROMPT_VERSION
from app.prompts.rendering import render_prompt
from app.services import project_report_rubric as rubric
from app.services.llm_service import chat_json, get_llm_provenance, set_llm_trace_context
from app.services.project_report_schema import (
    QUESTIONS_DEFERRED,
    QUESTIONS_DEFERRED_NOTE,
    ProjectReport,
    build_project_excerpt,
    excerpt_text,
    raw_entry_text,
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

# 六个题型是按成品那 20 题的实际问法归出来的，不是先验拟的。
QUESTION_KINDS: tuple[str, ...] = ("背景与定位", "链路与选型", "权衡与代价", "数据与评测", "工程与部署", "沉淀与迁移")
QUESTION_STATUSES: tuple[str, ...] = ("可答", "需补强", "高危")
TARGET_QUESTION_COUNT = 20
MIN_ANSWER_CHARS = 120
MIN_HOW_TO_DRAW_CHARS = 60
# 成品里每题被追问两轮：主答案 + 追问 1 + 追问 2 = "能撑三轮"。
FOLLOWUP_COUNT = 2
MIN_NODES, MAX_NODES = 3, 10
MIN_DEEP_DIVE_ROWS = 2
DIAGRAM_KEYS: tuple[str, ...] = ("function_arch", "core_flow", "system_arch", "sequence")

_CODE_RED_LINES, _MODEL_RED_LINES = rubric.judged_red_line_keys()
_TODO = re.compile(r"【待补[^】]*】")
_DIFFICULTY_NAMES = {row[0]: row[1] for row in rubric.DIFFICULTY_BANDS}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _blocked(text: str) -> list[str]:
    return [word for word in FORBIDDEN_MECHANISM_WORDS if word in text] + ellipsis_hits(text)


def _fold(value: str) -> str:
    """空白折叠后再做逐字包含判断：原文里的换行与缩进不是内容的差异。"""
    return re.sub(r"\s+", "", value or "")


def number_violations(value: Any, entry_text: str) -> list[str]:
    """递归扫一个结构里的每一段文字，找出"这份项目原文里一个都没有的数字"。

    逐段扫而不是整坨 JSON 扫，有两个原因：服务端自己分配的编号（节点的 `no`、题号）
    会被整坨扫成一堆新数字；而模型写的 `2.4` 那种小节引用也不该判成编造。
    数字要查的是**人写的句子**，所以按字符串叶子查。
    """
    known = json.dumps({"entry": entry_text}, ensure_ascii=False)
    out: list[str] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, str):
            bad = invented_numbers(node, known)
            if bad:
                out.append(f"{key or 'text'}：{node[:24]} → {bad[:3]}")
        elif isinstance(node, dict):
            for name, child in node.items():
                if name in ("no", "source", "expected"):
                    # `no` 是服务端自己分配的编号；`source` 是"职责第 3 条"那种**寻址**；
                    # `expected` 是"补齐后 D3 良 → 优"那种**对我们自己那张六维表的说法**。
                    # 三处里的数字都不是对简历事实的主张——把它们当成编造，
                    # 等于罚点名点得最准、承诺写得最清楚的那一句。
                    continue
                walk(child, name)
        elif isinstance(node, list):
            for child in node:
                walk(child, key)

    walk(value)
    return out


# ------------------------------------------------------------------ 项目条目取数
def project_entries(parsed: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = parsed or {}
    raw = data.get("project_experience")
    if not isinstance(raw, list):
        raw = data.get("projects")
    return [entry for entry in (raw or []) if isinstance(entry, dict)]


def project_entry_at(parsed: dict[str, Any] | None, project_index: int) -> dict[str, Any]:
    entries = project_entries(parsed)
    if not entries:
        raise ValueError("这份简历里没有项目经历，做不了单项目分析")
    if project_index < 0 or project_index >= len(entries):
        raise ValueError(f"没有第 {project_index + 1} 个项目（这份简历里共 {len(entries)} 个）")
    return entries[project_index]


def peer_projects(parsed: dict[str, Any] | None, project_index: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(project_entries(parsed)):
        if index == project_index:
            continue
        rows.append(
            {
                "project_index": index,
                "name": _text(entry.get("name")) or f"项目经历 {index + 1}",
                "tech": [str(t) for t in (entry.get("tech") or entry.get("tech_stack") or [])][:12],
            }
        )
    return rows


def _jd_and_position(jd: JobDescription | None, target_position: str) -> tuple[str, str]:
    if jd is None:
        return (
            "未指定目标岗位，按这一条项目自己写到的技术栈判断方向。",
            target_position or "未指定（按项目原文识别方向）",
        )
    return jd_text_for(jd), target_position or jd.title or ""


# ------------------------------------------------------------------ 一、项目档案
def validate_profile(
    payload: Any, project_index: int, entry_text: str, peers: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """读六维分、核红线证据、收亮点/钩子/风险；同简历其它项目的五个分也在这里读。"""
    rejected: list[dict[str, Any]] = []
    raw = _dict(payload)

    dimensions = rubric.read_dimensions(raw.get("dimensions"), project_index)
    scored = [row for row in dimensions if not row["positional"] and row["score"] is not None]
    unanchored = [row["key"] for row in scored if not is_anchored_note(row["note"])]

    portrait = _dict(raw.get("portrait"))
    portrait_out = {key: _text(portrait.get(key)) for key in ("domain", "scene", "main_line", "components")}

    # 红线：只收模型该判的那四条，且证据必须逐字落在项目原文里。
    folded = _fold(entry_text)
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

    highlights: list[dict[str, Any]] = []
    for item in _list(raw.get("highlights")):
        row = _dict(item)
        metric, value, basis = _text(row.get("metric")), _text(row.get("value")), _text(row.get("basis"))
        stamp = {"metric": metric[:40]}
        if not (metric and value):
            rejected.append(stamp | {"reason": "empty_highlight"})
            continue
        bad = invented_numbers(f"{value} {basis}", json.dumps({"entry": entry_text}, ensure_ascii=False))
        if bad:
            rejected.append(stamp | {"reason": "invented_number", "detail": bad[:5]})
            continue
        blocked = _blocked(f"{metric}{value}{basis}")
        if blocked:
            rejected.append(stamp | {"reason": "forbidden_word", "detail": blocked[:5]})
            continue
        highlights.append({"metric": metric, "value": value, "basis": basis or "（原文没有写这个数的口径）"})

    hooks: list[str] = []
    for item in _list(raw.get("hooks")):
        text = _text(item)
        if len(text) >= 8 and text not in hooks and not _blocked(text):
            hooks.append(text)

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
        risks.append({"point": point, "detail": detail, "fix": fix})
    risks = risks[:6]

    wanted = {peer["project_index"] for peer in peers}
    seen_peers: set[int] = set()
    peer_totals: list[dict[str, Any]] = []
    for item in _list(raw.get("peer_dimensions")):
        row = _dict(item)
        try:
            index = int(row.get("project_index"))
        except (TypeError, ValueError):
            rejected.append({"reason": "peer_index_unreadable"})
            continue
        if index not in wanted or index in seen_peers:
            rejected.append({"reason": "peer_out_of_list", "detail": index})
            continue
        seen_peers.add(index)
        rows = rubric.read_dimensions(row.get("dimensions"), index)
        peer_totals.append({"project_index": index, "total": rubric.total_of(rows)})

    # 五维的扣分点必须点名项目原文里的位置；整表都没点名的那一份在机检里会被拦。
    if scored and len(unanchored) == len(scored):
        rejected.append({"reason": "all_notes_unanchored", "detail": [row["key"] for row in scored]})

    return (
        {
            "portrait": portrait_out,
            "dimensions": dimensions,
            "excluded_by": excluded_by,
            "difficulty": difficulty_out,
            "highlights": highlights,
            "hooks": hooks,
            "risks": risks,
            "peer_totals": peer_totals,
            "anchor_stats": {"scored": len(scored), "unanchored_keys": unanchored},
        },
        rejected,
    )


def compute_contribution(project_index: int, total: int | None, peer_totals: list[dict[str, Any]]) -> dict[str, Any]:
    """位次、系数、占这份简历多少、整份简历的说服力——全部服务端算。"""
    coefficient = rubric.rank_coefficient(project_index)
    peers = []
    for row in peer_totals:
        try:
            index = int(row.get("project_index"))
        except (TypeError, ValueError):
            continue
        peers.append((row.get("total"), rubric.rank_coefficient(index)))
    all_rows = [(total, coefficient)] + peers
    return {
        "rank": project_index + 1,
        "coefficient": coefficient,
        "share": rubric.share_of(total, coefficient, peers),
        "persuasion": rubric.persuasion_index(all_rows),
        "peers_scored": sum(1 for row in all_rows if row[0] is not None),
        "peers_total": len(all_rows),
    }


def build_profile(
    resume: Resume, entry: dict[str, Any], project_index: int, jd: JobDescription | None, target_position: str
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    excerpt = build_project_excerpt(entry, project_index)
    body = excerpt_text(excerpt)
    jd_text, position = _jd_and_position(jd, target_position)
    peers = peer_projects(resume.parsed_json, project_index)
    prompt = render_prompt(
        PROJECT_REPORT_PROFILE_PROMPT,
        jd_text=jd_text,
        project_name=excerpt.get("name") or f"项目经历 {project_index + 1}",
        project_role=excerpt.get("role") or "（原文没有写角色）",
        project_period=excerpt.get("period") or "（原文没有写起止时间）",
        project_tech="、".join(excerpt.get("tech") or []) or "（原文没有单独列技术栈）",
        project_excerpt=body or "（这一条项目没有正文）",
        peer_projects_json=json.dumps(peers, ensure_ascii=False, indent=2)
        if peers
        else "（这份简历里只有这一个项目，peer_dimensions 给空数组）",
        rubric_block=rubric.rubric_prompt_block(),
        red_line_block=rubric.red_line_prompt_block(),
        difficulty_block=rubric.difficulty_prompt_block(),
    )
    set_llm_trace_context(
        {
            "source": f"project_report_service.build_profile[{project_index}]",
            "prompt_version": PROFILE_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    payload = chat_json(prompt, disable_thinking=True)
    profile, rejected = validate_profile(payload, project_index, raw_entry_text(entry), peers)
    profile["provenance"] = get_llm_provenance()
    profile["position"] = position
    return profile, rejected, body


# ------------------------------------------------------------------ 二、项目图解
def _deep_dive_rows(rows: Any, entry_text: str, where: str) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    accepted: list[dict[str, str]] = []
    rejected: list[dict[str, Any]] = []
    for item in _list(rows):
        row = _dict(item)
        where_text, point, source = _text(row.get("where")), _text(row.get("point")), _text(row.get("source"))
        if not (where_text and point):
            rejected.append({"diagram": where, "reason": "incomplete_deep_dive"})
            continue
        if not is_anchored_note(source):
            # 来源那一列就是这张表的理由：不点原文位置的"深挖点"没法人去核对。
            rejected.append({"diagram": where, "reason": "source_not_anchored", "detail": source[:40]})
            continue
        bad = invented_numbers(f"{where_text}{point}", json.dumps({"entry": entry_text}, ensure_ascii=False))
        if bad:
            rejected.append({"diagram": where, "reason": "invented_number", "detail": bad[:5]})
            continue
        accepted.append({"where": where_text, "point": point, "source": source})
    return accepted, rejected


def _cells(value: Any, limit: int = 6) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _list(value)[:limit]:
        row = _dict(item)
        title = _text(row.get("title"))
        lines = [_text(line) for line in _list(row.get("lines")) if _text(line)][:3]
        if title:
            rows.append({"title": title, "lines": lines})
    return rows


def _lines(value: Any, limit: int = 3) -> list[str]:
    return [_text(item) for item in _list(value) if _text(item)][:limit]


def validate_diagrams(payload: Any, entry_text: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    raw = _dict(payload)
    rejected: list[dict[str, Any]] = []

    background = _text(raw.get("background"))
    needs = _dict(raw.get("needs"))
    items = []
    for item in _list(needs.get("items")):
        row = _dict(item)
        title, detail = _text(row.get("title")), _text(row.get("detail"))
        if title and detail:
            items.append({"title": title, "detail": detail})
    needs_out = {
        "items": items[:5],
        "roles": _text(needs.get("roles")),
        "delivery": _text(needs.get("delivery")),
        "constraints": _text(needs.get("constraints")),
    }
    if (
        not background
        or len(items) < 2
        or not (needs_out["roles"] and needs_out["delivery"] and needs_out["constraints"])
    ):
        return None, rejected + [{"reason": "background_or_needs_incomplete", "detail": len(items)}]

    diagrams: dict[str, Any] = {}

    # 2.3 功能架构：至少三层 + 那句"我负责"的边界 + 深挖点表。
    arch = _dict(raw.get("function_arch"))
    layers = []
    for item in _list(arch.get("layers")):
        row = _dict(item)
        name, cells = _text(row.get("name")), _cells(row.get("cells"))
        if name and cells:
            layers.append({"name": name, "mine": bool(row.get("mine")), "cells": cells})
    boundary = _text(arch.get("boundary"))
    deep, drop = _deep_dive_rows(arch.get("deep_dive"), entry_text, "function_arch")
    rejected.extend(drop)
    if len(layers) < 3 or "负责" not in boundary or len(deep) < MIN_DEEP_DIVE_ROWS:
        rejected.append(
            {"diagram": "function_arch", "reason": "layers_boundary_or_deep_dive_incomplete", "detail": len(layers)}
        )
    else:
        diagrams["function_arch"] = {"layers": layers, "boundary": boundary, "deep_dive": deep}

    # 2.4 核心流程：输入 → 节点 → 出口 + 回退 + 共享状态。
    flow = _dict(raw.get("core_flow"))
    nodes = []
    for item in _list(flow.get("nodes")):
        row = _dict(item)
        title, lines = _text(row.get("title")), _lines(row.get("lines"))
        if title and lines:
            nodes.append({"no": len(nodes) + 1, "title": title, "lines": lines})
    input_row, exit_row = _dict(flow.get("input")), _dict(flow.get("exit"))
    fallbacks = _lines(flow.get("fallbacks"), 4)
    state = _text(flow.get("state"))
    deep, drop = _deep_dive_rows(flow.get("deep_dive"), entry_text, "core_flow")
    rejected.extend(drop)
    # 超十个就整张不要，不悄悄截断：截断会画出一张"看起来是原图"却少了环节的流程图。
    if not (MIN_NODES <= len(nodes) <= MAX_NODES) or not fallbacks or not state:
        rejected.append({"diagram": "core_flow", "reason": "nodes_or_fallbacks_incomplete", "detail": len(nodes)})
    elif not _text(input_row.get("title")) or not _text(exit_row.get("title")) or len(deep) < MIN_DEEP_DIVE_ROWS:
        rejected.append({"diagram": "core_flow", "reason": "endpoints_or_deep_dive_incomplete"})
    else:
        diagrams["core_flow"] = {
            "input": {"title": _text(input_row.get("title")), "lines": _lines(input_row.get("lines"))},
            "nodes": nodes,
            "exit": {"title": _text(exit_row.get("title")), "lines": _lines(exit_row.get("lines"))},
            "fallbacks": fallbacks,
            "state": state,
            "deep_dive": deep,
        }

    # 2.5 系统架构：至少三层、每层两个以上组件、至少一条分界原则。
    system = _dict(raw.get("system_arch"))
    sys_layers = []
    for item in _list(system.get("layers")):
        row = _dict(item)
        name = _text(row.get("name"))
        components = []
        for comp in _list(row.get("components")):
            crow = _dict(comp)
            title, line = _text(crow.get("title")), _text(crow.get("line"))
            if title:
                components.append({"title": title, "line": line})
        if name and len(components) >= 2:
            sys_layers.append({"name": name, "components": components[:6], "principle": _text(row.get("principle"))})
    deep, drop = _deep_dive_rows(system.get("deep_dive"), entry_text, "system_arch")
    rejected.extend(drop)
    if len(sys_layers) < 3 or not any(row["principle"] for row in sys_layers) or len(deep) < MIN_DEEP_DIVE_ROWS:
        rejected.append(
            {"diagram": "system_arch", "reason": "layers_principle_or_deep_dive_incomplete", "detail": len(sys_layers)}
        )
    else:
        diagrams["system_arch"] = {"layers": sys_layers, "deep_dive": deep}

    # 2.6 任务时序：泳道 + 消息（from/to 必须是已有泳道）+ 失败分支 + 三类字段。
    seq = _dict(raw.get("sequence"))
    lanes = [_text(x) for x in _list(seq.get("lanes")) if _text(x)][:8]
    messages = []
    for item in _list(seq.get("messages")):
        row = _dict(item)
        sender, receiver, body = _text(row.get("from")), _text(row.get("to")), _text(row.get("text"))
        if not body:
            continue
        if sender not in lanes or receiver not in lanes:
            # 一条发往不存在泳道的消息不是排版小瑕疵，是这张时序图自己前后对不上。
            rejected.append({"diagram": "sequence", "reason": "lane_unknown", "detail": f"{sender}->{receiver}"})
            continue
        messages.append({"from": sender, "to": receiver, "text": body})
    branches = _lines(seq.get("branches"), 4)
    artifacts = {key: _text(_dict(seq.get("artifacts")).get(key)) for key in ("task", "process", "control")}
    deep, drop = _deep_dive_rows(seq.get("deep_dive"), entry_text, "sequence")
    rejected.extend(drop)
    if len(lanes) < 3 or len(messages) < 4 or not branches or len(deep) < MIN_DEEP_DIVE_ROWS:
        rejected.append(
            {"diagram": "sequence", "reason": "lanes_messages_branches_incomplete", "detail": len(messages)}
        )
    else:
        diagrams["sequence"] = {
            "lanes": lanes,
            "messages": messages[:24],
            "branches": branches,
            "artifacts": artifacts,
            "deep_dive": deep,
        }

    for key in list(diagrams):
        bad = number_violations(diagrams[key], entry_text)
        if bad:
            del diagrams[key]
            rejected.append({"diagram": key, "reason": "invented_number_diagram", "detail": bad[:6]})

    prose = {
        "background": background,
        "needs": needs_out,
        "reading_note": _text(raw.get("reading_note")),
    }
    bad = number_violations(prose, entry_text)
    if bad:
        return None, rejected + [{"reason": "invented_number_prose", "detail": bad[:6]}]

    blocked = _blocked(json.dumps({**prose, **diagrams}, ensure_ascii=False))
    if blocked:
        return None, rejected + [{"reason": "forbidden_word_diagram", "detail": blocked[:6]}]

    kept = [key for key in DIAGRAM_KEYS if key in diagrams]
    if not kept:
        return None, rejected

    return {
        **prose,
        "figures": kept,
        **diagrams,
    }, rejected


# ------------------------------------------------------------------ 三、使用建议
def validate_advice(payload: Any, report: ProjectReport) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    raw = _dict(payload)
    entry_text = excerpt_text(report.excerpt)
    rejected: list[dict[str, Any]] = []

    teaching, reuse = _dict(raw.get("teaching")), _dict(raw.get("reuse"))
    practice, citation = _dict(raw.get("practice")), _dict(raw.get("citation"))
    teaching_out = {key: _text(teaching.get(key)) for key in ("suitable", "steps", "entry", "stage")}
    reuse_out = {key: _text(reuse.get(key)) for key in ("structure", "expression", "replace", "counterexample")}
    # 必练题与高危题是第四节的输出；这一发里写了也不取，只记一条对内差异。
    if any(_text(practice.get(key)) for key in ("must_practice", "high_risk")):
        rejected.append({"reason": "practice_keys_belong_to_section_four"})
    practice_out = {key: _text(practice.get(key)) for key in ("method", "rehearsal", "timing")}
    citation_out = {key: _text(citation.get(key)) for key in ("borrow", "adapt", "breaks")}

    strengthen: list[dict[str, Any]] = []
    for item in _list(raw.get("strengthen")):
        row = _dict(item)
        gap, action, expected = _text(row.get("gap")), _text(row.get("action")), _text(row.get("expected"))
        if not (gap and action and expected):
            rejected.append({"reason": "incomplete_strengthen", "detail": gap[:40]})
            continue
        if not rubric.mentions_dimension(expected):
            # "补齐后预计"不点名维度，这一行就只是一句好话。
            rejected.append({"reason": "expected_no_dimension", "detail": expected[:40]})
            continue
        strengthen.append({"gap": gap, "action": action, "expected": expected})
    strengthen = strengthen[:4]

    def drop_rows_with_new_numbers(block: dict[str, str], table: str, extra: str = "") -> dict[str, str]:
        """数字逐行核，**撤的是那一行，不是整节**。

        2026-10-14 拿真简历走了一遍才发现旧写法是"五张表里冒出一个原文没有的数字 ⇒ 整节缺席"：
        一条数字让四张没毛病的表陪葬，候选人看到的是"这一节没内容"。
        """
        kept: dict[str, str] = {}
        for key, value in block.items():
            bad = invented_numbers(f"{value}{extra}", json.dumps({"entry": entry_text}, ensure_ascii=False))
            if bad:
                rejected.append({"reason": "invented_number", "table": table, "field": key, "detail": bad[:3]})
                continue
            kept[key] = value
        return kept

    teaching_out = drop_rows_with_new_numbers(teaching_out, "3.1")
    reuse_out = drop_rows_with_new_numbers(reuse_out, "3.2")
    practice_out = drop_rows_with_new_numbers(practice_out, "3.3")
    citation_out = drop_rows_with_new_numbers(citation_out, "3.5")
    kept_rows: list[dict[str, Any]] = []
    for row in strengthen:
        bad = invented_numbers(f"{row['gap']}{row['action']}", json.dumps({"entry": entry_text}, ensure_ascii=False))
        if bad:
            rejected.append({"reason": "invented_number", "table": "3.4", "detail": bad[:3]})
            continue
        kept_rows.append(row)
    strengthen = kept_rows

    if (
        not teaching_out
        or not reuse_out
        or not practice_out
        or not citation_out
        or not all(teaching_out.values())
        or not all(reuse_out.values())
        or not all(practice_out.values())
        or not all(citation_out.values())
    ):
        return None, rejected + [{"reason": "advice_table_incomplete"}]
    if not strengthen:
        return None, rejected + [{"reason": "no_valid_strengthen_row"}]

    blocked = _blocked(
        json.dumps({"strengthen": strengthen, "citation": citation_out, "reuse": reuse_out}, ensure_ascii=False)
    )
    if blocked:
        return None, rejected + [{"reason": "forbidden_word_advice", "detail": blocked[:6]}]

    profile_level = _text(_dict(report.difficulty).get("level"))
    model_level = _text(teaching.get("level"))
    if model_level and model_level != profile_level:
        rejected.append({"reason": "difficulty_overridden_by_profile", "detail": model_level})
    return (
        {
            "teaching": teaching_out,
            "reuse": reuse_out,
            "practice": practice_out,
            "strengthen": strengthen,
            "citation": citation_out,
            # 难度这一格以档案为唯一来源：两处出现同一个量，只允许有一个出处。
            "level": profile_level,
            "level_reason": _text(_dict(report.difficulty).get("reason")),
            "level_source": "profile",
        },
        rejected,
    )


# ------------------------------------------------------------------ 四、面试准备
def _diagram_row(row: Any) -> dict[str, Any] | None:
    data = _dict(row)
    title = _text(data.get("title"))
    cards = _cells(data.get("cards"))
    how = _text(data.get("how_to_draw"))
    if not title or len(cards) < 3 or len(how) < MIN_HOW_TO_DRAW_CHARS:
        return None
    return {"title": title, "cards": cards, "note": _text(data.get("note")), "how_to_draw": how}


def validate_questions(
    payload: Any, entry_text: str, risk_total: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    raw = _dict(payload)
    known = json.dumps({"entry": entry_text}, ensure_ascii=False)
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
        if kind not in QUESTION_KINDS:
            rejected.append(stamp | {"reason": "bad_kind", "detail": kind})
            continue
        if len(answer) < MIN_ANSWER_CHARS:
            rejected.append(stamp | {"reason": "answer_too_short", "detail": len(answer)})
            continue
        bad = invented_numbers(answer, known)
        if bad:
            rejected.append(stamp | {"reason": "invented_number", "detail": bad[:5]})
            continue
        blocked = _blocked(f"{question}{answer}")
        if blocked:
            rejected.append(stamp | {"reason": "forbidden_word", "detail": blocked[:5]})
            continue
        if status not in QUESTION_STATUSES:
            rejected.append(stamp | {"reason": "bad_status", "detail": status})
            continue
        missing = [_text(x) for x in _list(row.get("missing")) if _text(x)]
        if status != "可答" and not missing:
            # 说"还不行"却不点名缺什么，这一句只是自我否定。
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

        diagram: dict[str, Any] | None = None
        if row.get("diagram") is not None:
            diagram = _diagram_row(row.get("diagram"))
            if diagram is None:
                rejected.append(stamp | {"reason": "diagram_incomplete"})
                continue
            bad = invented_numbers(json.dumps(diagram, ensure_ascii=False), known)
            if bad:
                rejected.append(stamp | {"reason": "invented_number_diagram", "detail": bad[:5]})
                continue

        try:
            risk_ref = int(row.get("risk_ref"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            risk_ref = 0
        if status == "高危":
            if not (1 <= risk_ref <= risk_total):
                # 指不回 1.6 那条风险的"高危"是凭空多出来的一个"一问就穿"，降回需补强。
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
                "diagram": diagram,
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
        "diagrammed": sum(1 for item in items if item["diagram"]),
    }


def practice_backfill(items: list[dict[str, Any]]) -> dict[str, str]:
    """第三节 3.3 空着的那两格，由第四节的题号回填。"""
    if not items:
        return {"must_practice": "", "high_risk": ""}
    need = [f"Q{item['no']}" for item in items if item["status"] != "可答"]
    high = [f"Q{item['no']}" for item in items if item["status"] == "高危"]
    return {
        "must_practice": "、".join(need[:6]) if need else "（这一轮的题都答得上，按顺序过一遍就行）",
        "high_risk": "、".join(high) if high else "无（没有一问就穿的题）",
    }


# ------------------------------------------------------------------ 段落拼装
def _score_block(report: ProjectReport) -> str:
    lines = []
    for row in report.dimensions:
        score = "未知" if row["score"] is None else f"{row['score']}/{row['full']}"
        lines.append(f"- {row['label']}：{score}；{row['note'] or '（这一维没有写出扣分点）'}")
    lines.append(f"合计：{report.score_cell()}（六维满分 {rubric.TOTAL_FULL}）")
    if report.excluded_by:
        lines.append("命中红线：" + "、".join(row["label"] for row in report.excluded_by))
    return "\n".join(lines)


def _risk_block(risks: list[dict[str, Any]]) -> str:
    if not risks:
        return "（这一份没有写出「哪里一问就穿」那一张表）"
    return "\n".join(
        f"{index}. {row['point']}｜{row['detail']}｜补齐：{row['fix']}" for index, row in enumerate(risks, start=1)
    )


def _hook_block(hooks: list[str]) -> str:
    return "\n".join(f"- {text}" for text in hooks) or "（没有给出可深挖的技术决策点）"


def collect_todos(report: ProjectReport) -> list[str]:
    blob = json.dumps(
        {"dimensions": report.dimensions, "highlights": report.highlights, "risks": report.risks}, ensure_ascii=False
    )
    seen: list[str] = []
    for span in _TODO.findall(blob):
        if span not in seen:
            seen.append(span)
    return seen


def _excerpt_inputs(report: ProjectReport, body: str) -> dict[str, Any]:
    return {
        "project_name": report.excerpt.get("name") or f"项目经历 {report.project_index + 1}",
        "project_role": report.excerpt.get("role") or "（原文没有写角色）",
        "project_tech": "、".join(report.excerpt.get("tech") or []) or "（原文没有单独列技术栈）",
        "project_excerpt": body or "（这一条项目没有正文）",
        "difficulty_level": report.difficulty.get("level") or "未定级",
    }


# ------------------------------------------------------------------ 编排
def build_diagrams(
    resume: Resume, report: ProjectReport, body: str
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    set_llm_trace_context(
        {
            "source": f"project_report_service.build_diagrams[{report.project_index}]",
            "prompt_version": DIAGRAMS_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    prompt = render_prompt(
        PROJECT_REPORT_DIAGRAMS_PROMPT,
        **_excerpt_inputs(report, body),
        difficulty_reason=report.difficulty.get("reason") or "（没有给出定级理由）",
        score_block=_score_block(report),
        risk_block=_risk_block(report.risks),
    )
    payload = chat_json(prompt, disable_thinking=True)
    report.provenance["diagrams"] = get_llm_provenance()
    return validate_diagrams(payload, body)


def build_advice(
    resume: Resume, report: ProjectReport, body: str
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    set_llm_trace_context(
        {
            "source": f"project_report_service.build_advice[{report.project_index}]",
            "prompt_version": ADVICE_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    pending = collect_todos(report)
    prompt = render_prompt(
        PROJECT_REPORT_ADVICE_PROMPT,
        **_excerpt_inputs(report, body),
        difficulty_reason=report.difficulty.get("reason") or "（没有给出定级理由）",
        score_block=_score_block(report),
        risk_block=_risk_block(report.risks),
        pending_block="、".join(pending) if pending else "（档案里没有留下【待补】的数）",
    )
    payload = chat_json(prompt, disable_thinking=True)
    report.provenance["advice"] = get_llm_provenance()
    return validate_advice(payload, report)


def build_questions(resume: Resume, report: ProjectReport) -> dict[str, Any]:
    """第四节：命中红线那份整块不出；出了就按服务端复核过的题号编排。"""
    if report.is_excluded():
        return {QUESTIONS_DEFERRED: True, "note": QUESTIONS_DEFERRED_NOTE, "questions": [], "distribution": None}

    body = excerpt_text(report.excerpt)
    set_llm_trace_context(
        {
            "source": f"project_report_service.build_questions[{report.project_index}]",
            "prompt_version": QUESTIONS_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    prompt = render_prompt(
        PROJECT_REPORT_QUESTIONS_PROMPT,
        **_excerpt_inputs(report, body),
        score_block=_score_block(report),
        risk_block=_risk_block(report.risks),
        risk_total=len(report.risks),
        hook_block=_hook_block(report.hooks),
        target_position=report.target_position or "未指定（按项目原文识别方向）",
        kind_block="\n".join(f"- {kind}" for kind in QUESTION_KINDS),
        followup_atoms="、".join(sorted(FOLLOWUP_ATOMS)),
    )
    # 这一发也关思考链：它是这条链上输出最长的一支（20 题 × 口述稿 + 两轮追问 + 配图）。
    payload = chat_json(prompt, disable_thinking=True)
    items, distribution, rejected = validate_questions(payload, body, len(report.risks))
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


def generate_project_report(
    db: Session,
    resume_id: int,
    project_index: int,
    jd_id: int | None = None,
    target_position: str = "",
    user_id: int | None = None,
) -> ProjectReport:
    """跑完前三节。第四节留给 `generate_project_questions`（他点的口径）。"""
    resume = get_owned_resume(db, resume_id, user_id) if user_id is not None else db.get(Resume, resume_id)
    if resume is None:
        raise ValueError("简历不存在或无权限")
    entry = project_entry_at(resume.parsed_json, project_index)

    jd: JobDescription | None = None
    if jd_id is not None:
        jd = db.get(JobDescription, jd_id)
        if jd is None:
            raise ValueError("目标岗位不存在")

    report = ProjectReport(
        resume_id=resume_id,
        project_index=project_index,
        user_id=user_id,
        jd_id=jd_id,
        target_position=target_position,
        report_date=utc_now().strftime("%Y-%m-%d"),
    )
    report.excerpt = build_project_excerpt(entry, project_index)

    # 阶段一：一、项目档案。这一发挂了后面没有意义（六维、红线、难度是余下各节的输入），直接抛。
    profile, rejected, body = build_profile(resume, entry, project_index, jd, target_position)
    report.portrait = profile["portrait"]
    report.dimensions = profile["dimensions"]
    report.excluded_by = profile["excluded_by"]
    report.difficulty = profile["difficulty"]
    report.highlights = profile["highlights"]
    report.hooks = profile["hooks"]
    report.risks = profile["risks"]
    report.peer_totals = profile["peer_totals"]
    report.red_line_rejected = rejected
    report.provenance["profile"] = profile.get("provenance")
    report.target_position = profile.get("position") or target_position

    scored = [row for row in report.dimensions if not row["positional"] and row["score"] is not None]
    unanchored = [row["key"] for row in scored if not is_anchored_note(row["note"])]
    report.total_score = rubric.total_of(report.dimensions)
    report.grade = None if report.is_excluded() else rubric.grade_of(report.total_score)
    report.grade_desc = "" if report.is_excluded() else rubric.grade_desc_of(report.total_score)
    report.grade_scale = rubric.grade_scale_block()
    report.contribution = compute_contribution(project_index, report.total_score, report.peer_totals)
    report.metric_gap_evidence = rubric.metric_gap_clauses(body)
    report.stack_footprint = rubric.stack_footprint([str(t) for t in (report.excerpt.get("tech") or [])], body)
    if len(scored) < len(rubric.DIMENSIONS) - 1:
        report.stage_errors["profile_partial"] = f"{len(rubric.DIMENSIONS) - 1 - len(scored)} 个维度没有读出分数"
    if scored and len(unanchored) == len(scored):
        report.stage_errors["profile_notes_unanchored"] = "五维的扣分点都没有点名项目原文里的位置"

    # 阶段二：二、项目图解。挂了只缺这一节。
    try:
        diagrams, diagram_rejected = build_diagrams(resume, report, body)
        report.diagram_rejected = diagram_rejected
        report.diagrams = diagrams
        if diagrams is None:
            report.stage_errors["diagrams"] = "四张图都没有通过复核"
    except Exception as exc:  # noqa: BLE001 - 一节挂了不影响其余各节
        logger.exception("项目图解阶段失败 resume=%s project=%s", resume_id, project_index)
        report.stage_errors["diagrams"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    # 阶段三：三、使用建议。
    try:
        advice, advice_rejected = build_advice(resume, report, body)
        report.advice_rejected = advice_rejected
        report.advice = advice
        if advice is None:
            report.stage_errors["advice"] = "五张表没有通过复核"
    except Exception as exc:  # noqa: BLE001
        logger.exception("项目使用建议阶段失败 resume=%s project=%s", resume_id, project_index)
        report.stage_errors["advice"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    return report


def generate_project_questions(db: Session, report: ProjectReport, user_id: int | None = None) -> ProjectReport:
    """在已有那份前三节之上补第四节——第二次模型调用，同一条作业链的续跑。"""
    resume = (
        get_owned_resume(db, report.resume_id, user_id) if user_id is not None else db.get(Resume, report.resume_id)
    )
    if resume is None:
        raise ValueError("简历不存在或无权限")
    report.questions = build_questions(resume, report)
    if report.questions.get("failed"):
        report.stage_errors["questions"] = "二十道题全部未通过复核"
    return report


__all__ = [
    "FOLLOWUP_COUNT",
    "MIN_ANSWER_CHARS",
    "QUESTION_KINDS",
    "QUESTION_STATUSES",
    "TARGET_QUESTION_COUNT",
    "build_advice",
    "build_diagrams",
    "build_profile",
    "build_questions",
    "collect_todos",
    "compute_contribution",
    "generate_project_questions",
    "generate_project_report",
    "number_violations",
    "peer_projects",
    "practice_backfill",
    "project_entries",
    "project_entry_at",
    "questions_distribution",
    "validate_advice",
    "validate_diagrams",
    "validate_profile",
    "validate_questions",
]
