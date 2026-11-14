"""把 `measure_real_chain.py` 的读数归成一句能贴进文档的结论。

为什么单独一个纯函数：量测脚本自己会打真 provider、会等两分钟、会写 JSON，这些都不该被测试碰；
而"这次读数到底能不能用"是纯算术，必须能被 pytest 钉住——2026-11-14 那次实测里，推荐分数看起来
像模像样（57/40/33），实际上 `vector_score` 全是空、分数只来自规则臂，而当时没有任何一处
会因此变红。这一层就是那个"会红"的判据。

判据只用载荷里已有的字段，不读日志文本当主证据（错误串只在"知道是谁欠费"这一步用得上）：

* `match_score_method` / `vector_score` —— 分数是哪条臂算的；
* `analysis_record_id` —— 分析记录有没有真的落库；
* `step_counts` —— 哪一步失败了；
* `prompt_trace.status` / `error_message` —— 谁没成功、为什么。
"""

from __future__ import annotations

from typing import Any

# 这些字样只用来把"欠费/限流"从一般错误里分出来，不用来判断成败
_ARREARAGE_HINTS = ("arrearage", "欠费", "insufficient balance", "quota")
_RATE_LIMIT_HINTS = ("429", "rate limit", "too many requests")

_KIND_LABELS = {
    "embedding_arrearage": "embedding 账号欠费（Arrearage）",
    "provider_arrearage": "模型账号欠费（Arrearage）",
    "rate_limited": "模型侧限流（429）",
}


def _text(value: Any) -> str:
    return str(value or "")


def _dig(source: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(source, dict):
            return None
        source = source.get(key)
    return source


def _classify_error(message: str) -> str | None:
    lowered = _text(message).lower()
    if any(hint in lowered for hint in _ARREARAGE_HINTS):
        return "embedding_arrearage" if "embedding" in lowered else "provider_arrearage"
    if any(hint in lowered for hint in _RATE_LIMIT_HINTS):
        return "rate_limited"
    return None


def classify_run(report: dict) -> dict:
    """入参就是脚本写进 `reports/measure_real_chain.json` 的那一份。"""
    steps = {step.get("step"): step for step in report.get("steps") or []}
    analysis = steps.get("analysis/full") or {}
    timeline = analysis.get("timeline") or []
    final = timeline[-1] if timeline else {}
    counts = report.get("step_counts") or {}

    status = final.get("status") or _dig(analysis, "accept", "payload", "data", "status")

    recs = (steps.get("jobs/recommend") or {}).get("recommendations") or []
    rule_only = [r for r in recs if r.get("vector_score") in (None, 0, "")]
    with_vector = [r for r in recs if r.get("vector_score") not in (None, 0, "")]

    traces = report.get("traces") or []
    failed = [t for t in traces if t.get("status") != "success"]

    blockers: list[str] = []
    if recs and rule_only:
        blockers.append(
            f"{len(rule_only)}/{len(recs)} 条推荐没有向量分（vector_score 为空）——" "分数只来自规则臂，不能当模型效果读"
        )
    kinds = {kind for kind in (_classify_error(t.get("error_message")) for t in failed) if kind}
    for kind in sorted(kinds):
        blockers.append(_KIND_LABELS[kind])

    record_landed = bool(report.get("analysis_record_id"))
    incomplete = report.get("polled_to_terminal") is False
    if incomplete:
        blockers.append(f"后台任务没跟到终态（只跟到 {status or '未知'}）——链路的耗时与落库都没量完")
    return {
        "task_status": status,
        "incomplete": incomplete,
        "steps_total": final.get("total_steps") or counts.get("total"),
        "steps_done": counts.get("completed"),
        "steps_failed": counts.get("failed"),
        "record_landed": record_landed,
        "recommendations": {
            "count": len(recs),
            "with_vector": len(with_vector),
            "rule_only": len(rule_only),
            "methods": sorted({_text(r.get("match_score_method")) for r in recs if r.get("match_score_method")}),
        },
        "trace_mix": {
            "real": sum(1 for t in traces if t.get("response_source") == "real"),
            "fallback_model": sum(1 for t in traces if t.get("response_source") == "fallback_model"),
            "failed": len(failed),
        },
        "blockers": blockers,
        "verdict": _verdict(status=status, record_landed=record_landed, blockers=blockers, incomplete=incomplete),
    }


def _verdict(*, status: str | None, record_landed: bool, blockers: list[str], incomplete: bool) -> str:
    if incomplete:
        chain = "链路没跟到终态，读数不完整"
    elif status in {"failed", "cancelled"} and not record_landed:
        chain = "链路没跑完，也没有产出落库"
    elif record_landed:
        chain = "链路跑通，产出已落库"
    else:
        chain = "链路跑通了但产出没落库"
    quality = "不能用于模型质量结论" if blockers else "可用于模型质量结论（run-to-run 会抖，别当基线）"
    return f"{chain}；{quality}"


def format_verdict(result: dict) -> str:
    """给终端用的一段话：脚本结尾那个 `========== 结论 ==========`。"""
    total = result.get("steps_total") or 0
    done = result.get("steps_done") or 0
    failed = result.get("steps_failed") or 0
    landed = "记录已落库" if result.get("record_landed") else "记录**没**落库"

    rec = result.get("recommendations") or {}
    methods = f" · 方法 {', '.join(rec['methods'])}" if rec.get("methods") else ""
    arms = (
        f"[arms]     {rec.get('count', 0)} 条推荐：{rec.get('with_vector', 0)} 条带向量分 · "
        f"{rec.get('rule_only', 0)} 条只有规则分{methods}"
    )

    mix = result.get("trace_mix") or {}
    traces = (
        f"[traces]   real {mix.get('real', 0)} · fallback {mix.get('fallback_model', 0)} · "
        f"失败 {mix.get('failed', 0)}"
    )

    blockers = result.get("blockers") or []
    blocked = "[blockers] " + "；".join(blockers) if blockers else "[blockers] 无"

    return "\n".join(
        [
            f"[analysis] {result.get('task_status') or '未知'} · {done}/{total} 步（失败 {failed}） · {landed}",
            arms,
            traces,
            blocked,
            f"[verdict]  {result.get('verdict')}",
        ]
    )
