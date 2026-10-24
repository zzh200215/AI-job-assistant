"""P3.2 追问质量样本的共用提取逻辑。"""

from __future__ import annotations

from typing import Any

TIERS = ("good", "mid", "weak")


def extract_followups(report: dict[str, Any]) -> dict[tuple[str, int], str]:
    """从动态评测报告里按 (档位, 题号) 提取追问；同题多次追问用 ` / ` 拼接。"""
    result: dict[tuple[str, int], str] = {}
    for tier, arms in (report.get("runs") or {}).items():
        dynamic = (arms or {}).get("dynamic") or {}
        for item in dynamic.get("transcript") or []:
            if not item.get("is_follow_up"):
                continue
            round_no = int(item.get("round") or 0)
            text = str(item.get("content") or "").strip()
            if not round_no or not text:
                continue
            key = (str(tier), round_no)
            previous = result.get(key)
            result[key] = f"{previous} / {text}" if previous else text
    return result
