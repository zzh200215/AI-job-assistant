from scripts.eval_agent import check_thresholds as check_agent_thresholds
from scripts.eval_rag import check_thresholds as check_rag_thresholds
from scripts.eval_rag import run_eval as run_rag_eval
from scripts.eval_recommend import check_thresholds as check_recommend_thresholds


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


def test_rag_eval_uses_hybrid_recall(monkeypatch):
    calls = []

    def fake_multi_recall(query, db=None, user_id=None, top_k=None):
        calls.append((query, db, user_id, top_k))
        return [{"doc_type": "resume_template", "text": "Python backend resume"}]

    monkeypatch.setattr("app.services.multi_recall.multi_recall", fake_multi_recall)

    session = object()  # 会话必须是真传进去的：multi_recall 无 db 会 fail-closed 返回空
    report = run_rag_eval(
        [
            {
                "query": "Python resume",
                "expected_doc_types": ["resume_template"],
                "expected_keywords": ["Python"],
            }
        ],
        top_k=5,
        db=session,
        user_id=7,
    )

    assert calls == [("Python resume", session, 7, 5)]
    assert report["recall@5"] == 1.0
    assert report["keyword_hit_rate"] == 1.0


# ===== 检索异常 vs 召回为 0：两者以前在报告里长得一样 =====

_EVAL_TWO = [
    {"query": "q1", "expected_doc_types": ["resume_template"], "expected_keywords": ["Python"]},
    {"query": "q2", "expected_doc_types": ["salary_benchmark"], "expected_keywords": ["薪资"]},
]


def test_retrieval_exceptions_are_counted_separately_and_zero_the_metrics(monkeypatch):
    def boom(query, db=None, user_id=None, top_k=None):
        raise RuntimeError("连接被拒绝")

    monkeypatch.setattr("app.services.multi_recall.multi_recall", boom)

    report = run_rag_eval(_EVAL_TWO, top_k=5, db=object())

    assert report["total"] == 2
    assert report["retrieved"] == 0
    assert report["retrieval_errors"] == 2
    assert report["empty_results"] == 0
    # 没测出来就是 None，不能写成 0.0 冒充"测了，很差"
    assert report["recall@5"] is None
    assert report["mrr"] is None
    assert report["keyword_hit_rate"] is None
    # 样本要能指认是哪条 query 因为什么炸
    assert len(report["error_samples"]) == 2
    assert report["error_samples"][0].startswith("q1: RuntimeError")
    assert [d["error"] is not None for d in report["details"]] == [True, True]


def test_empty_retrieval_is_still_a_measured_zero(monkeypatch):
    monkeypatch.setattr("app.services.multi_recall.multi_recall", lambda query, **kwargs: [])

    report = run_rag_eval(_EVAL_TWO, top_k=5, db=object())

    assert report["retrieval_errors"] == 0
    assert report["empty_results"] == 2
    assert report["retrieved"] == 2
    assert report["recall@5"] == 0.0  # 真的测了：什么都没召回


def test_only_the_errored_queries_leave_the_average(monkeypatch):
    """一条炸一条中：指标只按测出来的那条算，而不是把异常当成 0 分压平均。"""

    def flaky(query, db=None, user_id=None, top_k=None):
        if query == "q1":
            raise RuntimeError("偶发")
        return [{"doc_type": "salary_benchmark", "text": "薪资分位数据"}]

    monkeypatch.setattr("app.services.multi_recall.multi_recall", flaky)

    report = run_rag_eval(_EVAL_TWO, top_k=5, db=object())

    assert (report["retrieved"], report["retrieval_errors"]) == (1, 1)
    assert report["recall@5"] == 1.0
    assert report["details"][0]["recall"] is None
    assert report["details"][1]["recall"] == 1.0


def test_gate_reports_retrieval_errors_before_talking_about_thresholds():
    report = {
        "total": 2,
        "retrieved": 0,
        "retrieval_errors": 2,
        "error_samples": ["q1: RuntimeError: 连接被拒绝", "q2: RuntimeError: 连接被拒绝"],
        "recall@5": None,
        "mrr": None,
        "keyword_hit_rate": None,
    }

    failures = check_rag_thresholds(report, top_k=5, min_recall=0.5)

    assert failures[0].startswith("retrieval_errors 2 > 0")
    assert "连接被拒绝" in failures[0]
    assert failures[1] == "recall@5 未测出（没有一条 query 拿到可用检索结果），门槛 0.5 无从比较"

    # 显式允许异常时，仍然要说"未测出"，不能因为跳过就变成通过
    only_missing = check_rag_thresholds(report, top_k=5, min_recall=0.5, max_retrieval_errors=None)
    assert only_missing == [failures[1]]


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
