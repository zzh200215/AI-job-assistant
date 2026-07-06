# -*- coding: utf-8 -*-
"""测试 retrieval_planner 模块

覆盖：
  - 5 种 intent 的启发式回退
  - LLM 路径（mock provider 不走 LLM，应走入启发式）
  - _normalize_plan 清洗逻辑
  - 缓存命中
"""
from __future__ import annotations

import pytest

from app.services.retrieval_planner import (
    RetrievalPlan,
    _cache_key,
    _normalize_plan,
    clear_plan_cache,
    plan_retrieval,
)

_VALID_DOC_TYPES = {
    "resume_template", "jd_lib", "interview_q", "skill_model",
    "industry_report", "career_path", "salary_market", "transition_guide",
}


class TestHeuristicPlan:
    """mock provider 下 plan_retrieval 应走 heuristic 路径。"""

    def test_intent_resume_optimize(self):
        plan = plan_retrieval("改简历", intent="resume_optimize", use_llm=False)
        assert plan.source == "heuristic"
        assert "resume_template" in plan.doc_types
        assert 1 <= plan.doc_types["resume_template"] <= 5

    def test_intent_match_analysis(self):
        plan = plan_retrieval("匹配度", intent="match_analysis", use_llm=False)
        assert plan.source == "heuristic"
        assert "jd_lib" in plan.doc_types

    def test_intent_interview_prep(self):
        plan = plan_retrieval("面试准备", intent="interview_prep", use_llm=False)
        assert plan.source == "heuristic"
        assert "interview_q" in plan.doc_types
        assert plan.doc_types["interview_q"] >= 2

    def test_intent_career_planning(self):
        plan = plan_retrieval("职业规划", intent="career_planning", use_llm=False)
        assert plan.source == "heuristic"
        assert "career_path" in plan.doc_types
        assert "salary_market" in plan.doc_types

    def test_intent_full_analysis(self):
        plan = plan_retrieval("帮我全面分析", intent="full_analysis", use_llm=False)
        assert plan.source in ("heuristic",)
        # full_analysis 应覆盖 2-4 类
        assert 2 <= len(plan.doc_types) <= 6

    def test_unknown_intent_falls_back(self):
        """未知 intent 应退化为 full_analysis"""
        plan = plan_retrieval("随便查查", intent="nonsense_intent", use_llm=False)
        assert plan.source == "heuristic"
        assert len(plan.doc_types) >= 2

    def test_keyword_resume_fallback(self):
        """query 包含"优化"关键字，即使不传 intent 也应命中 resume_optimize"""
        plan = plan_retrieval("我想优化简历内容", use_llm=False)
        assert "resume_template" in plan.doc_types

    def test_keyword_interview_fallback(self):
        plan = plan_retrieval("面试题", use_llm=False)
        assert "interview_q" in plan.doc_types

    def test_keyword_career_fallback(self):
        plan = plan_retrieval("学习路线成长规划", use_llm=False)
        assert "career_path" in plan.doc_types


class TestNormalize:
    """_normalize_plan 清洗逻辑"""

    def test_valid_types_preserved(self):
        raw = {"doc_types": {"resume_template": 3, "skill_model": 2}, "reasoning": "test"}
        cleaned = _normalize_plan(raw)
        assert cleaned == {"resume_template": 3, "skill_model": 2}

    def test_invalid_type_dropped(self):
        raw = {"doc_types": {"resume_template": 2, "non_existent": 5}}
        cleaned = _normalize_plan(raw)
        assert "non_existent" not in cleaned
        assert cleaned == {"resume_template": 2}

    def test_top_k_capped(self):
        raw = {"doc_types": {"resume_template": 999}}
        cleaned = _normalize_plan(raw)
        assert cleaned["resume_template"] == 5  # _MAX_TOP_K_PER_SOURCE

    def test_negative_skipped(self):
        raw = {"doc_types": {"resume_template": -1, "skill_model": 0}}
        cleaned = _normalize_plan(raw)
        assert cleaned == {}

    def test_total_scaled(self):
        """超出总上限时按比例缩减"""
        raw = {"doc_types": {t: 5 for t in list(_VALID_DOC_TYPES)[:6]}}
        cleaned = _normalize_plan(raw)
        total = sum(cleaned.values())
        assert 1 <= total <= 15

    def test_not_dict_returns_empty(self):
        assert _normalize_plan(None) == {}
        assert _normalize_plan("string") == {}
        assert _normalize_plan([1, 2, 3]) == {}
        assert _normalize_plan({}) == {}  # no doc_types key


class TestCache:
    def test_cache_hit(self):
        clear_plan_cache()
        q = "测试缓存"
        p1 = plan_retrieval(q, intent="full_analysis", use_llm=False)
        p2 = plan_retrieval(q, intent="full_analysis", use_llm=False)
        assert p1.doc_types == p2.doc_types

    def test_cache_key_mismatch(self):
        clear_plan_cache()
        p1 = plan_retrieval("query A", intent="full_analysis", use_llm=False)
        p2 = plan_retrieval("query B", intent="full_analysis", use_llm=False)
        # 不同 query 不应共享缓存
        k1 = _cache_key("query A", "full_analysis")
        k2 = _cache_key("query B", "full_analysis")
        assert k1 != k2

    def test_clear_cache(self):
        clear_plan_cache()
        from app.services.retrieval_planner import _PLAN_CACHE
        assert len(_PLAN_CACHE) == 0


class TestRetrievalPlanDataclass:
    def test_is_empty_true(self):
        plan = RetrievalPlan(doc_types={})
        assert plan.is_empty() is True

    def test_is_empty_false(self):
        plan = RetrievalPlan(doc_types={"resume_template": 2})
        assert plan.is_empty() is False

    def test_default_source(self):
        plan = RetrievalPlan(doc_types={"skill_model": 1})
        assert plan.source == "heuristic"
