#!/usr/bin/env python
"""Generate the P3.2 follow-up quality sampling sheet (Markdown)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.interview_quality import extract_followups
except ModuleNotFoundError:  # 直接 `python scripts/...` 时脚本目录在 sys.path 上
    from interview_quality import extract_followups

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "eval" / "interview_dynamic_cases.json"
OUTPUT = ROOT / "tests" / "eval" / "interview_quality_sample.md"
TIERS = ("good", "mid", "weak")


def render(cases: dict, followups: dict[tuple[str, int], str] | None = None) -> str:
    questions = cases["questions"]
    lines = [
        "# P3.2 追问质量抽样表",
        "",
        "生成自 `tests/eval/interview_dynamic_cases.json`。跑完一发呆 provider 后，把动态臂的追问文本粘进“追问”列；"
        "没有触发追问的格子留空。",
        "",
        "评分 1–5：**针对性** = 是否对准回答里的弱点；**具体性** = 是否问出可验证的细节；"
        "**多样性** = 同一档内是否在重复同一句。三列都按单条追问打，不做跨档比较。",
        "",
        "追问后标 **（LLM）** = 模型现场组织；标 **（模板/降级）** = 启发式或降级句。质量分只按单条打。",
        "",
        "| 档位 | 题号 | 题型 | 题目 | 追问（跑完粘贴） | 针对性 | 具体性 | 多样性 | 备注 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for tier in TIERS:
        for index, question in enumerate(questions, start=1):
            followup = (followups or {}).get((tier, index), "")
            lines.append(
                f"| {tier} | {index} | {question['category']} | {question['question']} | " f"{followup} |  |  |  |  |"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check the P3.2 quality sampling sheet")
    parser.add_argument("--check", action="store_true", help="Fail when the checked-in sheet is stale")
    parser.add_argument("--report", default=None, help="从动态评测报告预填追问")
    parser.add_argument("--output", default=None, help="写出的文件（默认空白模板或 *_filled.md）")
    args = parser.parse_args(argv)
    if args.check and (args.report or args.output):
        parser.error("--check 只检查默认的空白模板，不能和 --report/--output 一起用")

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.report:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        followups = extract_followups(report, with_source=True)
        target = Path(args.output) if args.output else OUTPUT.with_name("interview_quality_sample_filled.md")
    else:
        followups = None
        target = Path(args.output) if args.output else OUTPUT
    content = render(cases, followups)
    if args.check:
        if not OUTPUT.exists():
            print(f"[STALE] missing {OUTPUT}")
            return 2
        if OUTPUT.read_text(encoding="utf-8") != content:
            print("[STALE] sheet differs from cases; run without --check")
            return 2
        print(f"[OK] {OUTPUT.name}: {len(cases['questions']) * len(TIERS)} rows")
        return 0
    target.write_text(content, encoding="utf-8", newline="\n")
    print(f"[OK] wrote {target} ({len(cases['questions']) * len(TIERS)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
