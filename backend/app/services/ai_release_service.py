"""Release gate evaluation for model and prompt changes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings


def evaluate_release_gate(
    report_details: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate selected offline evaluation reports and return immutable evidence."""
    required_types = set(settings.ai_release_required_evaluation_types)
    now = datetime.now(timezone.utc)
    failures: list[str] = []
    checks: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    seen_types: set[str] = set()

    for summary, raw in report_details:
        report_type = str(summary.get("report_type") or "")
        seen_types.add(report_type)
        report_failures = _check_report(summary, raw, now)
        checks.append(
            {
                "report_id": summary["report_id"],
                "report_type": report_type,
                "passed": not report_failures,
                "failures": report_failures,
            }
        )
        failures.extend(f"{summary['report_id']}: {failure}" for failure in report_failures)
        evidence.append(
            {
                "report_id": summary["report_id"],
                "report_type": report_type,
                "generated_at": summary.get("generated_at"),
                "total": summary.get("total"),
                "metrics": summary.get("metrics") or {},
                "thresholds": summary.get("thresholds") or {},
            }
        )

    missing_types = sorted(required_types - seen_types)
    failures.extend(f"缺少必需的 {report_type} 评测报告" for report_type in missing_types)
    return (
        {
            "passed": not failures,
            "required_report_types": sorted(required_types),
            "checked_at": now.isoformat(),
            "checks": checks,
            "failures": failures,
        },
        evidence,
    )


def _check_report(summary: dict[str, Any], raw: dict[str, Any], now: datetime) -> list[str]:
    failures: list[str] = []
    if int(summary.get("total") or 0) <= 0:
        failures.append("评测样本数必须大于 0")

    generated_at = _parse_datetime(summary.get("generated_at"))
    if generated_at is None:
        failures.append("缺少有效的报告生成时间")
    elif generated_at < now - timedelta(days=settings.AI_RELEASE_MAX_EVALUATION_AGE_DAYS):
        failures.append(f"评测报告超过 {settings.AI_RELEASE_MAX_EVALUATION_AGE_DAYS} 天有效期")

    thresholds = summary.get("thresholds") or {}
    configured_thresholds = {key: value for key, value in thresholds.items() if value is not None}
    if not configured_thresholds:
        failures.append("评测报告未声明发布阈值")
        return failures

    report_type = summary.get("report_type")
    if report_type == "rag":
        top_k = raw.get("run_meta", {}).get("top_k") or _infer_top_k(raw)
        actuals = {
            "min_recall": raw.get(f"recall@{top_k}"),
            "min_mrr": raw.get("mrr"),
            "min_keyword_hit": raw.get("keyword_hit_rate"),
        }
        comparisons = {"min_recall": "min", "min_mrr": "min", "min_keyword_hit": "min"}
    elif report_type == "agent":
        actuals = {
            "max_mae": raw.get("mae"),
            "min_spearman": raw.get("spearman_rho"),
            "min_hit_tol10": (raw.get("score_dist") or {}).get("hit_tol10"),
        }
        comparisons = {"max_mae": "max", "min_spearman": "min", "min_hit_tol10": "min"}
    elif report_type == "recommend":
        actuals = {
            "min_skill_match_accuracy": raw.get("skill_match_accuracy"),
            "min_explanation_consistency": raw.get("jd_explanation_consistency"),
            "min_explainability": raw.get("recommendation_explainability"),
            "min_interview_stability": raw.get("interview_score_stability"),
            "min_feedback_agreement_rate": raw.get("feedback_agreement_rate"),
        }
        comparisons = {key: "min" for key in actuals}
    else:
        return ["不支持的评测报告类型"]

    for threshold_name, threshold in configured_thresholds.items():
        actual = actuals.get(threshold_name)
        if threshold_name not in comparisons:
            failures.append(f"未知的发布阈值 {threshold_name}")
        elif actual is None:
            failures.append(f"缺少指标 {threshold_name}")
        elif comparisons[threshold_name] == "min" and float(actual) < float(threshold):
            failures.append(f"{threshold_name}: {actual} < {threshold}")
        elif comparisons[threshold_name] == "max" and float(actual) > float(threshold):
            failures.append(f"{threshold_name}: {actual} > {threshold}")
    return failures


def _infer_top_k(report: dict[str, Any]) -> int | None:
    for key in report:
        if str(key).startswith("recall@"):
            try:
                return int(str(key).split("@", 1)[1])
            except ValueError:
                return None
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
