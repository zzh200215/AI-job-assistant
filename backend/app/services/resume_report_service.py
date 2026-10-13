"""简历评估报告的编排：六个阶段串成一份可交付的 Report。

* 模块一/二/三 复用 `resume_analysis_service.analyze_resume`（七维那张表只有一份实现）；
* 模块三（批改稿）与模块四（面试预演）各带一个**纯函数复核**：模型只能提出、不能自证。
  `del` 必须逐字命中块文本且在该块里唯一；改写与口述稿里的数字必须是这份简历里已有的，
  新的只允许包在 `【待补：…】` 里；
* 模块五（投递策略）不过模型，逐字引用 `docs/report-templates/boss_zhipin_strategy.md`。

§5 那张禁词表与省略写法表**从 `report_html_lint` 导入**，不在这里抄第二份：
两个地方各持一份同一条规则，迟早一份改了另一份没改。

阶段失败沿用"AI 降级对候选人静默、对内可查"那条口径：某一段挂了就整段缺席，
`stage_errors` 记下原因，候选人看不到一句"模型出错了"。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription, Resume
from app.prompts.rendering import render_prompt
from app.prompts.resume_report_interview import PROMPT_VERSION as INTERVIEW_PROMPT_VERSION
from app.prompts.resume_report_interview import RESUME_REPORT_INTERVIEW_PROMPT
from app.prompts.resume_report_redline import PROMPT_VERSION as REDLINE_PROMPT_VERSION
from app.prompts.resume_report_redline import RESUME_REPORT_REDLINE_PROMPT
from app.services.llm_service import chat_json, get_llm_provenance, set_llm_trace_context
from app.services.report_html_lint import FOLLOWUP_ATOMS, FORBIDDEN_ELLIPSIS, FORBIDDEN_MECHANISM_WORDS
from app.services.resume_analysis_service import analyze_resume
from app.services.resume_blocks import build_report_sections
from app.services.resume_report_rubric import interview_allowed
from app.services.resume_report_schema import (
    INTERVIEW_DEFERRED_NOTE,
    STAT_MODE_CHANGES,
    STAT_MODE_OPTIONAL,
    STAT_MODE_UNCHANGED,
    Redline,
    RedlineBlock,
    RedlineEdit,
    Report,
)
from app.utils.service_access import get_owned_resume
from app.utils.time_helper import utc_now

logger = logging.getLogger(__name__)

MAX_REDLINE_EDITS = 40
QUESTION_KINDS = ("基础概念", "项目深挖", "对比权衡", "踩坑与边界", "场景设计")
QUESTION_STATUSES = ("可答", "需补强")
MIN_ANSWER_CHARS = 120
# 追问必须是三条：少于三条准备不到第三层，多于三条这一节就压不进一页。
FOLLOWUP_COUNT = 3

_TODO = re.compile(r"【待补[^】]*】")
_DIGITS = re.compile(r"\d+(?:\.\d+)?")

APPLY_STRATEGY_PATH = Path(__file__).resolve().parents[3] / "docs" / "report-templates" / "boss_zhipin_strategy.md"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _todo_spans(text: str) -> list[str]:
    return _TODO.findall(text)


def _blocked_words(text: str) -> list[str]:
    return [word for word in FORBIDDEN_MECHANISM_WORDS + FORBIDDEN_ELLIPSIS if word in text]


def invented_numbers(written: str, known_text: str) -> list[str]:
    """改写里出现、而整份简历里一个都没有的数字。

    先剥掉 `【待补：…】`——那是规范给"该有个数但还没实测"留的合法出口。
    """
    cleaned = _TODO.sub("", written)
    return [run for run in _DIGITS.findall(cleaned) if run not in known_text]


def _resume_digit_source(parsed: dict[str, Any] | None) -> str:
    return json.dumps(parsed or {}, ensure_ascii=False)


def _label_atoms(label: str) -> list[str]:
    return [atom.strip() for atom in label.replace("……", "").replace("。", "").split("/") if atom.strip()]


def validate_redline_edits(
    sections: list[dict[str, Any]],
    payload: Any,
    known_text: str,
    limit: int = MAX_REDLINE_EDITS,
) -> tuple[Redline, list[dict[str, Any]]]:
    """把模型给的句级批改折成 Redline，被拒的带原因返回。

    **编号在这里按成稿顺序分配，不信模型自报的序号**：正文编号与右栏批注一一对应
    是机检里最硬的一条，靠构造满足比靠校验模型靠谱。
    """
    by_id = {block["block_id"]: block for block in sections}
    raw = payload.get("edits") if isinstance(payload, dict) else payload
    rejected: list[dict[str, Any]] = []
    accepted: dict[str, list[RedlineEdit]] = {}
    seen: set[tuple[str, str]] = set()

    if not isinstance(raw, list):
        rejected.append({"block_id": None, "reason": "malformed_response"})
        raw = []

    def refuse(block_id: Any, reason: str, **extra: Any) -> None:
        item: dict[str, Any] = {"block_id": block_id if isinstance(block_id, str) else None, "reason": reason}
        item.update(extra)
        rejected.append(item)

    for entry in raw:
        if not isinstance(entry, dict):
            refuse(None, "not_an_object")
            continue

        block_id = entry.get("block_id")
        block = by_id.get(block_id) if isinstance(block_id, str) else None
        if block is None:
            refuse(block_id, "unknown_block")
            continue

        del_text = _text(entry.get("del"))
        if not del_text:
            refuse(block_id, "empty_del")
            continue
        hits = block["text"].count(del_text)
        if hits == 0:
            refuse(block_id, "original_mismatch")
            continue
        if hits > 1:
            # 同一个短语在一段里出现两次，位置就不确定：写回哪一处都是猜。
            refuse(block_id, "ambiguous_anchor")
            continue
        if (block_id, del_text) in seen:
            refuse(block_id, "duplicate_edit")
            continue

        tier = _text(entry.get("tier"))
        if tier not in ("key", "normal"):
            refuse(block_id, "bad_tier")
            continue

        ins_text = _text(entry.get("ins"))
        bad_numbers = invented_numbers(ins_text, known_text)
        if bad_numbers:
            refuse(block_id, "invented_number", detail=bad_numbers[:5])
            continue

        note = _text(entry.get("note"))
        if not note:
            refuse(block_id, "empty_note")
            continue
        blocked = _blocked_words(note)
        if blocked:
            refuse(block_id, "forbidden_word", detail=blocked[:5])
            continue

        overlapping = [
            existing.mark
            for existing in accepted.get(block_id, [])
            if existing.del_text in del_text or del_text in existing.del_text
        ]
        if overlapping:
            refuse(block_id, "overlapping_edit", detail=overlapping[:3])
            continue

        seen.add((block_id, del_text))
        accepted.setdefault(block_id, []).append(
            RedlineEdit(mark=0, block_id=block_id, del_text=del_text, ins_text=ins_text, note=note, key=tier == "key")
        )

    flat: list[tuple[dict[str, Any], RedlineEdit]] = []
    for block in sections:
        flat.extend((block, edit) for edit in accepted.get(block["block_id"], []))
    if len(flat) > limit:
        for _ in flat[limit:]:
            refuse(None, "over_limit")
        flat = flat[:limit]

    blocks: list[RedlineBlock] = []
    indexed: dict[str, RedlineBlock] = {}
    mark = 0
    for block, edit in flat:
        mark += 1
        edit.mark = mark
        row = indexed.get(block["block_id"])
        if row is None:
            row = RedlineBlock(
                block_id=block["block_id"],
                label=block["label"],
                text=block["text"],
                editable=bool(block.get("editable", True)),
            )
            indexed[block["block_id"]] = row
            blocks.append(row)
        row.edits.append(edit)

    free_note = _text(payload.get("no_change_note")) if isinstance(payload, dict) else ""
    # "这一版可以原样用"是一句**主张**，只在模型真的给出空清单时才成立。
    # 载荷读不出来、或给了批改却全被复核拒掉，都不是"没问题"，是"这一段没出来"——
    # 那种情况返回 None，让调用方记 stage_error，别让一句假话上屏。
    if not isinstance(payload, dict) or not isinstance(payload.get("edits"), list):
        return None, rejected
    if not mark and raw:
        return None, rejected

    redline = Redline(blocks=blocks)
    if redline.key_total:
        redline.mode = STAT_MODE_CHANGES
    elif redline.total:
        redline.mode = STAT_MODE_OPTIONAL
        redline.free_note = free_note
    else:
        redline.mode = STAT_MODE_UNCHANGED
        redline.free_note = free_note or "这一版没有必须动手改的地方，保持原样投出去就行。"

    return redline, rejected


def _pending_facts(redline: Redline | None) -> str:
    if redline is None:
        return "（本次没有批改稿）"
    spans: list[str] = []
    for edit in redline.edits:
        for span in _todo_spans(edit.ins_text) + _todo_spans(edit.note):
            if span not in spans:
                spans.append(span)
    return "、".join(spans) if spans else "（批改稿里没有留【待补】的数）"


def _score_block(report: Report) -> str:
    lines = []
    for row in report.dimensions:
        score = "未知" if row["score"] is None else f"{row['score']}/{row['full']}"
        lines.append(f"- {row['label']}：{score}；{row['note'] or '（这一维没有写待优化点）'}")
    total = report.total_score if report.total_score is not None else "未知"
    lines.append(f"合计：{total}/100，等级 {report.grade or '未知'}")
    return "\n".join(lines)


def validate_interview_questions(payload: Any, known_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """题型、状态、追问类型三处白名单 + 口述稿里的数字必须是简历里已有的。"""
    raw = payload.get("questions") if isinstance(payload, dict) else payload
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return [], [{"reason": "malformed_response"}]

    for entry in raw:
        if not isinstance(entry, dict):
            rejected.append({"reason": "not_an_object"})
            continue

        question = _text(entry.get("question"))
        kind = _text(entry.get("kind"))
        answer = _text(entry.get("answer"))
        status = _text(entry.get("status"))
        followups = _list(entry.get("followups"))
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
        bad = invented_numbers(answer, known_text)
        if bad:
            rejected.append(stamp | {"reason": "invented_number", "detail": bad[:5]})
            continue
        if status not in QUESTION_STATUSES:
            rejected.append(stamp | {"reason": "bad_status", "detail": status})
            continue
        missing = [_text(item) for item in _list(entry.get("missing")) if _text(item)]
        if status == "需补强" and not missing:
            # "需补强"却不说是缺哪个数，候选人无从下手，这一句就成了纯装饰。
            rejected.append(stamp | {"reason": "missing_not_named"})
            continue
        if len(followups) != FOLLOWUP_COUNT:
            rejected.append(stamp | {"reason": "followup_count", "detail": len(followups)})
            continue

        normalized: list[dict[str, str]] = []
        bad_followup_reason = ""
        for follow in followups:
            if not isinstance(follow, dict):
                bad_followup_reason = "not_an_object"
                break
            label = _text(follow.get("kind"))
            body = _text(follow.get("text"))
            atoms = _label_atoms(label)
            if not body:
                bad_followup_reason = "empty_followup"
                break
            if not atoms or any(atom not in FOLLOWUP_ATOMS for atom in atoms):
                bad_followup_reason = "bad_followup_kind"
                break
            normalized.append({"kind": label, "text": body})
        if bad_followup_reason:
            rejected.append(stamp | {"reason": bad_followup_reason})
            continue

        accepted.append(
            {
                "no": len(accepted) + 1,
                "question": question,
                "kind": kind,
                "project": _text(entry.get("project")) or "通用",
                "answer": answer,
                "followups": normalized,
                "status": status,
                "missing": missing if status == "需补强" else [],
            }
        )

    return accepted, rejected


def interview_distribution(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """分布由这里数出来。模型自报的 `total_questions` 历来和实际题数对不上。"""
    by_kind: dict[str, int] = {}
    by_project: dict[str, int] = {}
    for question in questions:
        by_kind[question["kind"]] = by_kind.get(question["kind"], 0) + 1
        by_project[question["project"]] = by_project.get(question["project"], 0) + 1
    return {
        "total": len(questions),
        "by_kind": by_kind,
        "by_project": by_project,
        "weak": sum(1 for question in questions if question["status"] == "需补强"),
    }


def load_apply_strategy(path: Path | None = None) -> dict[str, Any] | None:
    """逐字读第五节的五段。

    读不出来就返回 None：这一节是树里的一份定稿文本，不是模型输出，
    没有"降级出一份等价文字"这条路——文件不在就是树坏了。
    """
    target = path or APPLY_STRATEGY_PATH
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("投递策略原文读不出来 %s: %s", target, exc)
        return None

    chapters: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                chapters.append(current)
            current = {"title": line[3:].strip(), "blocks": []}
            continue
        if current is None:
            continue
        if line.strip():
            current["blocks"].append(line.rstrip())
        elif current["blocks"] and current["blocks"][-1] != "":
            current["blocks"].append("")
    if current is not None:
        chapters.append(current)

    for chapter in chapters:
        paragraphs: list[str] = []
        lines: list[str] = []
        for line in chapter["blocks"]:
            if line == "":
                if lines:
                    paragraphs.append("\n".join(lines))
                    lines = []
                continue
            lines.append(line)
        if lines:
            paragraphs.append("\n".join(lines))
        chapter["paragraphs"] = paragraphs
        del chapter["blocks"]

    chapters = chapters[:5]
    if not chapters:
        return None
    return {"source": "docs/report-templates/boss_zhipin_strategy.md", "chapters": chapters}


def _jd_text(jd: JobDescription | None) -> str:
    if jd is None:
        return "未指定目标岗位，按通用简历质量批改。"
    parsed = jd.parsed_json or {}
    return json.dumps(
        {"title": parsed.get("title") or jd.title, "required_skills": parsed.get("required_skills", [])},
        ensure_ascii=False,
    )


def _prompt_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"block_id": b["block_id"], "label": b["label"], "text": b["text"], "editable": b["editable"]} for b in sections
    ]


def build_redline(
    resume: Resume,
    sections: list[dict[str, Any]],
    jd: JobDescription | None,
) -> tuple[Redline | None, list[dict[str, Any]]]:
    if not sections:
        return None, [{"block_id": None, "reason": "no_sections"}]

    set_llm_trace_context(
        {
            "source": "resume_report_service.build_redline",
            "prompt_version": REDLINE_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    prompt = render_prompt(
        RESUME_REPORT_REDLINE_PROMPT,
        sections_json=json.dumps(_prompt_sections(sections), ensure_ascii=False, indent=2),
        jd_text=_jd_text(jd),
        max_edits=MAX_REDLINE_EDITS,
    )
    payload = chat_json(prompt, disable_thinking=True)
    redline, rejected = validate_redline_edits(sections, payload, _resume_digit_source(resume.parsed_json))
    return redline, rejected


def build_interview(resume: Resume, report: Report, target_position: str) -> dict[str, Any]:
    """§6：总分不达标时整块换成"暂缓生成"版——不出题，也就不花这一发模型钱。"""
    if not interview_allowed(report.total_score):
        return {"deferred": True, "note": INTERVIEW_DEFERRED_NOTE, "questions": [], "distribution": None}

    set_llm_trace_context(
        {
            "source": "resume_report_service.build_interview",
            "prompt_version": INTERVIEW_PROMPT_VERSION,
            "resume_id": resume.id,
        }
    )
    prompt = render_prompt(
        RESUME_REPORT_INTERVIEW_PROMPT,
        resume_json=json.dumps(resume.parsed_json or {}, ensure_ascii=False, indent=2),
        score_block=_score_block(report),
        pending_facts=_pending_facts(report.redline),
        target_position=target_position or "未指定（按简历关键词自动识别方向）",
    )
    # 这一发也关思考链，理由和改写作业那一发同源但更硬：这是整条链里**输出最长**的一支
    # （18–22 题 × 口述稿 + 三条追问）。D189 量过同一族简历 prompt 开着思考链时
    # 91.77s / 95.33s 返回的 `content` 长度为 0（8192 个 completion token 全花在 reasoning 上）——
    # 输出预算越紧的那一支越先撞上这一条，而空 content 会被判成 provider 失败、整节缺席。
    payload = chat_json(prompt, disable_thinking=True)
    questions, rejected = validate_interview_questions(payload, _resume_digit_source(resume.parsed_json))
    report.provenance["interview"] = get_llm_provenance()
    report.interview_rejected = rejected
    if not questions:
        # 一题都没过复核 ≠ 这一轮没有题可问。返回 None，由调用方记原因。
        return None
    return {
        "deferred": False,
        "note": "",
        "questions": questions,
        "distribution": interview_distribution(questions),
    }


def _first_sentence(text: str, limit: int = 60) -> str:
    head = re.split(r"[。\n]", text.strip(), maxsplit=1)[0].strip()
    return head if len(head) <= limit else head[: limit - 1] + "…"


def build_personalization(sections: list[dict[str, Any]], competition: dict[str, Any]) -> dict[str, str]:
    """§7 点名的两处填空：在线简历的一句话标签、打招呼第一句里的项目亮点。

    两处都是**引用**报告里已有的话，不是再让模型写一句自我介绍：
    标签取第三节"个人优势"的第一句原文，亮点取竞争分析那张能打的牌。
    算在数据层，应用内那一页与下载的那份 HTML 才读得到同一份内容。
    """
    advantage = next((s.get("text") or "" for s in sections if s.get("block_id") == "self_evaluation"), "")
    cards = competition.get("cards") or []
    return {
        "one_line_label": _first_sentence(advantage),
        "opener": _text(cards[0]) if cards else "",
    }


def generate_resume_report(
    db: Session,
    resume_id: int,
    jd_id: int | None = None,
    target_position: str = "",
    user_id: int | None = None,
) -> Report:
    """跑完六个阶段，返回一份 Report。"""
    resume = get_owned_resume(db, resume_id, user_id) if user_id is not None else db.get(Resume, resume_id)
    if resume is None:
        raise ValueError("简历不存在或无权限")

    jd: JobDescription | None = None
    if jd_id is not None:
        jd = db.get(JobDescription, jd_id)
        if jd is None:
            raise ValueError("目标岗位不存在")
        if not target_position:
            target_position = jd.title or ""

    report = Report(
        resume_id=resume_id,
        user_id=user_id,
        jd_id=jd_id,
        target_position=target_position,
        report_date=utc_now().strftime("%Y-%m-%d"),
    )

    # 阶段一：模块一/二/三。这一段失败就往上抛——没有七维评分的报告没有意义，
    # 后面每一段都要读它的分数。
    overview = analyze_resume(db, resume_id, target_position=target_position, user_id=user_id)
    report.verdict = overview["verdict"]
    report.dimensions = overview["dimensions"]
    report.total_score = overview["total_score"]
    report.grade = overview["grade"]
    report.grade_desc = overview["grade_desc"]
    report.grade_scale = overview["grade_scale"]
    report.to_next_grade = overview["to_next_grade"]
    report.missing_keywords = overview["missing_keywords"]
    report.competition = overview["competition"]
    report.model_reported_total = overview["model_reported_total"]
    report.provenance["overview"] = get_llm_provenance()

    # 阶段二：批改稿。挂了只缺这一节。
    sections = build_report_sections(resume.parsed_json)
    report.sections = sections
    report.personalization = build_personalization(sections, report.competition)
    try:
        redline, rejected = build_redline(resume, sections, jd)
        report.redline_rejected = rejected
        if redline is None:
            report.stage_errors["redline"] = (
                "模型这一发没有给出可解析的批改清单" if not rejected else f"{len(rejected)} 条批改全部未通过复核"
            )
        else:
            report.redline = redline
            if rejected:
                report.stage_errors["redline_partial"] = f"{len(rejected)} 条批改未通过复核"
        report.provenance["redline"] = get_llm_provenance()
    except Exception as exc:  # noqa: BLE001 - 一段挂了不影响其余各段
        logger.exception("批改稿阶段失败 resume=%s", resume_id)
        report.stage_errors["redline"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    # 阶段三：面试预演（读批改稿里留下的【待补】）。
    try:
        report.interview = build_interview(resume, report, target_position)
        if report.interview is None:
            rejected = report.interview_rejected
            report.stage_errors["interview"] = (
                "模型这一发没有给出可用的题" if not rejected else f"{len(rejected)} 道题全部未通过复核"
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("面试预演阶段失败 resume=%s", resume_id)
        report.stage_errors["interview"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    # 阶段四：投递策略，不经模型。
    report.apply_strategy = load_apply_strategy()
    if report.apply_strategy is None:
        report.stage_errors["apply_strategy"] = "投递策略原文读不出来"

    return report


__all__ = [
    "MAX_REDLINE_EDITS",
    "QUESTION_KINDS",
    "build_interview",
    "build_personalization",
    "build_redline",
    "generate_resume_report",
    "interview_distribution",
    "invented_numbers",
    "load_apply_strategy",
    "validate_interview_questions",
    "validate_redline_edits",
]
