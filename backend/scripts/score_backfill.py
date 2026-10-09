#!/usr/bin/env python3
"""把历史匹配分回算成唯一权威的那个数——**默认一个字都不写**。

半径已经由 `score_backfill_radius.py` 量完（2026-10-09 现量：70 行全在半径内、68 行候选人还看得见、
重算 42.3 ms 零 provider 调用）。这个脚本是那半条"写"的路径，形态按 §10.38 的 ③：

* **重算**：走 `compute_canonical_score` → `MatchExplainer.compute_rubric`，没有 LLM、没有 embedding。
* **保留原值**：候选人当时看到的那个数落到 `match_report["displayed_before_backfill"]`，模型自报数
  （这行本来有的话）留在 `model_reported_score`，然后才盖权威标记。回算不是把历史抹平，
  是让历史自己说清它是哪来的。
* **写要点名**：默认 dry-run；`--apply` 才写，而且必须同时给 `--backup PATH`——先把改动行的
  before-image 整份写到那个文件，写库发生在备份落盘之后。
* **不覆盖并发的写**：每一行都是 `WHERE id=? AND match_score=旧值` 的条件更新，rowcount 0 就跳过
  （这行在我们读它之后被人改过，比如候选人刚跑了一场新分析）。

用法：
    python scripts/score_backfill.py                 # dry-run，看会改什么
    python scripts/score_backfill.py --json          # 机读
    python scripts/score_backfill.py --apply --backup ../out/score-before-image.json

退出码：0 = 正常出表/正常写完；其余 = 连不上库或参数不合规，异常直接抛出去，不猜数、不静默跳过。

**这一条欠的**：③ 里"历史页读得到'当时显示 85、现按权威重算为 16'"那一半**没做**——数据侧留了
`displayed_before_backfill`，界面上还没有任何读者。要么下一次一并把 `History.vue` 那格补上，要么
就承认这个键暂时只是审计用的。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.history import AnalysisRecord, JobDescription, Resume  # noqa: E402
from app.services.match_score_service import compute_canonical_score  # noqa: E402
from app.utils.time_helper import utc_now  # noqa: E402

# 判据只有一份：半径脚本认哪一种行是旧的，这里就只回算那一种。两处各写一遍迟早会分叉。
from scripts.score_backfill_radius import authority_marker  # noqa: E402

BACKFILL_KEYS = ("displayed_before_backfill", "score_method", "cap_applied", "skill_gap", "backfilled_at")


def plan_rows(db: Session) -> list[dict]:
    """扫全表，产出"这行会被怎么改"的计划。不写任何东西。"""
    rows = db.query(AnalysisRecord).order_by(AnalysisRecord.id.asc()).all()
    plan: list[dict] = []
    for row in rows:
        if authority_marker(row):
            plan.append({"record_id": row.id, "action": "skip_marked"})
            continue
        resume, jd = db.get(Resume, row.resume_id), db.get(JobDescription, row.jd_id)
        if resume is None or jd is None:
            plan.append({"record_id": row.id, "action": "skip_unreachable"})
            continue
        canonical = compute_canonical_score(resume, jd)
        authoritative = int(round(float(canonical.get("score", 0.0))))
        stored = int(row.match_score or 0)
        report = dict(row.match_report) if isinstance(row.match_report, dict) else {}
        if authoritative == stored:
            # 值本来就对，只是没盖标记。这里不写：为一个候选人看不见的差别去动一行数据不值得，
            # 而"同一个数恰好相等"也不等于"同一个方法算出来的"。
            plan.append({"record_id": row.id, "action": "skip_equal", "stored": stored})
            continue
        new_report = {
            **report,
            "displayed_before_backfill": stored,
            "model_reported_score": report.get("model_reported_score", stored),
            "score_method": canonical.get("method"),
            "cap_applied": bool(canonical.get("cap_applied")),
            "skill_gap": canonical.get("skill_gap") or [],
            "backfilled_at": utc_now().isoformat(timespec="seconds"),
        }
        plan.append(
            {
                "record_id": row.id,
                "action": "rewrite",
                "user_id": row.user_id,
                "resume_id": row.resume_id,
                "jd_id": row.jd_id,
                "stored": stored,
                "authoritative": authoritative,
                "delta": authoritative - stored,
                "is_deleted": bool(row.is_deleted),
                "report": new_report,
            }
        )
    return plan


def summarize(plan: list[dict]) -> dict:
    counts = {"skip_marked": 0, "skip_unreachable": 0, "skip_equal": 0, "rewrite": 0, "rewrite_visible": 0}
    deltas = []
    for item in plan:
        counts[item["action"]] += 1
        if item["action"] == "rewrite":
            deltas.append(item["delta"])
            if not item["is_deleted"]:
                counts["rewrite_visible"] += 1
    return {
        "total": len(plan),
        **counts,
        "delta_min": min(deltas) if deltas else None,
        "delta_max": max(deltas) if deltas else None,
    }


def before_image(db: Session, plan: list[dict]) -> list[dict]:
    """改动行的旧样子：旧分数 + 整份旧 `match_report`，够逐行还原。"""
    image = []
    for item in plan:
        if item["action"] != "rewrite":
            continue
        row = db.get(AnalysisRecord, item["record_id"])
        image.append({"record_id": row.id, "match_score": row.match_score, "match_report": row.match_report})
    return image


def write_backup(path: Path, before: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8", newline="")


def apply_plan(db: Session, plan: list[dict]) -> tuple[int, int]:
    """逐行条件更新，返回 (写入行数, 被并发抢改而跳过的行数)。"""
    written, raced = 0, 0
    for item in plan:
        if item["action"] != "rewrite":
            continue
        won = (
            db.query(AnalysisRecord)
            .filter(AnalysisRecord.id == item["record_id"], AnalysisRecord.match_score == item["stored"])
            .update(
                {AnalysisRecord.match_score: item["authoritative"], AnalysisRecord.match_report: item["report"]},
                synchronize_session=False,
            )
        )
        if won == 1:
            written += 1
        else:
            raced += 1
    return written, raced


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="历史匹配分回算（默认 dry-run）")
    ap.add_argument("--apply", action="store_true", help="真的写库（必须同时给 --backup）")
    ap.add_argument("--backup", type=Path, default=None, help="写库前的 before-image 落地路径")
    ap.add_argument("--json", action="store_true", help="输出机读 JSON")
    args = ap.parse_args(argv)

    if args.apply and args.backup is None:
        # 不是礼貌提醒：没有 before-image 就没有回退路径，这条直接拒绝执行。
        raise SystemExit("--apply 必须带 --backup：不动候选人的数，除非能还原")

    db = SessionLocal()
    try:
        plan = plan_rows(db)
        summary = summarize(plan)
        written = skipped = 0
        if args.apply:
            write_backup(args.backup, before_image(db, plan))  # 备份在前：这一句炸了就不能已经写了一半
            written, skipped = apply_plan(db, plan)
            db.commit()
    finally:
        db.rollback()
        db.close()

    if args.json:
        payload = {
            "mode": "apply" if args.apply else "dry-run",
            "summary": summary,
            "written": written,
            "skipped_concurrent": skipped,
        }
        if not args.apply:
            payload["plan"] = plan
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human(summary, applied=written, skipped=skipped, applying=args.apply)
    return 0


def print_human(summary: dict, *, applied: int, skipped: int, applying: bool) -> None:
    print(f"分析记录总数：{summary['total']}")
    print(f"  已走权威（带标记，跳过）：{summary['skip_marked']}")
    print(f"  简历/岗位不可达（跳过）：{summary['skip_unreachable']}")
    print(f"  值本来就等于权威（跳过，且不盖标记）：{summary['skip_equal']}")
    print(f"  要改：{summary['rewrite']}（其中候选人还看得见 {summary['rewrite_visible']}）")
    if summary["rewrite"]:
        print(f"  Δ 区间（权威分 − 存分）：{summary['delta_min']} … {summary['delta_max']}")
    if applying:
        print(f"  实际写入：{applied}；读后被并发抢改、已跳过：{skipped}")
    else:
        print("  （dry-run：一行都没写。要写请 --apply 并带 --backup）")


if __name__ == "__main__":
    raise SystemExit(main())
