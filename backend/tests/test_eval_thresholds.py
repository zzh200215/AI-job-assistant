# -*- coding: utf-8 -*-
from scripts.eval_agent import check_thresholds as check_agent_thresholds
from scripts.eval_recommend import check_thresholds as check_recommend_thresholds
from scripts.eval_rag import check_thresholds as check_rag_thresholds


def test_rag_thresholds_pass_when_metrics_meet_floor():
    report = {
        "total": 10,
        "recall@5": 0.9,
        "mrr": 0.86,
        "keyword_hit_rate": 0.8,
    }

    failures = check_rag_thresholds(
        report,
        top_k=5,
        min_recall=0.85,
        min_mrr=0.85,
        min_keyword_hit=0.75,
    )

    assert failures == []


def test_rag_thresholds_report_all_failed_metrics():
    report = {
        "total": 10,
        "recall@5": 0.84,
        "mrr": 0.8,
        "keyword_hit_rate": 0.7,
    }

    failures = check_rag_thresholds(
        report,
        top_k=5,
        min_recall=0.85,
        min_mrr=0.85,
        min_keyword_hit=0.75,
    )

    assert failures == [
        "recall@5 0.84 < 0.85",
        "mrr 0.8 < 0.85",
        "keyword_hit_rate 0.7 < 0.75",
    ]


def test_agent_thresholds_pass_when_metrics_meet_gate():
    report = {
        "total": 10,
        "mae": 10.0,
        "spearman_rho": 0.909,
        "score_dist": {"hit_tol10": 7, "over": 2, "under": 1},
    }

    failures = check_agent_thresholds(
        report,
        max_mae=12.0,
        min_spearman=0.8,
        min_hit_tol10=7,
    )

    assert failures == []


def test_agent_thresholds_report_all_failed_metrics():
    report = {
        "total": 10,
        "mae": 12.1,
        "spearman_rho": 0.79,
        "score_dist": {"hit_tol10": 6, "over": 3, "under": 1},
    }

    failures = check_agent_thresholds(
        report,
        max_mae=12.0,
        min_spearman=0.8,
        min_hit_tol10=7,
    )

    assert failures == [
        "mae 12.1 > 12.0",
        "spearman_rho 0.79 < 0.8",
        "hit_tol10 6 < 7",
    ]


def test_recommend_thresholds_pass_when_metrics_meet_gate():
    report = {
        "total": 6,
        "skill_match_accuracy": 0.91,
        "jd_explanation_consistency": 0.87,
        "recommendation_explainability": 0.83,
        "interview_score_stability": 0.92,
        "feedback_agreement_rate": 0.8,
    }

    failures = check_recommend_thresholds(
        report,
        min_skill_match_accuracy=0.9,
        min_explanation_consistency=0.85,
        min_explainability=0.8,
        min_interview_stability=0.9,
        min_feedback_agreement_rate=0.75,
    )

    assert failures == []


def test_recommend_thresholds_report_all_failed_metrics():
    report = {
        "total": 6,
        "skill_match_accuracy": 0.89,
        "jd_explanation_consistency": 0.84,
        "recommendation_explainability": 0.79,
        "interview_score_stability": 0.88,
        "feedback_agreement_rate": 0.74,
    }

    failures = check_recommend_thresholds(
        report,
        min_skill_match_accuracy=0.9,
        min_explanation_consistency=0.85,
        min_explainability=0.8,
        min_interview_stability=0.9,
        min_feedback_agreement_rate=0.75,
    )

    assert failures == [
        "skill_match_accuracy 0.89 < 0.9",
        "jd_explanation_consistency 0.84 < 0.85",
        "recommendation_explainability 0.79 < 0.8",
        "interview_score_stability 0.88 < 0.9",
        "feedback_agreement_rate 0.74 < 0.75",
    ]
