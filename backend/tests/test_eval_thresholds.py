from scripts.eval_agent import check_thresholds as check_agent_thresholds
from scripts.eval_agent import run_eval as run_agent_eval
from scripts.eval_rag import check_thresholds as check_rag_thresholds
from scripts.eval_rag import random_metric_baselines, run_lexical_eval
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


# ===== eval_agent：没跑出预测分 ≠ 模型给了 0 分 =====


def _agent_pair(pid: str, expected: int) -> dict:
    return {
        "id": pid,
        "resume_profile": {"skills": ["Python"]},
        "jd_profile": {"required_skills": ["Python"]},
        "expected_match_score": expected,
    }


def test_agent_eval_keeps_unscored_pairs_out_of_the_metrics(monkeypatch):
    def timeout_chat_json(*args, **kwargs):
        raise RuntimeError("provider 超时")

    monkeypatch.setattr("app.services.llm_service.chat_json", timeout_chat_json)

    report = run_agent_eval([_agent_pair("p1", 60), _agent_pair("p2", 70)])

    assert report["total"] == 2
    assert report["scored"] == 0
    assert report["eval_errors"] == 2
    # 以前这里会是 mae≈65、hit_tol10=0 —— 看着像模型很差，其实是两条都没测出来
    assert report["mae"] is None
    assert report["spearman_rho"] is None
    assert [d["label"] for d in report["details"]] == ["errored", "errored"]
    assert report["score_dist"]["errored"] == 2
    assert report["error_samples"][0].startswith("p1: RuntimeError")


def test_agent_eval_measures_only_the_pairs_that_returned_a_score(monkeypatch):
    monkeypatch.setattr("app.services.match_score_calibration.apply_match_score_cap", lambda *args, **kwargs: None)

    calls: list[int] = []

    def flaky_chat_json(prompt, **kwargs):
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("解析失败")
        return {"match_score": 70}

    monkeypatch.setattr("app.services.llm_service.chat_json", flaky_chat_json)

    report = run_agent_eval([_agent_pair("p1", 60), _agent_pair("p2", 70)])

    # p1 没跑出来就不能记成 0 分：那样 mae 会变成 30，看着像模型差，其实是解析失败
    assert (report["scored"], report["eval_errors"]) == (1, 1)
    assert report["mae"] == 0.0
    assert report["spearman_rho"] is None  # 只剩一个点，秩相关无从谈起
    assert report["details"][0]["label"] == "errored"
    assert report["details"][1]["label"] == "hit"


def test_agent_gate_reports_unscored_pairs_before_thresholds():
    report = {
        "total": 2,
        "scored": 0,
        "eval_errors": 2,
        "error_samples": ["p1: RuntimeError: provider 超时"],
        "mae": None,
        "spearman_rho": None,
        "score_dist": {"hit_tol10": 0, "over": 0, "under": 0, "errored": 2},
    }

    failures = check_agent_thresholds(report, max_mae=12.0, min_spearman=0.8)

    assert failures[0].startswith("eval_errors 2 > 0")
    assert failures[1] == "mae 未测出（跑出预测分的 pair 只有 0 条，至少 1 条）门槛 12.0 无从比较"
    assert failures[2] == "spearman_rho 未测出（跑出预测分的 pair 只有 0 条，至少 2 条）门槛 0.8 无从比较"

    # 显式允许时，仍然不能因为"跳过"就变成通过
    without_gate = check_agent_thresholds(report, max_mae=12.0, min_spearman=0.8, max_errors=None)
    assert without_gate == failures[1:]


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


# ===== 词法那一路：CI（mock 向量，无语义）里唯一能门住语义的数 =====


class _FakeCollection:
    """最小可用的 Chroma collection：只支持 eval 用到的 get()。"""

    def __init__(self, rows):
        # rows: (chunk_id, doc_id, doc_type, text)
        self.rows = rows

    def get(self, ids=None, include=None):
        picked = [r for r in self.rows if ids is None or r[0] in ids]
        return {
            "ids": [r[0] for r in picked],
            "metadatas": [{"doc_id": r[1], "doc_type": r[2]} for r in picked],
            "documents": [r[3] for r in picked],
        }


class _FakeIndex:
    def __init__(self, corpus_count, build_failed=False):
        self._corpus_count = corpus_count
        self.build_failed = build_failed

    @classmethod
    def get(cls):
        return _FakeIndex(4)


_ROWS = [
    ("c1", "11", "resume_template", "Python 后端简历模板"),
    ("c2", "11", "resume_template", "项目经验写法"),
    ("c3", "22", "salary_market", "薪资分位数据"),
    ("c4", "99", "jd_lib", "别人的岗位文档"),
]

_LEX_EVAL = [{"query": "Python 简历", "expected_doc_types": ["resume_template"], "expected_keywords": ["Python"]}]
_VISIBLE = frozenset({"11", "22"})


def _patch_lexical(monkeypatch, bm25_result, rows=None, visible=_VISIBLE):
    """把词法那一路的外部依赖换成假的：BM25 打分、索引元信息、Chroma 取文、可见集合。

    `visible=None` 表示管理员语义（全量可见，不做裁剪）。
    """
    rows = _ROWS if rows is None else rows
    monkeypatch.setattr("app.services.multi_recall._bm25_score", lambda query, **kwargs: list(bm25_result))
    monkeypatch.setattr("app.services.multi_recall._BM25Index", _FakeIndex)
    collection = _FakeCollection(rows)
    monkeypatch.setattr("app.core.chroma_client.get_knowledge_collection", lambda: collection)
    monkeypatch.setattr(
        "app.utils.knowledge_access.get_visible_knowledge_doc_ids",
        lambda db, **kwargs: set(visible) if visible is not None else None,
    )
    return collection


def test_lexical_eval_measures_only_the_bm25_path(monkeypatch):
    _patch_lexical(monkeypatch, [("c3", 9.0), ("c1", 5.0), ("c2", 1.0)])

    report = run_lexical_eval(_LEX_EVAL, db=object(), user_id=7, top_k=5)

    assert report["retrieved"] == 1
    assert report["retrieval_errors"] == 0
    assert report["empty_results"] == 0
    assert report["recall@5"] == 1.0
    # mrr 0.5 说明排名用的是 BM25 的顺序，不是 collection.get() 的返回顺序（c1 在 _ROWS 里排第一）
    assert report["mrr"] == 0.5
    assert report["keyword_hit_rate"] == 1.0
    assert report["bm25_corpus_chunks"] == 4


def test_lexical_eval_keeps_invisible_docs_out_of_the_metrics(monkeypatch):
    # c4 属于 doc 99，不在可见集合里：连它的 doc_type 都不该出现在结果里
    _patch_lexical(monkeypatch, [("c4", 99.0), ("c1", 5.0)])

    report = run_lexical_eval(_LEX_EVAL, db=object(), user_id=7, top_k=5)

    assert report["keyword_hit_rate"] == 1.0
    assert report["per_doc_type_recall"] == {"resume_template": 1.0}
    assert "jd_lib" not in report["per_doc_type_recall"]


def test_lexical_eval_recalls_when_bm25_ranks_right(monkeypatch):
    _patch_lexical(monkeypatch, [("c1", 5.0), ("c2", 1.0)])

    report = run_lexical_eval(_LEX_EVAL, db=object(), user_id=7, top_k=5)

    assert report["recall@5"] == 1.0
    assert report["mrr"] == 1.0
    assert report["keyword_hit_rate"] == 1.0


def test_dead_bm25_index_turns_the_lexical_gate_red(monkeypatch):
    """非空洞性检查：词法路断掉时，这道门必须变红而不是静悄悄放行。"""
    _patch_lexical(monkeypatch, [])

    report = run_lexical_eval(_LEX_EVAL, db=object(), user_id=7, top_k=5)
    assert report["recall@5"] == 0.0
    assert report["empty_results"] == 1

    failures = check_rag_thresholds(
        {"total": 1, "retrieved": 1, "retrieval_errors": 0, "lexical": report},
        top_k=5,
        min_lexical_recall=0.6,
    )
    assert failures == ["词法 recall@5 0.0 < 0.6（1/1 条测出，其中空结果 1 条、异常 0 条，BM25 覆盖 4 切片）"]


def test_lexical_gate_reports_a_failed_index_build(monkeypatch):
    """索引没建起来时，失败信息要指到"索引"而不是让人去查相关性。"""

    class _BrokenIndex:
        @classmethod
        def get(cls):
            return _FakeIndex(-1, build_failed=True)

    _patch_lexical(monkeypatch, [])
    monkeypatch.setattr("app.services.multi_recall._BM25Index", _BrokenIndex)

    report = run_lexical_eval(_LEX_EVAL, db=object(), user_id=7, top_k=5)
    assert report["bm25_corpus_chunks"] == -1
    assert report["bm25_build_failed"] is True

    failures = check_rag_thresholds({"total": 1, "lexical": report}, top_k=5, min_lexical_keyword_hit=0.6)
    assert len(failures) == 1
    assert failures[0].startswith("词法 keyword_hit_rate 0.0 < 0.6")
    assert "索引构建失败" in failures[0]


def test_fused_semantic_floor_is_refused_under_mock_embeddings():
    report = {
        "total": 2,
        "retrieved": 2,
        "retrieval_errors": 0,
        "empty_results": 0,
        "recall@5": 0.9,
        "mrr": 0.9,
        "keyword_hit_rate": 0.9,
    }

    failures = check_rag_thresholds(report, top_k=5, min_recall=0.5, embedding_provider="mock")

    assert len(failures) == 1
    assert "EMBEDDING_PROVIDER=mock 下不成立" in failures[0]
    # 真 provider 时同样的门槛照常比大小
    assert check_rag_thresholds(report, top_k=5, min_recall=0.5, embedding_provider="dashscope") == []


def test_empty_fused_results_fail_as_a_broken_pipeline_not_as_a_low_score():
    report = {
        "total": 3,
        "retrieved": 3,
        "retrieval_errors": 0,
        "empty_results": 3,
        "recall@5": 0.0,
        "mrr": 0.0,
        "keyword_hit_rate": 0.0,
    }

    failures = check_rag_thresholds(report, top_k=5, max_empty_results=0, embedding_provider="mock")

    assert failures[0].startswith("empty_results 3 > 0")
    assert "该查链路/可见性" in failures[0]


def test_floor_at_or_below_the_random_baseline_is_not_a_gate():
    report = {
        "total": 1,
        "retrieved": 1,
        "retrieval_errors": 0,
        "recall@5": 0.9,
        "lexical": {
            "total": 1,
            "retrieved": 1,
            "retrieval_errors": 0,
            "empty_results": 0,
            "recall@5": 0.9,
            "bm25_corpus_chunks": 4,
        },
    }
    baselines = {"recall": 0.479, "mrr": 0.333, "keyword_hit": 0.411}

    failures = check_rag_thresholds(
        report,
        top_k=5,
        min_recall=0.45,
        min_lexical_recall=0.4,
        random_baselines=baselines,
    )

    assert failures == [
        "recall@5 门槛 0.45 ≤ 随机基线 0.479：这道门分不出好坏，抬门槛或换语料",
        "词法 recall@5 门槛 0.4 ≤ 随机基线 0.479：这道门分不出好坏，抬门槛或换语料",
    ]

    # 门槛设了但根本没测词法路：说"未测出"，不能因为没数就放行
    no_lexical = check_rag_thresholds(
        {"total": 1, "retrieved": 1, "retrieval_errors": 0, "recall@5": 0.9},
        top_k=5,
        min_lexical_recall=0.6,
    )
    assert no_lexical == [
        "词法 recall@5 未测出（0/0 条测出，其中空结果 0 条、异常 0 条，BM25 覆盖 未建 切片），门槛 0.6 无从比较"
    ]


def test_random_baseline_is_one_when_the_corpus_cannot_be_distinguished(monkeypatch):
    """语料只有一种 doc_type 时，随机检索必得满分——基线要如实说出来。"""
    collection = _FakeCollection([("c1", "11", "jd_lib", "岗位"), ("c2", "11", "jd_lib", "职责")])
    monkeypatch.setattr("app.core.chroma_client.get_knowledge_collection", lambda: collection)

    eval_set = [{"query": "岗位", "expected_doc_types": ["jd_lib"], "expected_keywords": ["岗位"]}]
    baselines = random_metric_baselines(eval_set, top_k=5)

    assert baselines == {"recall": 1.0, "mrr": 1.0, "keyword_hit": 1.0}


def test_random_baseline_is_none_without_a_corpus(monkeypatch):
    def boom():
        raise RuntimeError("chroma 连不上")

    monkeypatch.setattr("app.core.chroma_client.get_knowledge_collection", boom)

    assert random_metric_baselines([{"query": "q", "expected_doc_types": ["jd_lib"]}], top_k=5) is None


# ===== 一次性语料的自锁：不许把种子文档灌进真库 =====


def test_seeder_refuses_a_non_sqlite_target(monkeypatch):
    from app.core.config import settings
    from scripts.seed_rag_corpus import guard_scratch_target

    monkeypatch.setattr(settings, "DATABASE_URL", "mysql+pymysql://root@127.0.0.1:3306/llmXM")
    try:
        guard_scratch_target()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("目标是 MySQL 时应该拒绝写入，否则种子文档会进真库")

    # 临时 SQLite 照常放行
    monkeypatch.setattr(settings, "DATABASE_URL", "sqlite:///./rag_ci.sqlite3")
    assert guard_scratch_target() == "sqlite:///./rag_ci.sqlite3"
    # 显式 --force 才允许写非 SQLite
    monkeypatch.setattr(settings, "DATABASE_URL", "mysql+pymysql://root@127.0.0.1:3306/llmXM")
    assert guard_scratch_target(allow_non_scratch=True).startswith("mysql+pymysql://")
