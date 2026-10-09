#!/usr/bin/env python3
"""历史匹配分的**回算半径**报告——只读，一条都不写。

为什么先要这张表：A4 定了匹配分的唯一权威（`canonical_match_score`），而两条落库路径是**分别**接上它的：

* `app/services/match_service.py:99`（`POST /analysis/match`）在 `e1054c9`（2026-09-19）接上；
* `app/orchestration/strategies.py:260`（"一键智能分析"走的编排路径）在 `1d4e16a`（2026-09-20）接上，
  并把模型自报数降级成 `match_report["model_reported_score"]`。

于是"代码里接上了"和"库里已有的行"是两件事：本地库 70 行的 `create_time` 全落在 2026-06，
即两次接线**之前**，它们带的是模型自报的数。所以"要不要回算"在没有这张表之前无法回答——
affected 行数、分差分布、以及"其中多少候选人还会在界面上看到"都得先量。回算本身（写路径）不在这里，
那要单独拍板。

用法：
    python scripts/score_backfill_radius.py            # 人读的汇总表
    python scripts/score_backfill_radius.py --json      # 机读，给账和测试用
    python scripts/score_backfill_radius.py --limit 40  # 多列几条分差最大的行

退出码：0 = 正常出表。连不上库、或模型返回读不出来时**不吞、不猜数**——异常直接抛出去（非 0 退出）。

代价说明：重算走的是 `compute_canonical_score` → `MatchExplainer.compute_rubric`，
那条路径**没有 LLM、没有 embedding**（`match_explainer_service.py:110` 的 docstring 就是这句），
所以这个半径报告的花费是纯 CPU + 读库，与 provider 无关。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.history import AnalysisRecord, JobDescription, Resume  # noqa: E402
from app.services.match_score_service import compute_canonical_score  # noqa: E402

# `1d4e16a` 的提交日期，只用来做**交叉核对**：真正的判据是行里有没有落库路径自己盖的权威标记
# （见下面 `AUTHORITY_MARKER_KEYS`），日期只是"这条行是不是在修复之后才生成"的旁证。
AUTHORITY_LANDED_AT = datetime(2026, 9, 20)


# 权威标记的键名。**D166 之前两条落库路径拼法不一样**：
#   · `app/orchestration/strategies.py:262` 一直写 `score_method`
#   · `app/services/match_service.py:103` 曾写 `match_score_method`（2026-10-09 已对齐成前者）
# 旧键已经落在历史行里，所以判据**继续认两种**——只认新的那一种会把已有行当成没人管过的旧形状
# 重算一遍（值相同、Δ0，看不出错，只有半径虚高）。新写入只许一种，由
# `test_match_score_single_source.test_only_one_spelling_of_the_authority_marker_is_written` 钉住。
AUTHORITY_MARKER_KEYS = ("score_method", "match_score_method")


def authority_marker(row: AnalysisRecord) -> str | None:
    report = row.match_report if isinstance(row.match_report, dict) else {}
    for key in AUTHORITY_MARKER_KEYS:
        method = report.get(key)
        if isinstance(method, str) and method:
            return method
    return None


def _model_reported(row: AnalysisRecord) -> int | None:
    report = row.match_report if isinstance(row.match_report, dict) else {}
    value = report.get("model_reported_score")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(round(value))


def _bucket(delta: int) -> str:
    a = abs(delta)
    if a == 0:
        return "equal"
    if a <= 5:
        return "le5"
    if a <= 15:
        return "le15"
    return "gt15"


def build_report(db: Session, detail_limit: int) -> dict:
    rows = db.query(AnalysisRecord).order_by(AnalysisRecord.id.asc()).all()
    resume_cache: dict[int, Resume | None] = {}
    jd_cache: dict[int, JobDescription | None] = {}

    def get_resume(rid):
        if rid not in resume_cache:
            resume_cache[rid] = db.get(Resume, rid)
        return resume_cache[rid]

    def get_jd(jid):
        if jid not in jd_cache:
            jd_cache[jid] = db.get(JobDescription, jid)
        return jd_cache[jid]

    summary = {
        "total": len(rows),
        "with_authority_marker": 0,
        "without_authority_marker": 0,
        "without_and_created_after_fix": 0,
        "recomputable": 0,
        "not_recomputable": 0,
        "not_recomputable_reasons": {},
        "buckets": {"equal": 0, "le5": 0, "le15": 0, "gt15": 0},
        "deltas": [],
        "visible_without_marker": 0,
    }
    detail = []

    for row in rows:
        if authority_marker(row):
            summary["with_authority_marker"] += 1
            continue
        summary["without_authority_marker"] += 1
        created = getattr(row, "create_time", None)
        if isinstance(created, datetime) and created >= AUTHORITY_LANDED_AT:
            summary["without_and_created_after_fix"] += 1
        # "候选人还会不会看到"：没软删、且这行本身有分数
        if not row.is_deleted and row.match_score is not None:
            summary["visible_without_marker"] += 1

        resume, jd = get_resume(row.resume_id), get_jd(row.jd_id)
        if resume is None or jd is None:
            reason = "简历已不可见" if resume is None else "岗位已不可见"
            summary["not_recomputable"] += 1
            summary["not_recomputable_reasons"][reason] = summary["not_recomputable_reasons"].get(reason, 0) + 1
            continue
        try:
            canonical = compute_canonical_score(resume, jd)
        except Exception as exc:  # 不猜数：算不出来就单独报出来
            summary["not_recomputable"] += 1
            key = f"重算抛异常：{type(exc).__name__}"
            summary["not_recomputable_reasons"][key] = summary["not_recomputable_reasons"].get(key, 0) + 1
            continue

        summary["recomputable"] += 1
        authoritative = int(round(float(canonical.get("score", 0.0))))
        stored = int(row.match_score or 0)
        delta = authoritative - stored
        summary["buckets"][_bucket(delta)] += 1
        summary["deltas"].append(abs(delta))
        # 明细**全部**收下来，最后按 |delta| 倒序截断。边扫边截是错的：那样留下的是
        # 最早的那 limit 条，而这张表的用途是"先看最离谱的那几条"（见 print_human 的标题）。
        # 半径本身只有几十行，多留几个字典不是代价。
        detail.append(
            {
                "record_id": row.id,
                "user_id": row.user_id,
                "resume_id": row.resume_id,
                "jd_id": row.jd_id,
                "create_time": created.isoformat(sep=" ", timespec="seconds") if created else None,
                "stored": stored,
                "model_reported": _model_reported(row),
                "authoritative": authoritative,
                "delta": delta,
                "method": canonical.get("method"),
                "cap_applied": bool(canonical.get("cap_applied")),
                "is_deleted": bool(row.is_deleted),
                "remark": (row.remark or "")[:40],
            }
        )

    deltas = summary["deltas"]
    summary["delta_stats"] = {
        "n": len(deltas),
        "max": max(deltas) if deltas else None,
        "mean": round(statistics.fmean(deltas), 2) if deltas else None,
        "median": statistics.median(deltas) if deltas else None,
        "p90": sorted(deltas)[int(len(deltas) * 0.9)] if deltas else None,
    }
    detail.sort(key=lambda d: -abs(d["delta"]))
    return {"summary": summary, "detail": detail[:detail_limit]}


def print_human(report: dict) -> None:
    s = report["summary"]
    print(f"分析记录总数：{s['total']}")
    print(f"  带权威标记（score_method / match_score_method，已走权威）：{s['with_authority_marker']}")
    print(f"  不带权威标记（旧形状）：{s['without_authority_marker']}")
    print(
        f"    其中 create_time 晚于 {AUTHORITY_LANDED_AT.date()}（= 修复之后仍在往里长的）："
        f"{s['without_and_created_after_fix']}"
    )
    print(f"    未软删且自己有分数（回算会改到候选人可见的数）：{s['visible_without_marker']}")
    print(f"  可重算：{s['recomputable']} | 不可重算：{s['not_recomputable']} {s['not_recomputable_reasons'] or ''}")
    st = s["delta_stats"]
    if st["n"]:
        print(f"  |权威分 − 存分| 分布：max {st['max']} / 均值 {st['mean']} / 中位 {st['median']} / p90 {st['p90']}")
        b = s["buckets"]
        print(f"  分差分桶：相等 {b['equal']} · ≤5 {b['le5']} · 6–15 {b['le15']} · >15 {b['gt15']}")
    print("\n分差最大的记录（delta = 权威分 − 存分）：")
    if not report["detail"]:
        print("  （没有可重算的旧形状记录）")
    for d in report["detail"]:
        print(
            f"  #{d['record_id']} user={d['user_id']} resume={d['resume_id']} jd={d['jd_id']} "
            f"存 {d['stored']} → 权威 {d['authoritative']}（Δ{d['delta']:+d}） "
            f"自报 {d['model_reported']} {d['create_time']} 删={d['is_deleted']} 备注={d['remark']!r}"
        )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="历史匹配分回算半径（只读）")
    ap.add_argument("--json", action="store_true", help="输出机读 JSON")
    ap.add_argument("--limit", type=int, default=15, help="明细最多列几条（默认 15）")
    args = ap.parse_args(argv)

    db = SessionLocal()
    try:
        report = build_report(db, args.limit)
    finally:
        # 这条 rollback 不是装饰：这个脚本的"只读"要能被测试证伪（见
        # tests/test_score_backfill_radius.py 里那条"任何 commit 都直接红"）。
        db.rollback()
        db.close()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
