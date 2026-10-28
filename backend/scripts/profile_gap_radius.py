#!/usr/bin/env python3
"""旧报告画像缺口半径：缺 `interview_memory.jd_required_skills` 的会话能不能从 JD 推回——只读。

设置页/画像里"上一场技能弱点"来自 `build_session_summary`：它按
`interview_memory.jd_required_skills` 把逐题评分归到技能上。早期会话没有这个键，
所以画像里技能弱点为空（2026-10-20 活页发现）。这条半径回答三件事：

1. 多少已完成会话根本没有必考项、也没有可回推的 JD；
2. 多少能从关联 JD 的 `required_skills` / `skill_tags` 推回；
3. 推回后会在画像里**新增**多少条当前没有的技能弱点——这决定要不要补口径。

回填（写 `interview_memory` 或改画像派生）不在本脚本里，要另一次拍板。

用法：
    python scripts/profile_gap_radius.py           # 人读汇总
    python scripts/profile_gap_radius.py --json     # 机读
    python scripts/profile_gap_radius.py --limit 40 # 明细条数

零写入：全程 SELECT；测试把 `Session.commit/flush` 换成"一调用就红"来证。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.history import JobDescription  # noqa: E402
from app.models.interview_session import InterviewSession  # noqa: E402
from app.services.interview_profile_service import build_session_summary, get_profile  # noqa: E402
from app.services.skill_gap import canonical_skill, jd_required_names  # noqa: E402


def _required_from_report(session: InterviewSession) -> list[str]:
    report = session.evaluation if isinstance(session.evaluation, dict) else {}
    memory = report.get("interview_memory") or session.memory_snapshot or {}
    raw = memory.get("jd_required_skills") if isinstance(memory, dict) else None
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _required_from_jd(jd: JobDescription | None) -> list[str]:
    if jd is None:
        return []
    return jd_required_names(jd.parsed_json or {}) or [
        str(item).strip() for item in (jd.skill_tags or []) if str(item).strip()
    ]


def _summary_with_required(session: InterviewSession, required: list[str]) -> dict | None:
    """用推回的必考项重算这一场的 summary；不碰 ORM 对象，拷一份报告。"""
    report = dict(session.evaluation or {})
    memory = dict(report.get("interview_memory") or {})
    memory["jd_required_skills"] = list(required)
    report["interview_memory"] = memory
    shim = SimpleNamespace(
        id=session.id,
        user_id=session.user_id,
        interview_type=session.interview_type,
        status=session.status,
        evaluation_status=session.evaluation_status,
        evaluation=report,
        memory_snapshot=session.memory_snapshot,
        completed_at=session.completed_at,
    )
    return build_session_summary(shim)


def build_report(db: Session, detail_limit: int) -> dict:
    sessions = db.query(InterviewSession).order_by(InterviewSession.id.asc()).all()
    profile_cache: dict[int, set[str]] = {}

    summary = {
        "sessions_total": len(sessions),
        "by_status": dict(Counter(session.status or "unknown" for session in sessions)),
        "completed": 0,
        "completed_without_report": 0,
        "with_required": 0,
        "missing_required": 0,
        "missing_with_jd": 0,
        "recoverable": 0,
        "recoverable_no_summary": 0,
        "recoverable_but_no_new_weakness": 0,
        "would_gain_sessions": 0,
        "would_gain_weaknesses": 0,
        "unrecoverable_no_jd": 0,
        "unrecoverable_missing_jd_row": 0,
        "unrecoverable_jd_no_skills": 0,
        "profile_errors": 0,
    }
    detail = []

    for session in sessions:
        if session.status != "completed":
            continue
        summary["completed"] += 1
        if not isinstance(session.evaluation, dict) or not session.evaluation:
            summary["completed_without_report"] += 1
            continue

        if _required_from_report(session):
            summary["with_required"] += 1
            continue

        summary["missing_required"] += 1
        if session.jd_id is None:
            summary["unrecoverable_no_jd"] += 1
            continue
        summary["missing_with_jd"] += 1
        jd = db.get(JobDescription, session.jd_id)
        if jd is None:
            summary["unrecoverable_missing_jd_row"] += 1
            continue
        required = _required_from_jd(jd)
        if not required:
            summary["unrecoverable_jd_no_skills"] += 1
            continue
        summary["recoverable"] += 1

        patched = _summary_with_required(session, required)
        if not patched:
            # 有必考项但报告里没有可计入的作答（全超时/空评分）：推回了也派生不出弱点。
            summary["recoverable_no_summary"] += 1
            continue
        user_id = int(session.user_id or 0)
        if user_id not in profile_cache:
            try:
                profile = get_profile(db, user_id)
                profile_cache[user_id] = {
                    row.get("canonical") or canonical_skill(row.get("skill"))
                    for row in (profile.get("skill_weaknesses") or [])
                    if isinstance(row, dict)
                }
            except Exception as exc:  # 读不出画像就说出来，不按"没有弱点"蒙混
                summary["profile_errors"] += 1
                print(f"画像读取失败 user={user_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
                profile_cache[user_id] = set()
        current = profile_cache[user_id]
        gained = []
        for row in patched.get("skill_weaknesses") or []:
            canonical = row.get("canonical") or canonical_skill(row.get("skill"))
            if canonical and canonical not in current:
                gained.append(
                    {
                        "skill": row.get("skill"),
                        "canonical": canonical,
                        "avg_score": row.get("avg_score"),
                    }
                )
        if gained:
            summary["would_gain_sessions"] += 1
            summary["would_gain_weaknesses"] += len(gained)
            detail.append(
                {
                    "session_id": session.id,
                    "user_id": session.user_id,
                    "jd_id": session.jd_id,
                    "required_from_jd": len(required),
                    "gained": gained,
                }
            )
        else:
            summary["recoverable_but_no_new_weakness"] += 1

    detail.sort(key=lambda row: (-len(row["gained"]), row["session_id"]))
    return {"summary": summary, "detail": detail[:detail_limit]}


def print_human(report: dict) -> None:
    s = report["summary"]
    print(f"会话：{s['sessions_total']}（按状态 {s['by_status']}）")
    print(f"  已完成：{s['completed']} · 其中报告为空：{s['completed_without_report']}")
    print(f"  报告里有必考项：{s['with_required']} · 缺必考项：{s['missing_required']}")
    print(
        f"    缺但挂了 JD：{s['missing_with_jd']} → 可从 JD 推回：{s['recoverable']} · "
        f"JD 也没有必考项：{s['unrecoverable_jd_no_skills']} · JD 行已不在：{s['unrecoverable_missing_jd_row']}"
    )
    print(f"    没挂 JD：{s['unrecoverable_no_jd']}")
    print(
        f"  推回后会新增技能弱点：{s['would_gain_sessions']} 场 / {s['would_gain_weaknesses']} 条；"
        f"推回但无新增：{s['recoverable_but_no_new_weakness']} · 无可计入作答：{s['recoverable_no_summary']}"
    )
    print(f"  画像读取失败：{s['profile_errors']}")
    print("\n会新增弱点的会话：")
    if not report["detail"]:
        print("  （没有）")
    for row in report["detail"]:
        print(
            f"  #{row['session_id']} user={row['user_id']} jd={row['jd_id']} "
            f"JD 必考 {row['required_from_jd']} 条 → 新增 {[g['skill'] for g in row['gained']]}"
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="旧报告画像缺口半径（只读）")
    ap.add_argument("--json", action="store_true", help="输出机读 JSON")
    ap.add_argument("--limit", type=int, default=15, help="明细最多列几条（默认 15）")
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        report = build_report(db, args.limit)
    finally:
        db.rollback()
        db.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
