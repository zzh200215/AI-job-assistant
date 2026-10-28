#!/usr/bin/env python3
"""D281 存量半径：完整规划的 `skill_gaps` 里有多少条还没有 canonical——只读，一条都不写。

新规划由 `career_agent.annotate_skill_gaps()` 在落库前补 `canonical`，前端据此把面试
证据贴到别名的缺口上（K8s ↔ kubernetes）。历史分析记录里存下的 `skill_gaps` 没有这个
字段，前端只能退回拼写比较——所以"要不要回填存量"这个问题，在拿到 affected 行数、
会多贴出几条证据之前无法回答。回填本身（写路径）不在这里，那要单独拍板。

用法：
    python scripts/career_gap_canonical_radius.py           # 人读的汇总
    python scripts/career_gap_canonical_radius.py --json     # 机读，给账和测试用
    python scripts/career_gap_canonical_radius.py --limit 40 # 多列几条会多贴证据的记录

退出码：0 = 正常出表。连不上库或读不出画像时**不吞、不猜数**——异常直接抛出去。

零写入：全程只有 SELECT；`main()` 结束前显式 rollback，测试把 `Session.commit/flush`
换成"一调用就红"来证明这件事。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.agent import AgentStepLog, AgentTask  # noqa: E402
from app.models.history import AnalysisRecord  # noqa: E402
from app.orchestration.protocol import normalize_step_name  # noqa: E402
from app.services.interview_profile_service import get_profile  # noqa: E402
from app.services.skill_gap import canonical_skill, normalize_skill  # noqa: E402

# 与前端 `planningModel.skillMatchKey` 逐字同义：小写 + 去掉分隔符。老记录的缺口与
# 画像弱点都只能按这个键比，别名（k8s / kubernetes）在这一步不会合并。
_SPELLING_NOISE = re.compile(r"[\s_./\\|-]+")


def spelling_key(value) -> str:
    return _SPELLING_NOISE.sub("", str(value or "").lower())


def _as_dict(value) -> dict:
    """递归剥掉 JSON 字符串（兼容 LLM 双重序列化与 DB 驱动差异）。"""
    if isinstance(value, str):
        try:
            return _as_dict(json.loads(value))
        except Exception:
            return {}
    return value if isinstance(value, dict) else {}


def plan_for_task(db: Session, task_id: int) -> dict:
    """与 `api/analysis._load_task_outputs` 同一取法：倒序找 career_planning，或 SummaryAgent 里嵌套的那份。"""
    steps = (
        db.query(AgentStepLog).filter(AgentStepLog.task_id == task_id).order_by(AgentStepLog.step_index.desc()).all()
    )
    for step in steps:
        parsed = _as_dict(step.output_data)
        if normalize_step_name(step.step_name) == "career_planning":
            return parsed
        nested = parsed.get("career_planning")
        if isinstance(nested, dict) and nested:
            return _as_dict(nested)
    return {}


def profile_keys(profile: dict) -> tuple[set[str], set[str]]:
    """画像弱点读成两把尺：canonical（回填后能对上的）与拼写键（今天前端在用的）。"""
    canonicals: set[str] = set()
    spellings: set[str] = set()
    for row in (profile or {}).get("skill_weaknesses") or []:
        if not isinstance(row, dict):
            continue
        canonical = canonical_skill(row.get("canonical")) or canonical_skill(row.get("skill"))
        if canonical:
            canonicals.add(canonical)
        key = spelling_key(row.get("canonical") or row.get("skill"))
        if key:
            spellings.add(key)
    return canonicals, spellings


def _gap_skill(gap) -> str:
    """旧报告里 `skill_gaps` 可能直接是字符串；前端也是这么兜的。"""
    if isinstance(gap, str):
        return gap
    if isinstance(gap, dict) and isinstance(gap.get("skill"), str):
        return gap["skill"]
    return ""


def classify_gap(gap, canonicals: set[str], spellings: set[str]) -> dict:
    skill = _gap_skill(gap)
    if not skill:
        return {"kind": "empty"}
    explicit = gap.get("canonical") if isinstance(gap, dict) else None
    canonical = (canonical_skill(explicit) if isinstance(explicit, str) and explicit else "") or canonical_skill(skill)
    matched_now = spelling_key(explicit or skill) in spellings
    matched_after = canonical in canonicals
    if isinstance(explicit, str) and explicit:
        kind = "canonical_matched" if matched_now else "canonical_no_match"
    elif matched_now:
        kind = "legacy_matched_by_spelling"
    elif matched_after:
        kind = "legacy_would_gain"
    else:
        kind = "legacy_no_match"
    return {
        "kind": kind,
        "skill": skill,
        "canonical": canonical,
        "alias_hit": bool(canonical) and canonical != normalize_skill(skill),
    }


def build_report(db: Session, detail_limit: int) -> dict:
    records = db.query(AnalysisRecord).order_by(AnalysisRecord.id.asc()).all()
    profile_cache: dict[int, tuple[set[str], set[str]]] = {}

    summary = {
        "records_total": len(records),
        "records_deleted": 0,
        "records_without_task": 0,
        "records_without_plan": 0,
        "records_without_gaps": 0,
        "records_with_legacy_gaps": 0,
        "records_that_would_gain": 0,
        "gaps_total": 0,
        "gaps_with_canonical": 0,
        "gaps_legacy": 0,
        "legacy_alias_hits": 0,
        "legacy_would_gain": 0,
        "legacy_matched_by_spelling": 0,
        "legacy_no_match": 0,
        "canonical_matched": 0,
        "canonical_no_match": 0,
        "empty_gaps": 0,
        "users_with_profile": 0,
        "profile_errors": 0,
    }
    detail = []

    for record in records:
        if record.is_deleted:
            summary["records_deleted"] += 1
        task = (
            db.query(AgentTask)
            .filter(AgentTask.analysis_record_id == record.id, AgentTask.user_id == record.user_id)
            .order_by(AgentTask.id.desc())
            .first()
        )
        if not task:
            summary["records_without_task"] += 1
            continue
        plan = plan_for_task(db, task.id)
        if not plan:
            summary["records_without_plan"] += 1
            continue
        gaps = plan.get("skill_gaps")
        if not isinstance(gaps, list) or not gaps:
            summary["records_without_gaps"] += 1
            continue

        user_id = int(record.user_id or 0)
        if user_id not in profile_cache:
            try:
                profile_cache[user_id] = profile_keys(get_profile(db, user_id))
            except Exception as exc:  # 画像读不出来就说出来，不按"没有弱点"蒙混
                summary["profile_errors"] += 1
                print(f"画像读取失败 user={user_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
                profile_cache[user_id] = (set(), set())
        canonicals, spellings = profile_cache[user_id]

        kinds = [classify_gap(gap, canonicals, spellings) for gap in gaps]
        summary["gaps_total"] += len(gaps)
        legacy = [row for row in kinds if row["kind"].startswith("legacy_")]
        canonical_rows = [row for row in kinds if row["kind"].startswith("canonical_")]
        would_gain = [row for row in kinds if row["kind"] == "legacy_would_gain"]
        summary["gaps_legacy"] += len(legacy)
        summary["gaps_with_canonical"] += len(canonical_rows)
        summary["legacy_alias_hits"] += sum(1 for row in legacy if row["alias_hit"])
        summary["legacy_would_gain"] += len(would_gain)
        summary["legacy_matched_by_spelling"] += sum(1 for row in legacy if row["kind"] == "legacy_matched_by_spelling")
        summary["legacy_no_match"] += sum(1 for row in legacy if row["kind"] == "legacy_no_match")
        summary["canonical_matched"] += sum(1 for row in canonical_rows if row["kind"] == "canonical_matched")
        summary["canonical_no_match"] += sum(1 for row in canonical_rows if row["kind"] == "canonical_no_match")
        summary["empty_gaps"] += sum(1 for row in kinds if row["kind"] == "empty")
        if legacy:
            summary["records_with_legacy_gaps"] += 1
        if would_gain:
            summary["records_that_would_gain"] += 1
        detail.append(
            {
                "record_id": record.id,
                "task_id": task.id,
                "user_id": record.user_id,
                "is_deleted": bool(record.is_deleted),
                "gaps": len(gaps),
                "legacy": len(legacy),
                "with_canonical": len(canonical_rows),
                "would_gain": [row["skill"] for row in would_gain],
                "would_gain_canonicals": [row["canonical"] for row in would_gain],
                "alias_hits": [row["skill"] for row in legacy if row["alias_hit"]],
            }
        )

    summary["users_with_profile"] = sum(1 for canonicals, _ in profile_cache.values() if canonicals)
    detail.sort(key=lambda row: (-len(row["would_gain"]), -row["legacy"], row["record_id"]))
    return {"summary": summary, "detail": detail[:detail_limit]}


def print_human(report: dict) -> None:
    s = report["summary"]
    print(f"分析记录：{s['records_total']}（软删 {s['records_deleted']}）")
    print(
        f"  无任务 {s['records_without_task']} · 无规划输出 {s['records_without_plan']} · 无缺口 {s['records_without_gaps']}"
    )
    print(f"  带旧形状缺口（无 canonical）的记录：{s['records_with_legacy_gaps']}")
    print(f"  回填后会多贴出面试证据的记录：{s['records_that_would_gain']}")
    print(f"缺口总数：{s['gaps_total']}（已有 canonical {s['gaps_with_canonical']} / 旧形状 {s['gaps_legacy']}）")
    print(
        f"  旧形状里：别名命中 {s['legacy_alias_hits']} · 回填后能对上画像 {s['legacy_would_gain']} · "
        f"现在按拼写已对上 {s['legacy_matched_by_spelling']} · 都对不上 {s['legacy_no_match']}"
    )
    print(f"  已有 canonical 的缺口：对上画像 {s['canonical_matched']} · 对不上 {s['canonical_no_match']}")
    print(f"画像：有弱点的用户 {s['users_with_profile']} · 读取失败 {s['profile_errors']}")
    print("\n回填后会多贴证据的记录（按会多贴的条数倒序）：")
    if not report["detail"]:
        print("  （没有这样的记录）")
    for row in report["detail"]:
        if not row["would_gain"]:
            continue
        print(
            f"  #{row['record_id']} task={row['task_id']} user={row['user_id']} 删={row['is_deleted']} "
            f"缺口 {row['gaps']}（旧 {row['legacy']}） 会多贴：{row['would_gain']} → {row['would_gain_canonicals']}"
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="完整规划 skill_gaps 的 canonical 存量半径（只读）")
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
