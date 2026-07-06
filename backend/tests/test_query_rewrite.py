# -*- coding: utf-8 -*-
"""RAG Query Rewrite 模块测试用例"""
import pytest
from unittest.mock import patch, MagicMock

from app.services.query_rewrite_service import rewrite_queries, RewrittenQuery, _build_prompt
from app.services.rag_service import merge_and_dedup_results, search_knowledge_multi_queries


# ==================== Query Rewrite Service 测试 ====================

class TestQueryRewriteService:
    def test_build_prompt_contains_fields(self):
        prompt = _build_prompt("原始问题", "简历摘要", "JD摘要")
        assert "原始问题" in prompt
        assert "简历摘要" in prompt
        assert "JD摘要" in prompt
        assert "query_type" in prompt
        assert "skill" in prompt
        assert "responsibility" in prompt
        assert "interview" in prompt
        assert "competency" in prompt

    @patch("app.services.query_rewrite_service.chat_json")
    def test_rewrite_queries_success(self, mock_chat_json):
        mock_chat_json.return_value = [
            {"query_text": "Python FastAPI 后端技能", "query_type": "skill", "purpose": "检索技能", "priority": 1},
            {"query_text": "后端工程师岗位职责", "query_type": "responsibility", "purpose": "检索职责", "priority": 2},
        ]
        result = rewrite_queries("我想了解后端工程师", resume_summary="5年Python", jd_summary="招后端")
        assert len(result) == 3
        assert result[0].query_text == "Python FastAPI 后端技能"
        assert result[0].query_type == "skill"
        assert result[0].priority == 1
        assert result[-1].query_type == "original"
        assert result[-1].query_text == "我想了解后端工程师"

    @patch("app.services.query_rewrite_service.chat_json")
    def test_rewrite_queries_fallback_on_empty(self, mock_chat_json):
        mock_chat_json.return_value = []
        result = rewrite_queries("原始问题")
        assert len(result) == 1
        assert result[0].query_type == "original"
        assert result[0].query_text == "原始问题"

    @patch("app.services.query_rewrite_service.chat_json")
    def test_rewrite_queries_fallback_on_exception(self, mock_chat_json):
        mock_chat_json.side_effect = RuntimeError("LLM 服务不可用")
        result = rewrite_queries("原始问题")
        assert len(result) == 1
        assert result[0].query_type == "original"
        assert "回退" in result[0].purpose

    @patch("app.services.query_rewrite_service.chat_json")
    def test_rewrite_queries_deduplicate(self, mock_chat_json):
        mock_chat_json.return_value = [
            {"query_text": "相同内容", "query_type": "skill", "purpose": "a", "priority": 1},
            {"query_text": "相同内容", "query_type": "skill", "purpose": "b", "priority": 2},
        ]
        result = rewrite_queries("test")
        assert len(result) == 2  # 一个 skill + 一个 original fallback
        texts = [r.query_text for r in result]
        assert texts.count("相同内容") == 1

    @patch("app.services.query_rewrite_service.chat_json")
    def test_rewrite_queries_max_queries(self, mock_chat_json):
        mock_chat_json.return_value = [
            {"query_text": f"query{i}", "query_type": "skill", "purpose": "", "priority": i}
            for i in range(10)
        ]
        result = rewrite_queries("test", max_queries=3)
        assert len(result) <= 4  # 3个 + 可能1个original

    def test_rewrite_queries_empty_input(self):
        result = rewrite_queries("")
        assert result == []

    @patch("app.services.query_rewrite_service.chat_json")
    def test_rewrite_queries_nested_dict_response(self, mock_chat_json):
        mock_chat_json.return_value = {
            "queries": [
                {"query_text": "技能A", "query_type": "skill", "purpose": "", "priority": 1},
            ]
        }
        result = rewrite_queries("test")
        assert len(result) == 2  # skill + original
        assert result[0].query_text == "技能A"


# ==================== RAG Merge & Dedup 测试 ====================

class TestMergeAndDedup:
    def test_merge_and_dedup_basic(self):
        results = [
            {"chunk_id": "c1", "text": "text1", "score": 0.5, "query_used": "q1", "query_type": "skill", "doc_title": "A", "doc_type": "t"},
            {"chunk_id": "c2", "text": "text2", "score": 0.3, "query_used": "q1", "query_type": "skill", "doc_title": "B", "doc_type": "t"},
            {"chunk_id": "c1", "text": "text1", "score": 0.2, "query_used": "q2", "query_type": "interview", "doc_title": "A", "doc_type": "t"},
        ]
        merged = merge_and_dedup_results(results)
        assert len(merged) == 2
        # c1 应该保留 score 最小的 0.2
        c1 = [m for m in merged if m["chunk_id"] == "c1"][0]
        assert c1["score"] == 0.2
        assert c1["query_used"] == "q2"
        assert len(c1["queries"]) == 2

    def test_merge_and_dedup_single(self):
        results = [
            {"chunk_id": "c1", "text": "text1", "score": 0.1, "query_used": "q1", "query_type": "skill", "doc_title": "A", "doc_type": "t"},
        ]
        merged = merge_and_dedup_results(results)
        assert len(merged) == 1
        assert merged[0]["queries"][0]["text"] == "q1"

    def test_merge_and_dedup_empty(self):
        assert merge_and_dedup_results([]) == []

    def test_merge_and_dedup_sort_order(self):
        results = [
            {"chunk_id": "c3", "text": "t3", "score": 0.8, "query_used": "q1", "query_type": "skill", "doc_title": "A", "doc_type": "t"},
            {"chunk_id": "c1", "text": "t1", "score": 0.1, "query_used": "q1", "query_type": "skill", "doc_title": "A", "doc_type": "t"},
            {"chunk_id": "c2", "text": "t2", "score": 0.5, "query_used": "q1", "query_type": "skill", "doc_title": "A", "doc_type": "t"},
        ]
        merged = merge_and_dedup_results(results)
        scores = [m["score"] for m in merged]
        assert scores == sorted(scores)


# ==================== RewrittenQuery Dataclass 测试 ====================

class TestRewrittenQuery:
    def test_dataclass_creation(self):
        q = RewrittenQuery(query_text="test", query_type="skill", purpose="purpose", priority=1)
        assert q.query_text == "test"
        assert q.priority == 1
