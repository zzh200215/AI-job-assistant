"""P4：跨会话面试画像——把已完成会话的报告压成维度/技能弱点。

三条回流（简历改写、学习建议、下一场考察重点）读的是同一份结构，所以这里只做一件事：
把每场已完成面试压成一份紧凑的 session summary，再按 session_id 幂等合并成画像。

**画像不落库**：原稿给的是"新表或 user 级 JSON 列"，但画像是一组已完成报告的纯函数；
未执行的迁移会让 `tb_user` 的每条查询当场 Unknown column（P1.2 的教训），而这里的会话量只有
几十场，先按需派生。等有性能证据再谈持久化，别用一笔没跑的 DDL 换一个缓存。

两条阈值刻意不同：
- 维度弱点对齐现有 `/interview/performance` 的 65 分线（用户已经在那张页面上看到同一口径）；
- 技能弱点对齐 P3 决策器的 70 分深挖线（答得差才会被追问）。

超时题不是技能证据：P3 已定"没回答的题不许触发深挖"，这里同样把它放进 `unanswered_required`，
既不算"这项技能不会"，也不算"这项没考到"。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.interview_session import InterviewSession
from app.models.user import User
from app.services.skill_gap import canonical_skill, jd_required_names, normalize_skill, skill_match_terms
from app.utils.job_access import get_accessible_job
from app.utils.time_helper import utc_now

PROFILE_VERSION = 1
WEAK_DIMENSION_THRESHOLD = 65
WEAK_SKILL_THRESHOLD = 70
MAX_SESSIONS = 10
MAX_ITEMS = 8
MAX_UNASKED = 12

DIMENSION_LABELS = {
    "completeness": "完整性",
    "accuracy": "准确性",
    "depth": "深度",
    "expression": "表达力",
}


def _score(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("aspect", "detail", "text", "description", "comment", "suggestion"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
        return ""
    return "" if value is None else str(value).strip()


def _unique_texts(values: Any, *, limit: int = MAX_ITEMS) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _text(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
            if len(out) >= limit:
                break
    return out


def _dimension_scores(report: dict[str, Any]) -> dict[str, float]:
    raw = report.get("dimension_scores") or {}
    scores: dict[str, float] = {}
    for dimension in DIMENSION_LABELS:
        score = _score(raw.get(dimension))
        if score > 0:
            scores[dimension] = float(score)
    return scores


def _mentions(text: str, terms: list[str]) -> bool:
    normalized = normalize_skill(text)
    for term in terms:
        if not term:
            continue
        # 短 ASCII 名按词边界匹配：Go 不许在 Google 里命中；中文按子串匹配。
        if re.fullmatch(r"[a-z0-9+#.-]+", term):
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized):
                return True
        elif term in normalized:
            return True
    return False


def _question_text(item: dict[str, Any]) -> str:
    return str(item.get("question") or item.get("q") or "").strip()


def _is_eligible(item: dict[str, Any]) -> bool:
    return not item.get("timed_out") and _score(item.get("overall_score")) > 0


def _evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "question": _question_text(item)[:120],
        "score": _score(item.get("overall_score")),
        "feedback": _text(item.get("feedback"))[:120],
    }


def build_session_summary(session: InterviewSession) -> dict[str, Any] | None:
    """压一场已完成面试；没有有效作答就返回 None（画像不该被空报告污染）。"""
    if session is None or session.status != "completed":
        return None
    # 旧会话的结束路径没有把 evaluation_status 从 idle 推到 completed，但报告里的逐题评分
    # 已经齐了；只有 processing 才代表“还在评”，不能拿半份报告算画像。
    if (session.evaluation_status or "idle") == "processing":
        return None
    report = session.evaluation or {}
    if report.get("evaluation_status") == "processing":
        return None
    evaluations = [item for item in (report.get("question_evaluations") or []) if isinstance(item, dict)]
    eligible = [item for item in evaluations if _is_eligible(item)]
    if not eligible:
        return None

    memory = report.get("interview_memory") or session.memory_snapshot or {}
    required = _unique_texts(memory.get("jd_required_skills") or [], limit=50)
    dimensions = _dimension_scores(report)
    dimension_weaknesses = [
        {
            "dimension": dimension,
            "label": DIMENSION_LABELS[dimension],
            "avg_score": score,
        }
        for dimension, score in dimensions.items()
        if score < WEAK_DIMENSION_THRESHOLD
    ]
    dimension_weaknesses.sort(key=lambda row: (row["avg_score"], row["dimension"]))

    skill_scores: list[dict[str, Any]] = []
    unasked_required: list[str] = []
    unanswered_required: list[str] = []
    for skill in required:
        canonical = canonical_skill(skill) or normalize_skill(skill)
        if not canonical:
            continue
        terms = skill_match_terms(skill)
        matched = [item for item in eligible if _mentions(_question_text(item), terms)]
        timed_out = [item for item in evaluations if item.get("timed_out") and _mentions(_question_text(item), terms)]
        if matched:
            avg = round(sum(_score(item.get("overall_score")) for item in matched) / len(matched), 1)
            evidence = []
            for item in matched:
                row = _evidence(item)
                if row not in evidence:
                    evidence.append(row)
            skill_scores.append(
                {
                    "skill": skill,
                    "canonical": canonical,
                    "avg_score": avg,
                    "samples": len(matched),
                    "weak": avg < WEAK_SKILL_THRESHOLD,
                    "evidence": evidence[:3],
                }
            )
        elif timed_out:
            unanswered_required.append(skill)
        else:
            unasked_required.append(skill)

    skill_scores.sort(key=lambda row: (row["avg_score"], row["skill"]))
    skill_weaknesses = [row for row in skill_scores if row["weak"]][:MAX_ITEMS]

    completed_at = session.completed_at
    if hasattr(completed_at, "isoformat"):
        completed_at = completed_at.isoformat()

    return {
        "session_id": session.id,
        "user_id": session.user_id,
        "completed_at": completed_at,
        "interview_type": session.interview_type or "tech",
        "overall_score": _score(report.get("overall_score")),
        "dimensions": dimensions,
        "dimension_weaknesses": dimension_weaknesses,
        "required_skills": required,
        "skill_scores": skill_scores,
        "skill_weaknesses": skill_weaknesses,
        "unasked_required": unasked_required,
        "unanswered_required": unanswered_required,
        "weakness_texts": _unique_texts(report.get("weaknesses")),
        "strengths": _unique_texts(report.get("strengths")),
    }


def _empty_profile() -> dict[str, Any]:
    return {
        "version": PROFILE_VERSION,
        "has_data": False,
        "total_sessions": 0,
        "session_count": 0,
        "session_ids": [],
        "sessions": [],
        "dimension_scores": {},
        "dimension_weaknesses": [],
        "skill_scores": [],
        "skill_weaknesses": [],
        "unasked_required": [],
        "unanswered_required": [],
        "weakness_texts": [],
        "strengths": [],
        "last_session": None,
        "generated_at": None,
    }


def _session_sort_key(summary: dict[str, Any]) -> tuple[str, int]:
    return (str(summary.get("completed_at") or ""), int(summary.get("session_id") or 0))


def _aggregate_dimensions(sessions: list[dict[str, Any]]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    values: dict[str, list[float]] = {dimension: [] for dimension in DIMENSION_LABELS}
    for session in sessions:
        for dimension, score in (session.get("dimensions") or {}).items():
            if dimension in values and score:
                values[dimension].append(float(score))
    scores = {dimension: round(sum(items) / len(items), 1) for dimension, items in values.items() if items}
    weaknesses = [
        {
            "dimension": dimension,
            "label": DIMENSION_LABELS[dimension],
            "avg_score": score,
            "sessions": len(values[dimension]),
        }
        for dimension, score in scores.items()
        if score < WEAK_DIMENSION_THRESHOLD
    ]
    weaknesses.sort(key=lambda row: (row["avg_score"], row["dimension"]))
    return scores, weaknesses


def _aggregate_skills(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for session in sessions:
        for row in session.get("skill_scores") or []:
            canonical = row.get("canonical") or canonical_skill(row.get("skill"))
            if not canonical:
                continue
            group = groups.setdefault(
                canonical,
                {
                    "skill": row.get("skill") or canonical,
                    "canonical": canonical,
                    "weighted_score": 0.0,
                    "samples": 0,
                    "sessions": 0,
                    "evidence": [],
                },
            )
            samples = max(1, int(row.get("samples") or 1))
            group["weighted_score"] += float(row.get("avg_score") or 0) * samples
            group["samples"] += samples
            group["sessions"] += 1
            for item in row.get("evidence") or []:
                if item not in group["evidence"]:
                    group["evidence"].append(item)
    rows: list[dict[str, Any]] = []
    for group in groups.values():
        avg = round(group["weighted_score"] / group["samples"], 1) if group["samples"] else 0.0
        rows.append(
            {
                "skill": group["skill"],
                "canonical": group["canonical"],
                "avg_score": avg,
                "samples": group["samples"],
                "sessions": group["sessions"],
                "weak": avg < WEAK_SKILL_THRESHOLD,
                "evidence": group["evidence"][:3],
            }
        )
    rows.sort(key=lambda row: (row["avg_score"], row["skill"]))
    return rows


def merge_profile(existing: dict[str, Any] | None, summary: dict[str, Any]) -> dict[str, Any]:
    """按 session_id 幂等合并；同一场重放不会把样本数翻倍。"""
    profile = _empty_profile()
    previous_sessions = list((existing or {}).get("sessions") or [])
    is_new = all(item.get("session_id") != summary.get("session_id") for item in previous_sessions)
    sessions = [item for item in previous_sessions if item.get("session_id") != summary.get("session_id")]
    sessions.append(summary)
    sessions.sort(key=_session_sort_key)
    sessions = sessions[-MAX_SESSIONS:]

    previous_total = int((existing or {}).get("total_sessions") or len(previous_sessions) or 0)
    total_sessions = previous_total + (1 if is_new else 0)
    dimension_scores, dimension_weaknesses = _aggregate_dimensions(sessions)
    skill_scores = _aggregate_skills(sessions)
    matched = {row["canonical"] for row in skill_scores}

    required: dict[str, str] = {}
    unanswered: set[str] = set()
    for session in sessions:
        for skill in session.get("required_skills") or []:
            canonical = canonical_skill(skill) or normalize_skill(skill)
            if canonical:
                required.setdefault(canonical, skill)
        for skill in session.get("unanswered_required") or []:
            canonical = canonical_skill(skill) or normalize_skill(skill)
            if canonical:
                unanswered.add(canonical)
    unasked = [
        skill for canonical, skill in required.items() if canonical not in matched and canonical not in unanswered
    ]
    unanswered_required = [
        skill for canonical, skill in required.items() if canonical in unanswered and canonical not in matched
    ]

    weakness_texts = _unique_texts([text for session in sessions for text in (session.get("weakness_texts") or [])])
    strengths = _unique_texts([text for session in sessions for text in (session.get("strengths") or [])])
    last = sessions[-1]
    profile.update(
        {
            "has_data": True,
            "total_sessions": total_sessions,
            "session_count": len(sessions),
            "session_ids": [item.get("session_id") for item in sessions],
            "sessions": sessions,
            "dimension_scores": dimension_scores,
            "dimension_weaknesses": dimension_weaknesses,
            "skill_scores": skill_scores,
            "skill_weaknesses": [row for row in skill_scores if row["weak"]][:MAX_ITEMS],
            "unasked_required": unasked[:MAX_UNASKED],
            "unanswered_required": unanswered_required[:MAX_UNASKED],
            "weakness_texts": weakness_texts,
            "strengths": strengths,
            "last_session": {
                "session_id": last.get("session_id"),
                "completed_at": last.get("completed_at"),
                "interview_type": last.get("interview_type"),
                "overall_score": last.get("overall_score"),
            },
            "generated_at": utc_now().isoformat(),
        }
    )
    return profile


def build_profile(db: Session, user_id: int) -> dict[str, Any]:
    """从该用户所有已完成会话派生画像；窗口只留最近 MAX_SESSIONS 场。"""
    sessions = (
        db.query(InterviewSession)
        .filter(InterviewSession.user_id == user_id, InterviewSession.status == "completed")
        .order_by(InterviewSession.completed_at.asc(), InterviewSession.id.asc())
        .all()
    )
    summaries = [summary for session in sessions if (summary := build_session_summary(session))]
    profile = _empty_profile()
    for summary in summaries:
        profile = merge_profile(profile, summary)
    profile["total_sessions"] = len(summaries)
    profile["generated_at"] = utc_now().isoformat()
    profile["has_data"] = bool(summaries)
    return profile


def get_profile(db: Session, user_id: int) -> dict[str, Any]:
    return build_profile(db, user_id)


def jd_focus(db: Session, user: User, jd_id: int | None, profile: dict[str, Any]) -> dict[str, Any]:
    """本场 JD 必考项与上一场技能弱点的**逐项交集**（设置页"重点考察 X"的数据源）。

    与建会话时的倾斜同一把尺：`canonical_skill` 对齐 K8s / Kubernetes；别岗位旧弱点
    不参与。岗位不可见时返回空交集，不猜。
    """
    job = get_accessible_job(db, jd_id, user) if jd_id is not None else None
    if job is None:
        return {"jd_id": jd_id, "title": "", "required_count": 0, "overlap": []}

    required = jd_required_names(job.parsed_json or {}) or [str(item) for item in (job.skill_tags or [])]
    required_canonical = {canonical_skill(skill) for skill in required if canonical_skill(skill)}
    overlap = []
    for row in (profile or {}).get("skill_weaknesses") or []:
        if not isinstance(row, dict):
            continue
        canonical = row.get("canonical") or canonical_skill(row.get("skill"))
        if not canonical or canonical not in required_canonical:
            continue
        overlap.append(
            {
                "skill": row.get("skill") or canonical,
                "canonical": canonical,
                "avg_score": row.get("avg_score"),
                "sessions": row.get("sessions"),
            }
        )
    return {
        "jd_id": job.id,
        "title": job.title or "",
        "required_count": len(required_canonical),
        "overlap": overlap,
    }


def tilt_questions_by_profile(
    questions: list[dict[str, Any]],
    required_skills: list[str],
    profile: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """把"问到了上一场弱项"的本场必考项排到开场前面；没命中就原样返回。

    只认本场 JD 必考项：旧画像里别岗位的弱项不参与。题面走共享别名表
    （K8s / Kubernetes 同一项，短 ASCII 名按词边界，Go 不会在 Google 里命中）。
    稳定分区：命中组与非命中组各自保持原顺序。
    """
    if not questions:
        return list(questions)
    required = {canonical_skill(skill) for skill in (required_skills or []) if canonical_skill(skill)}
    weak: list[str] = []
    for row in (profile or {}).get("skill_weaknesses") or []:
        if not isinstance(row, dict):
            continue
        canonical = canonical_skill(row.get("canonical")) or canonical_skill(row.get("skill"))
        if canonical and canonical in required and canonical not in weak:
            weak.append(canonical)
    if not weak:
        return list(questions)

    terms = sorted({term for skill in weak for term in skill_match_terms(skill) if term})
    if not terms:
        return list(questions)

    def covered(question: dict[str, Any]) -> bool:
        return _mentions(str(question.get("question") or question.get("q") or ""), terms)

    front = [question for question in questions if covered(question)]
    if not front:
        return list(questions)
    return front + [question for question in questions if not covered(question)]


def compact_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    """新会话快照只带"下一场要优先关注什么"，不搬证据卡与逐场明细。"""
    source = profile or {}
    return {
        "skill_weaknesses": [
            {key: row.get(key) for key in ("skill", "canonical", "avg_score", "sessions")}
            for row in (source.get("skill_weaknesses") or [])
            if isinstance(row, dict)
        ][:MAX_ITEMS],
        "dimension_weaknesses": [
            {key: row.get(key) for key in ("dimension", "label", "avg_score")}
            for row in (source.get("dimension_weaknesses") or [])
            if isinstance(row, dict)
        ][:4],
        "weakness_texts": [str(item).strip() for item in (source.get("weakness_texts") or []) if str(item).strip()][:4],
        "last_session": source.get("last_session"),
    }


def public_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """路由载荷：内部 `sessions` 明细不外发，避免把整份报告搬进列表页。"""
    return {
        "has_data": bool(profile.get("has_data")),
        "total_sessions": int(profile.get("total_sessions") or 0),
        "session_count": int(profile.get("session_count") or 0),
        "generated_at": profile.get("generated_at"),
        "dimension_scores": profile.get("dimension_scores") or {},
        "dimension_weaknesses": profile.get("dimension_weaknesses") or [],
        "skill_weaknesses": profile.get("skill_weaknesses") or [],
        "unasked_required": profile.get("unasked_required") or [],
        "unanswered_required": profile.get("unanswered_required") or [],
        "weakness_texts": profile.get("weakness_texts") or [],
        "strengths": profile.get("strengths") or [],
        "last_session": profile.get("last_session"),
    }
