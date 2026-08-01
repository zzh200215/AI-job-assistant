"""
RAG 检索测试

覆盖 RAG 流水线的核心模块：
  1. search_knowledge        — 向量检索 + 文档类型过滤 + 空库降级
  2. search_knowledge_multi_queries — 多 query 改写检索 + 去重融合
  3. merge_and_dedup_results — 去重合并的边界情况
  4. build_rag_context_multi — 多类型分类上下文组装
  5. get_knowledge_references — 引用提取
  6. evaluate_rag_confidence — RAG 置信度评估
  7. multi_recall            — 多路召回（集成测试级别）
"""

from unittest.mock import patch

import pytest

from app.services.multi_recall import _tokenize, multi_recall
from app.services.query_rewrite_service import RewrittenQuery
from app.services.rag_confidence_service import evaluate_rag_confidence
from app.services.rag_service import (
    build_rag_context,
    build_rag_context_multi,
    get_knowledge_references,
    get_knowledge_references_with_rewrite,
    merge_and_dedup_results,
    search_knowledge,
    search_knowledge_multi_queries,
)

# ===================== Fixtures =====================


@pytest.fixture(autouse=True)
def auto_mock_chroma_and_embed(mock_chroma_collection, mock_embedding, mock_reranker):
    """Globally mock Chroma, Embedding, and Reranker for all RAG tests."""
    yield


@pytest.fixture(autouse=True)
def _tenantless_rag_db(db_session):
    """让纯检索逻辑用例的 RAG 入口带上 DB 会话并放开可见性过滤。

    本文件用例只验证检索/组装逻辑（Chroma 已 mock），不验证租户隔离——
    隔离行为由 tests/test_tenant_jobs_knowledge.py 专项覆盖，故此处：
      1. get_visible_knowledge_doc_ids → None（全量可见，admin 语义）；
      2. 未显式传 db 的调用自动补上 db_session（绕过 fail-closed）。

    同时替换 rag_service / multi_recall 模块属性与本文件 `from ... import` 的名字
    （import 时已绑定，仅 patch 模块属性不足以覆盖本文件的直接调用）。
    """
    import sys
    from unittest import mock

    import app.services.multi_recall as mr
    import app.services.rag_service as rs

    test_module = sys.modules[__name__]
    _orig_search = rs.search_knowledge
    _orig_multi = mr.multi_recall

    def _search(*args, **kwargs):
        if kwargs.get("db") is None:
            kwargs["db"] = db_session
        return _orig_search(*args, **kwargs)

    def _multi(*args, **kwargs):
        if kwargs.get("db") is None:
            kwargs["db"] = db_session
        return _orig_multi(*args, **kwargs)

    patchers = [
        mock.patch("app.services.rag_service.get_visible_knowledge_doc_ids", return_value=None),
        mock.patch("app.services.multi_recall.get_visible_knowledge_doc_ids", return_value=None),
        mock.patch("app.services.rag_service.search_knowledge", side_effect=_search),
        mock.patch("app.services.multi_recall.multi_recall", side_effect=_multi),
        mock.patch.object(test_module, "search_knowledge", side_effect=_search),
        mock.patch.object(test_module, "multi_recall", side_effect=_multi),
    ]
    for patcher in patchers:
        patcher.start()
    try:
        yield
    finally:
        for patcher in reversed(patchers):
            patcher.stop()


@pytest.fixture
def sample_chunks():
    """Create sample Chroma-like results to return from mock query."""
    return {
        "ids": [["chunk_1", "chunk_2", "chunk_3"]],
        "documents": [["Python FastAPI 开发经验", "RAG 系统架构设计", "深度学习基础"]],
        "metadatas": [
            [
                {"doc_title": "后端技能清单", "doc_type": "skill_model", "chunk_index": 0},
                {"doc_title": "RAG 实践指南", "doc_type": "jd_lib", "chunk_index": 1},
                {"doc_title": "深度学习入门", "doc_type": "interview_q", "chunk_index": 2},
            ]
        ],
        "distances": [[0.15, 0.30, 0.50]],
    }


# ==================== search_knowledge Tests ====================


class TestSearchKnowledge:
    """search_knowledge 基础检索测试"""

    def test_basic_retrieval(self, mock_chroma_collection, sample_chunks):
        """正常检索应返回解析后的结果列表。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = sample_chunks

        results = search_knowledge(query="Python开发", top_k=3)

        assert len(results) == 3
        assert results[0]["chunk_id"] == "chunk_1"
        assert results[0]["text"] == "Python FastAPI 开发经验"
        assert results[0]["doc_title"] == "后端技能清单"
        assert results[0]["doc_type"] == "skill_model"
        assert results[0]["score"] == 0.15

    def test_retrieval_with_doc_type_filter(self, mock_chroma_collection, sample_chunks):
        """传入 doc_type 过滤时，应传递给 Chroma query 的 where 参数。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = sample_chunks

        search_knowledge(query="Python", doc_type="skill_model", top_k=3)

        # 验证 where 参数被正确传递
        call_kwargs = mock_chroma_collection.query.call_args[1]
        assert call_kwargs["where"] == {"doc_type": "skill_model"}

    def test_empty_collection(self, mock_chroma_collection):
        """知识库为空时返回空列表。"""
        mock_chroma_collection.count.return_value = 0

        results = search_knowledge(query="anything")
        assert results == []
        mock_chroma_collection.query.assert_not_called()

    def test_query_failure_returns_empty(self, mock_chroma_collection):
        """Chroma 查询异常时应降级为空结果。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.side_effect = Exception("Chroma 连接失败")

        results = search_knowledge(query="test")
        assert results == []

    def test_empty_documents_field(self, mock_chroma_collection):
        """documents 字段缺少对应条目时应有兜底。"""
        mock_chroma_collection.count.return_value = 5
        # Chroma 返回的 ids 和 metadatas 长度匹配，documents 是所有结果的总列表
        mock_chroma_collection.query.return_value = {
            "ids": [["c1"]],
            "documents": [[""]],  # 空文档内容
            "metadatas": [[{"doc_title": "A", "doc_type": "t", "chunk_index": 0}]],
            "distances": [[0.1]],
        }

        results = search_knowledge(query="test", top_k=2)
        assert len(results) >= 1
        assert results[0]["text"] == ""

    def test_top_k_respects_settings_default(self, mock_chroma_collection, sample_chunks):
        """不传 top_k 时应使用 settings 默认值。"""
        from app.core.config import settings

        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = sample_chunks

        search_knowledge(query="test")
        call_kwargs = mock_chroma_collection.query.call_args[1]
        assert call_kwargs["n_results"] == settings.RAG_TOP_K

    def test_embedding_reuse(self, mock_chroma_collection, mock_embedding, sample_chunks):
        """传入 query_embedding 时复用，不重复调用 embed_text。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = sample_chunks

        precomputed = [0.1] * 512
        search_knowledge(query="test", query_embedding=precomputed, top_k=3)

        # embed_text 不应被调用（因为传入了预计算向量）
        # mock_embedding 是 autouse fixture，但 search_knowledge 内部调用了 embed_text
        # 由于我们传入了 query_embedding，embed_text 不会被调用
        call_kwargs = mock_chroma_collection.query.call_args[1]
        assert call_kwargs["query_embeddings"] == [precomputed]

    def test_result_order_by_distance(self, mock_chroma_collection):
        """结果应按 score（cosine distance）升序排列。"""
        mock_chroma_collection.count.return_value = 10
        # Chroma 按 distance 升序返回
        mock_chroma_collection.query.return_value = {
            "ids": [["c3", "c1", "c2"]],
            "documents": [["text3", "text1", "text2"]],
            "metadatas": [
                [
                    {"doc_title": "C", "doc_type": "t", "chunk_index": 2},
                    {"doc_title": "A", "doc_type": "t", "chunk_index": 0},
                    {"doc_title": "B", "doc_type": "t", "chunk_index": 1},
                ]
            ],
            "distances": [[0.1, 0.3, 0.5]],
        }

        results = search_knowledge(query="test", top_k=3)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores)


# ==================== Multi-Query Search Tests ====================


class TestSearchKnowledgeMultiQueries:
    """多 Query 改写检索测试"""

    def test_multi_query_retrieval(self, mock_chroma_collection):
        """多个改写 query 分别检索后合并去重。"""
        mock_chroma_collection.count.return_value = 10

        # 每次 query 返回不同结果
        call_count = [0]

        def _side_effect(*args, **kwargs):
            call_count[0] += 1
            idx = call_count[0]
            return {
                "ids": [[f"chunk_{idx}_1", f"chunk_{idx}_2"]],
                "documents": [[f"result_{idx}_a", f"result_{idx}_b"]],
                "metadatas": [
                    [
                        {"doc_title": f"Doc{idx}", "doc_type": "skill_model", "chunk_index": 0},
                        {"doc_title": f"Doc{idx}", "doc_type": "skill_model", "chunk_index": 1},
                    ]
                ],
                "distances": [[0.1, 0.2]],
            }

        mock_chroma_collection.query.side_effect = _side_effect

        queries = [
            RewrittenQuery(query_text="Python开发", query_type="original", purpose="原始", priority=1),
            RewrittenQuery(query_text="Python后端技能", query_type="skill", purpose="技能", priority=2),
        ]

        results = search_knowledge_multi_queries(queries, top_k_per_query=2)

        assert len(results) > 0
        # 应该包含 vector_score 字段（internal addition from search_knowledge_multi_queries）
        for r in results:
            assert "vector_score" in r
            assert "recalled_by" in r
            assert "query_used" in r

    def test_multi_query_empty_input(self, mock_chroma_collection):
        """空 query 列表应返回空结果。"""
        results = search_knowledge_multi_queries([])
        assert results == []

    def test_multi_query_empty_text(self, mock_chroma_collection):
        """query_text 为空的条目应跳过。"""
        results = search_knowledge_multi_queries(
            [
                RewrittenQuery(query_text="", query_type="original", purpose="", priority=1),
            ]
        )
        assert results == []


# ==================== Merge & Dedup Tests ====================


class TestMergeAndDedup:
    """merge_and_dedup_results 去重合并测试"""

    def test_dedup_same_chunk_keeps_best_score(self):
        """相同 chunk_id 应保留 score 最小的（cosine distance）。"""
        results = [
            {
                "chunk_id": "c1",
                "score": 0.5,
                "text": "text1",
                "query_used": "q1",
                "query_type": "skill",
                "doc_title": "A",
                "doc_type": "t",
            },
            {
                "chunk_id": "c1",
                "score": 0.2,
                "text": "text1",
                "query_used": "q2",
                "query_type": "interview",
                "doc_title": "A",
                "doc_type": "t",
            },
            {
                "chunk_id": "c2",
                "score": 0.3,
                "text": "text2",
                "query_used": "q1",
                "query_type": "skill",
                "doc_title": "B",
                "doc_type": "t",
            },
        ]
        merged = merge_and_dedup_results(results)

        assert len(merged) == 2
        c1 = next(m for m in merged if m["chunk_id"] == "c1")
        assert c1["score"] == 0.2  # 更小的 score
        assert len(c1["queries"]) == 2

    def test_dedup_queries_list_deduped(self):
        """queries 列表本身应去重。"""
        results = [
            {
                "chunk_id": "c1",
                "score": 0.5,
                "text": "text1",
                "query_used": "q1",
                "query_type": "skill",
                "doc_title": "A",
                "doc_type": "t",
            },
            {
                "chunk_id": "c1",
                "score": 0.3,
                "text": "text1",
                "query_used": "q1",
                "query_type": "skill",
                "doc_title": "A",
                "doc_type": "t",
            },
        ]
        merged = merge_and_dedup_results(results)

        assert len(merged) == 1
        # queries 应去重
        assert len(merged[0]["queries"]) == 1

    def test_sort_by_score_ascending(self):
        """最终结果应按 score 升序排列。"""
        results = [
            {
                "chunk_id": "c3",
                "score": 0.8,
                "text": "t3",
                "query_used": "q1",
                "query_type": "skill",
                "doc_title": "A",
                "doc_type": "t",
            },
            {
                "chunk_id": "c1",
                "score": 0.1,
                "text": "t1",
                "query_used": "q1",
                "query_type": "skill",
                "doc_title": "B",
                "doc_type": "t",
            },
            {
                "chunk_id": "c2",
                "score": 0.5,
                "text": "t2",
                "query_used": "q1",
                "query_type": "skill",
                "doc_title": "C",
                "doc_type": "t",
            },
        ]
        merged = merge_and_dedup_results(results)
        scores = [m["score"] for m in merged]
        assert scores == sorted(scores)

    def test_empty_input(self):
        assert merge_and_dedup_results([]) == []

    def test_scores_with_equal_values(self):
        """score 相等时保留第一个。"""
        results = [
            {
                "chunk_id": "c1",
                "score": 0.5,
                "text": "original",
                "query_used": "q1",
                "query_type": "skill",
                "doc_title": "A",
                "doc_type": "t",
            },
            {
                "chunk_id": "c1",
                "score": 0.5,
                "text": "later",
                "query_used": "q2",
                "query_type": "interview",
                "doc_title": "A",
                "doc_type": "t",
            },
        ]
        merged = merge_and_dedup_results(results)
        assert len(merged) == 1
        # score 相同时保留第一个，所以 text 是 "original"
        assert merged[0]["text"] == "original"


# ==================== build_rag_context_multi Tests ====================


class TestBuildRagContextMulti:
    """build_rag_context_multi 多类型上下文测试"""

    def test_multi_context_format(self, mock_chroma_collection):
        """多类型上下文应包含所有 doc_type 的分类结果。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = {
            "ids": [["c1"]],
            "documents": [["Python开发经验"]],
            "metadatas": [[{"doc_title": "技能清单", "doc_type": "skill_model", "chunk_index": 0}]],
            "distances": [[0.15]],
        }

        ctx = build_rag_context_multi(query="Python开发")

        # 应包含所有分类字段
        assert "resume_templates" in ctx
        assert "jd_library" in ctx
        assert "skill_models" in ctx
        assert "all" in ctx  # 汇总字段
        assert "_plan" in ctx  # 调试字段

        # 至少有一个分类有内容（排除 _plan 调试字段）
        has_content = any(bool(v) for k, v in ctx.items() if k not in ("all", "_plan"))
        assert has_content

    def test_multi_context_empty_when_no_results(self, mock_chroma_collection):
        """检索为空时所有分类应为空或只含空白。"""
        mock_chroma_collection.count.return_value = 0

        ctx = build_rag_context_multi(query="nothing")

        # 子分类字段应为空字符串（排除调试用的 _plan 字段）
        sub_keys = [k for k in ctx if k not in ("all", "_plan")]
        for key in sub_keys:
            assert ctx[key] == "", f"{key} 应为空字符串"

    def test_multi_context_with_embedding_reuse(self, mock_chroma_collection):
        """多类型检索应复用一次 query embedding。"""
        from app.services import embedding_service

        original_embed = embedding_service.embed_text

        call_count = [0]

        def tracking_embed(text):
            call_count[0] += 1
            return original_embed(text)

        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = {
            "ids": [["c1"]],
            "documents": [["test"]],
            "metadatas": [[{"doc_title": "T", "doc_type": "skill_model", "chunk_index": 0}]],
            "distances": [[0.1]],
        }

        with patch("app.services.rag_service.embed_text", side_effect=tracking_embed):
            build_rag_context_multi(query="test")

        # embed_text 应该只被调用 1 次（build_rag_context_multi 内部先预计算一次）
        assert call_count[0] == 1


# ==================== get_knowledge_references Tests ====================


class TestGetKnowledgeReferences:
    """知识引用提取测试"""

    def test_references_extraction(self, mock_chroma_collection):
        """引用应按 doc_title 分组并包含 chunks。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = {
            "ids": [["c1", "c2"]],
            "documents": [["Python开发经验", "FastAPI项目"]],
            "metadatas": [
                [
                    {"doc_title": "技能清单", "doc_type": "skill_model", "chunk_index": 0},
                    {"doc_title": "技能清单", "doc_type": "skill_model", "chunk_index": 1},
                ]
            ],
            "distances": [[0.15, 0.30]],
        }

        refs = get_knowledge_references(query="Python")

        assert len(refs) == 1  # 同一文档聚合
        assert refs[0]["doc_title"] == "技能清单"
        assert len(refs[0]["chunks"]) == 2

    def test_references_empty(self, mock_chroma_collection):
        """检索为空时返回空列表。"""
        mock_chroma_collection.count.return_value = 0
        assert get_knowledge_references(query="nothing") == []


# ==================== RAG Confidence Tests ====================


class TestRagConfidence:
    """RAG 置信度评估测试"""

    def test_high_confidence_full_retrieval(self):
        """8 类文档都有召回时置信度高。"""
        retrievals = {
            "resume_template": [{"score": 0.1, "doc_title": "A", "doc_type": "resume_template"}] * 2,
            "jd_lib": [{"score": 0.2, "doc_title": "B", "doc_type": "jd_lib"}] * 2,
            "interview_q": [{"score": 0.3, "doc_title": "C", "doc_type": "interview_q"}] * 1,
            "skill_model": [{"score": 0.15, "doc_title": "D", "doc_type": "skill_model"}] * 3,
            "industry_report": [{"score": 0.4, "doc_title": "E", "doc_type": "industry_report"}] * 1,
            "career_path": [{"score": 0.5, "doc_title": "F", "doc_type": "career_path"}] * 1,
            "salary_market": [{"score": 0.6, "doc_title": "G", "doc_type": "salary_market"}] * 1,
            "transition_guide": [{"score": 0.7, "doc_title": "H", "doc_type": "transition_guide"}] * 1,
        }

        confidence = evaluate_rag_confidence("Python开发", retrievals)

        assert confidence["score"] >= 80
        assert confidence["level"] == "high"
        assert confidence["signals"]["has_skill_model"] is True
        assert confidence["signals"]["has_similar_jd"] is True
        assert "召回证据较充足" in " ".join(confidence["strengths"])

    def test_low_confidence_empty_retrieval(self):
        """没有召回时置信度低。"""
        retrievals = {
            "resume_template": [],
            "jd_lib": [],
            "interview_q": [],
            "skill_model": [],
            "industry_report": [],
            "career_path": [],
            "salary_market": [],
            "transition_guide": [],
        }

        confidence = evaluate_rag_confidence("未知领域", retrievals)

        assert confidence["score"] < 60
        assert confidence["level"] == "low"
        assert len(confidence["risks"]) > 0

    def test_confidence_breakdown_structure(self):
        """置信度返回结果应包含完整的字段结构。"""
        retrievals = {
            "skill_model": [{"score": 0.1, "doc_title": "D", "doc_type": "skill_model"}],
            "jd_lib": [],
        }

        confidence = evaluate_rag_confidence("Python", retrievals)

        assert "query" in confidence
        assert "score" in confidence
        assert "level" in confidence
        assert "signals" in confidence
        assert "breakdown" in confidence
        assert "strengths" in confidence
        assert "risks" in confidence
        assert "summary" in confidence

        # breakdown 应有 4 项
        assert len(confidence["breakdown"]) == 4

    def test_confidence_handles_final_score(self):
        """当提供 final_score 时优先使用。"""
        retrievals = {
            "skill_model": [{"final_score": 0.9, "score": 0.1, "doc_title": "D", "doc_type": "skill_model"}],
        }

        confidence = evaluate_rag_confidence("Python", retrievals)
        # final_score=0.9 → similarity 高
        assert confidence["signals"]["avg_similarity"] > 0.5

    def test_confidence_handles_different_score_formats(self):
        """置信度应兼容不同的 score 字段格式。"""
        retrievals = {
            "skill_model": [
                {"final_score": 0.85, "doc_title": "A", "doc_type": "skill_model"},
                {"vector_similarity": 0.75, "doc_title": "B", "doc_type": "skill_model"},
                {"score": 0.2, "doc_title": "C", "doc_type": "skill_model"},
            ],
        }

        confidence = evaluate_rag_confidence("Python", retrievals)
        assert confidence["score"] > 0
        # 即使分数格式不同也不应抛异常


# ==================== MultiRecall Integration Tests ====================


class TestMultiRecall:
    """multi_recall 多路召回集成测试"""

    def test_multi_recall_with_results(self, mock_chroma_collection):
        """多路召回应返回融合后的结果。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = {
            "ids": [["c1", "c2"]],
            "documents": [["Python开发", "FastAPI"]],
            "metadatas": [
                [
                    {"doc_title": "技能清单", "doc_type": "skill_model", "chunk_index": 0, "doc_id": "1"},
                    {"doc_title": "技能清单", "doc_type": "skill_model", "chunk_index": 1, "doc_id": "1"},
                ]
            ],
            "distances": [[0.15, 0.30]],
        }
        mock_chroma_collection.get.return_value = {
            "ids": ["c1", "c2"],
            "documents": ["Python开发", "FastAPI"],
            "metadatas": [
                {"doc_title": "技能清单", "doc_type": "skill_model", "chunk_index": 0, "doc_id": "1"},
                {"doc_title": "技能清单", "doc_type": "skill_model", "chunk_index": 1, "doc_id": "1"},
            ],
        }

        results = multi_recall(query="Python开发", doc_type="skill_model", top_k=3)

        assert len(results) > 0
        for r in results:
            assert "chunk_id" in r
            assert "text" in r
            assert "doc_title" in r
            assert "doc_type" in r
            assert "rrf_score" in r
            assert "vector_score" in r
            assert "bm25_relevance" in r
            assert "final_score" in r

    def test_multi_recall_empty_collection(self, mock_chroma_collection):
        """空 collection 时返回空结果。"""
        mock_chroma_collection.count.return_value = 0

        results = multi_recall(query="anything")
        assert results == []

    def test_multi_recall_vector_failure(self, mock_chroma_collection):
        """向量召回失败时仍可返回结果（BM25 降级）。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.side_effect = Exception("Chroma 查询失败")

        # 即使向量召回失败，multi_recall 不该抛异常
        results = multi_recall(query="Python", top_k=3)
        # 应该是空结果或降级结果
        assert isinstance(results, list)


# ==================== _tokenize Tests ====================


class TestTokenize:
    """分词工具测试"""

    def test_tokenize_basic(self):
        tokens = _tokenize("Python 开发经验")
        assert len(tokens) > 0
        assert "Python" in tokens or "开发" in tokens or "经验" in tokens

    def test_tokenize_empty(self):
        assert _tokenize("") == []

    def test_tokenize_whitespace(self):
        assert _tokenize("   ") == []

    def test_tokenize_padding(self):
        """短文本应正常分词。"""
        tokens = _tokenize("AI")
        assert isinstance(tokens, list)


# ==================== web_search_context Tests ====================


class TestBuildRagContext:
    """build_rag_context 基础上下文组装测试"""

    def test_build_context_format(self, mock_chroma_collection):
        """上下文应采用标准格式。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = {
            "ids": [["c1"]],
            "documents": [["Python开发经验"]],
            "metadatas": [
                [
                    {"doc_title": "技能清单", "doc_type": "skill_model", "chunk_index": 0},
                ]
            ],
            "distances": [[0.15]],
        }

        context = build_rag_context(query="Python开发", db=None)

        assert "===== 参考知识 =====" in context
        assert "技能清单" in context
        assert "Python开发经验" in context

    def test_build_context_empty(self, mock_chroma_collection):
        """空检索返回空字符串。"""
        mock_chroma_collection.count.return_value = 0
        assert build_rag_context(query="nothing", db=None) == ""


# ==================== get_knowledge_references_with_rewrite Tests ====================


class TestGetKnowledgeReferencesWithRewrite:
    """改写 query 的知识引用测试"""

    def test_references_with_rewrite(self, mock_chroma_collection):
        """改写 query 的引用应包含 query_type 信息。"""
        mock_chroma_collection.count.return_value = 10
        mock_chroma_collection.query.return_value = {
            "ids": [["c1"]],
            "documents": [["Python开发经验"]],
            "metadatas": [
                [
                    {"doc_title": "技能清单", "doc_type": "skill_model", "chunk_index": 0},
                ]
            ],
            "distances": [[0.15]],
        }

        queries = [
            RewrittenQuery(query_text="Python开发", query_type="skill", purpose="技能", priority=1),
        ]
        refs = get_knowledge_references_with_rewrite(queries)

        assert len(refs) > 0
        assert "query_type" in refs[0]["chunks"][0]
        assert "query_used" in refs[0]["chunks"][0]
