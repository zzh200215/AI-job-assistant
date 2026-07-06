# -*- coding: utf-8 -*-
"""Recommendation quality evaluation script."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import pstdev
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("eval_recommend")


def load_eval_set(path: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("skip invalid line %d: %s", line_no, exc)
    return items


def _mean(values: Iterable[Optional[float]], digits: int = 3) -> Optional[float]:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return round(sum(filtered) / len(filtered), digits)


def _normalize_terms(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    for value in values:
        text = str(value or "").strip().lower()
        if text:
            result.append(text)
    return result


def _jaccard(left: Iterable[Any], right: Iterable[Any]) -> float:
    left_set = set(_normalize_terms(left))
    right_set = set(_normalize_terms(right))
    if not left_set and not right_set:
        return 1.0
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 1.0


def _keyword_hit_rate(texts: Iterable[str], keywords: Iterable[Any]) -> float:
    normalized_keywords = _normalize_terms(keywords)
    if not normalized_keywords:
        return 1.0
    corpus = " ".join(texts).lower()
    hits = sum(1 for keyword in normalized_keywords if keyword in corpus)
    return hits / len(normalized_keywords)


def _build_resume_stub(profile: Dict[str, Any]) -> SimpleNamespace:
    normalized = dict(profile or {})
    normalized.setdefault("skills", [])
    normalized.setdefault("project_experience", normalized.get("projects", []))
    normalized.setdefault("work_experience", [])
    normalized.setdefault("education", normalized.get("degree", ""))
    normalized.setdefault("years_exp", normalized.get("years_exp", 0))
    return SimpleNamespace(parsed_json=normalized, name=normalized.get("name", "eval_resume"), file_name="eval_resume.json")


def _build_jd_stub(profile: Dict[str, Any]) -> SimpleNamespace:
    normalized = dict(profile or {})
    normalized.setdefault("required_skills", [])
    normalized.setdefault("nice_to_have", [])
    normalized.setdefault("responsibilities", [])
    normalized.setdefault("keywords", [])
    normalized.setdefault("experience_requirement", normalized.get("experience_requirement", ""))
    normalized.setdefault("education_requirement", normalized.get("education_requirement", ""))
    return SimpleNamespace(
        parsed_json=normalized,
        title=normalized.get("title", "eval_jd"),
        company=normalized.get("company", "eval_company"),
        raw_text=normalized.get("raw_text", ""),
        experience_requirement=normalized.get("experience_requirement", ""),
        education_requirement=normalized.get("education_requirement", ""),
    )


def _run_explainer(resume_profile: Dict[str, Any], jd_profile: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.match_explainer_service import MatchExplainer

    explainer = MatchExplainer()
    explainer._llm_explain = lambda dims, _skill_match, overall, _resume, _jd: explainer._fallback_explain(dims, overall)  # type: ignore[attr-defined]
    result = explainer.explain(_build_resume_stub(resume_profile), _build_jd_stub(jd_profile))
    return result.to_dict()


def _structure_score(result: Dict[str, Any]) -> float:
    dimensions = result.get("dimensions") or []
    dimension_reason_count = sum(1 for item in dimensions if str(item.get("reason") or "").strip())
    checks = [
        bool(str(result.get("overall_reason") or "").strip()),
        dimension_reason_count >= max(len(dimensions) - 1, 1),
        bool(result.get("risk_points")),
        bool(result.get("optimization_suggestions")),
    ]
    return sum(1 for item in checks if item) / len(checks)


def _interview_score_stability(scores: Iterable[Any]) -> Optional[float]:
    values = [float(score) for score in scores if score is not None]
    if not values:
        return None
    if len(values) == 1:
        return 1.0
    deviation = pstdev(values)
    return round(max(0.0, 1 - (deviation / 20.0)), 3)


def _recommendation_positive(label: str) -> bool:
    normalized = str(label or "").strip()
    return normalized not in {"不建议投递", "谨慎投递", "不推荐", "hold"}


def _evaluate_case(item: Dict[str, Any]) -> Dict[str, Any]:
    result = _run_explainer(item.get("resume_profile") or {}, item.get("jd_profile") or {})
    predicted_overlap = result.get("skill_match", {}).get("matched") or []
    predicted_missing = result.get("skill_match", {}).get("missing_required") or []
    expected_overlap = item.get("expected_skill_overlap") or []
    expected_missing = item.get("expected_missing_skills") or []
    expected_recommendation = item.get("expected_recommendation")
    reason_keywords = item.get("expected_reason_keywords") or []
    interview_samples = item.get("interview_score_samples") or []

    skill_accuracy = round(_jaccard(predicted_overlap, expected_overlap), 3)
    missing_consistency = round(_jaccard(predicted_missing, expected_missing), 3)
    consistency_parts = []
    if expected_missing or predicted_missing:
        consistency_parts.append(missing_consistency)
    if expected_recommendation:
        consistency_parts.append(1.0 if result.get("recommendation") == expected_recommendation else 0.0)
    jd_explanation_consistency = round(_mean(consistency_parts, digits=3) or 1.0, 3)

    details_text = []
    for dimension in result.get("dimensions") or []:
        details_text.append(str(dimension.get("reason") or ""))
        details_text.extend(str(detail) for detail in (dimension.get("details") or []))
    details_text.extend(str(item) for item in result.get("risk_points") or [])
    details_text.extend(str(item) for item in result.get("optimization_suggestions") or [])
    details_text.append(str(result.get("overall_reason") or ""))
    reason_keyword_hit_rate = round(_keyword_hit_rate(details_text, reason_keywords), 3)
    explainability = round((reason_keyword_hit_rate + _structure_score(result)) / 2.0, 3)

    return {
        "id": item.get("id") or f"case_{item.get('resume_id', 'na')}_{item.get('jd_id', 'na')}",
        "resume_id": item.get("resume_id"),
        "jd_id": item.get("jd_id"),
        "overall_score": result.get("overall_score"),
        "recommendation": result.get("recommendation"),
        "predicted_positive": _recommendation_positive(str(result.get("recommendation") or "")),
        "skill_match_accuracy": skill_accuracy,
        "missing_skill_consistency": missing_consistency,
        "jd_explanation_consistency": jd_explanation_consistency,
        "recommendation_explainability": explainability,
        "reason_keyword_hit_rate": reason_keyword_hit_rate,
        "interview_score_stability": _interview_score_stability(interview_samples),
        "predicted_skill_overlap": predicted_overlap,
        "expected_skill_overlap": expected_overlap,
        "predicted_missing_skills": predicted_missing,
        "expected_missing_skills": expected_missing,
        "expected_recommendation": expected_recommendation,
        "overall_reason": result.get("overall_reason"),
        "risk_points": result.get("risk_points") or [],
        "optimization_suggestions": result.get("optimization_suggestions") or [],
    }


def _build_online_feedback_linkage(eval_set: List[Dict[str, Any]], details: List[Dict[str, Any]], db) -> Dict[str, Any]:
    if db is None:
        return {
            "linked_pair_count": 0,
            "linked_feedback_count": 0,
            "feedback_agreement_rate": None,
            "feedback_summary": {"total_feedback": 0, "like_rate": 0.0, "high_score_dislike_count": 0, "low_score_like_count": 0},
        }

    from app.models.job_recommend import JobRecommendationFeedback

    pairs = {
        (int(item["resume_id"]), int(item["jd_id"]))
        for item in eval_set
        if item.get("resume_id") is not None and item.get("jd_id") is not None
    }
    rows = db.query(JobRecommendationFeedback).all()
    pair_rows: Dict[tuple[int, int], List[JobRecommendationFeedback]] = {}
    total_feedback = 0
    like_count = 0
    high_score_dislike_count = 0
    low_score_like_count = 0
    for row in rows:
        pair = (int(row.resume_id), int(row.jd_id))
        if pair not in pairs:
            continue
        pair_rows.setdefault(pair, []).append(row)
        total_feedback += 1
        if row.feedback_type == "like":
            like_count += 1
            if row.match_score is not None and row.match_score < 60:
                low_score_like_count += 1
        elif row.feedback_type == "dislike" and row.match_score is not None and row.match_score >= 80:
            high_score_dislike_count += 1

    detail_by_pair = {
        (int(detail["resume_id"]), int(detail["jd_id"])): detail
        for detail in details
        if detail.get("resume_id") is not None and detail.get("jd_id") is not None
    }
    linked_pair_count = 0
    agreement_count = 0
    linked_details = []
    for pair, pair_feedback in pair_rows.items():
        detail = detail_by_pair.get(pair)
        if not detail:
            continue
        linked_pair_count += 1
        like_total = sum(1 for row in pair_feedback if row.feedback_type == "like")
        dislike_total = sum(1 for row in pair_feedback if row.feedback_type == "dislike")
        actual_positive = like_total >= dislike_total
        agreed = actual_positive == bool(detail.get("predicted_positive"))
        if agreed:
            agreement_count += 1
        linked_details.append(
            {
                "resume_id": pair[0],
                "jd_id": pair[1],
                "like_count": like_total,
                "dislike_count": dislike_total,
                "predicted_positive": bool(detail.get("predicted_positive")),
                "agreed": agreed,
            }
        )

    return {
        "linked_pair_count": linked_pair_count,
        "linked_feedback_count": total_feedback,
        "feedback_agreement_rate": round(agreement_count / linked_pair_count, 3) if linked_pair_count else None,
        "feedback_summary": {
            "total_feedback": total_feedback,
            "like_rate": round(like_count / total_feedback, 3) if total_feedback else 0.0,
            "high_score_dislike_count": high_score_dislike_count,
            "low_score_like_count": low_score_like_count,
        },
        "linked_details": linked_details,
    }


def run_eval(eval_set: List[Dict[str, Any]], db=None) -> Dict[str, Any]:
    details = [_evaluate_case(item) for item in eval_set]
    linkage = _build_online_feedback_linkage(eval_set, details, db)
    return {
        "total": len(eval_set),
        "skill_match_accuracy": _mean([item["skill_match_accuracy"] for item in details], digits=3) or 0.0,
        "jd_explanation_consistency": _mean([item["jd_explanation_consistency"] for item in details], digits=3) or 0.0,
        "recommendation_explainability": _mean([item["recommendation_explainability"] for item in details], digits=3) or 0.0,
        "interview_score_stability": _mean([item["interview_score_stability"] for item in details], digits=3),
        "feedback_agreement_rate": linkage.get("feedback_agreement_rate"),
        "online_feedback_linkage": linkage,
        "details": details,
    }


def check_thresholds(
    report: Dict[str, Any],
    *,
    min_skill_match_accuracy: Optional[float] = None,
    min_explanation_consistency: Optional[float] = None,
    min_explainability: Optional[float] = None,
    min_interview_stability: Optional[float] = None,
    min_feedback_agreement_rate: Optional[float] = None,
) -> List[str]:
    failed: List[str] = []
    if min_skill_match_accuracy is not None and float(report["skill_match_accuracy"]) < min_skill_match_accuracy:
        failed.append(f"skill_match_accuracy {report['skill_match_accuracy']} < {min_skill_match_accuracy}")
    if min_explanation_consistency is not None and float(report["jd_explanation_consistency"]) < min_explanation_consistency:
        failed.append(f"jd_explanation_consistency {report['jd_explanation_consistency']} < {min_explanation_consistency}")
    if min_explainability is not None and float(report["recommendation_explainability"]) < min_explainability:
        failed.append(f"recommendation_explainability {report['recommendation_explainability']} < {min_explainability}")
    stability = report.get("interview_score_stability")
    if min_interview_stability is not None and stability is not None and float(stability) < min_interview_stability:
        failed.append(f"interview_score_stability {stability} < {min_interview_stability}")
    feedback_agreement = report.get("feedback_agreement_rate")
    if min_feedback_agreement_rate is not None and feedback_agreement is not None and float(feedback_agreement) < min_feedback_agreement_rate:
        failed.append(f"feedback_agreement_rate {feedback_agreement} < {min_feedback_agreement_rate}")
    return failed


def main():
    parser = argparse.ArgumentParser(description="Recommendation quality evaluation")
    parser.add_argument("--eval-set", default=str(_PROJECT_ROOT / "tests" / "eval" / "recommend_eval.jsonl"))
    parser.add_argument("--sample", type=int, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--min-skill-match-accuracy", type=float, default=None)
    parser.add_argument("--min-explanation-consistency", type=float, default=None)
    parser.add_argument("--min-explainability", type=float, default=None)
    parser.add_argument("--min-interview-stability", type=float, default=None)
    parser.add_argument("--min-feedback-agreement-rate", type=float, default=None)
    args = parser.parse_args()

    eval_set = load_eval_set(args.eval_set)
    if args.sample:
        eval_set = eval_set[: args.sample]

    db = None
    try:
        from app.core.database import SessionLocal

        db = SessionLocal()
    except Exception as exc:
        logger.warning("db unavailable, skip online feedback linkage: %s", exc)

    try:
        report = run_eval(eval_set, db=db)
    finally:
        if db is not None:
            db.close()

    report["report_type"] = "recommend"
    report["run_meta"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_set": str(Path(args.eval_set).resolve()),
        "sample": args.sample,
        "thresholds": {
            "min_skill_match_accuracy": args.min_skill_match_accuracy,
            "min_explanation_consistency": args.min_explanation_consistency,
            "min_explainability": args.min_explainability,
            "min_interview_stability": args.min_interview_stability,
            "min_feedback_agreement_rate": args.min_feedback_agreement_rate,
        },
    }

    print("\n" + "=" * 50)
    print(f"Recommendation eval report (total {report['total']})")
    print("=" * 50)
    print(f"  skill_match_accuracy           : {report['skill_match_accuracy']}")
    print(f"  jd_explanation_consistency     : {report['jd_explanation_consistency']}")
    print(f"  recommendation_explainability  : {report['recommendation_explainability']}")
    print(f"  interview_score_stability      : {report['interview_score_stability']}")
    print(f"  feedback_agreement_rate        : {report['feedback_agreement_rate']}")
    print("=" * 50)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("report written to %s", out_path)

    failed = check_thresholds(
        report,
        min_skill_match_accuracy=args.min_skill_match_accuracy,
        min_explanation_consistency=args.min_explanation_consistency,
        min_explainability=args.min_explainability,
        min_interview_stability=args.min_interview_stability,
        min_feedback_agreement_rate=args.min_feedback_agreement_rate,
    )
    if failed:
        print("[FAIL] Recommendation eval thresholds not met:")
        for item in failed:
            print(f"  - {item}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
