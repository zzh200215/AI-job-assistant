"""P3.2 追问质量样本的共用提取逻辑。"""

from __future__ import annotations

from typing import Any

TIERS = ("good", "mid", "weak")


def extract_followups(report: dict[str, Any], *, with_source: bool = False) -> dict[tuple[str, int], str]:
    """从动态评测报告里按 (档位, 题号) 提取追问；同题多次追问用 ` / ` 拼接。

    `with_source=True` 时给每条追问标来源：`（LLM）` 是模型现场组织，
    `（模板/降级）` 是启发式或降级句。填质量表必须带这个标记，否则模板句会被
    当成模型质量打分（2026-10-25 第八发：12 条追问里只有 3 条 LLM）。
    """
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
            if with_source:
                decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
                composed = decision.get("source") == "llm" and not decision.get("degraded")
                text = f"{text}（{'LLM' if composed else '模板/降级'}）"
            key = (str(tier), round_no)
            previous = result.get(key)
            result[key] = f"{previous} / {text}" if previous else text
    return result
