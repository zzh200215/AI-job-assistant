"""
统一 LLM 调用封装
- 通过 LLM_PROVIDER 切换：mock / openai / qwen / local
- 对外只暴露 chat_json(prompt) -> dict
- 真实模型走 OpenAI 兼容协议（OpenAI 官方、Qwen 兼容模式都可用）
"""

import copy
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

import requests
from pydantic import BaseModel, ValidationError

from app.agents.tools import Tool, get_tool
from app.core.config import settings
from app.core.prometheus_metrics import record_llm_error, record_llm_request
from app.core.request_context import get_request_id
from app.utils.json_utils import extract_json
from app.utils.retry import retry_call

logger = logging.getLogger(__name__)

# 网络类故障的重试次数与退避
_LLM_MAX_RETRIES = 2
_LLM_USAGE_CONTEXT: ContextVar[dict[str, float]] = ContextVar("llm_usage_context", default=None)
_SIMPLIFIED_PROMPT_MAX_CHARS = 3000


class _RetryableLLMError(Exception):
    """可重试的 LLM 网络/服务端错误，供 retry_call 识别"""

    pass


class LLMProviderError(Exception):
    """LLM provider 错误基类，供上层映射 HTTP 状态码"""

    pass


class LLMTimeoutError(LLMProviderError):
    """LLM 调用超时"""

    pass


class LLMAuthError(LLMProviderError):
    """LLM 鉴权失败"""

    pass


class LLMRateLimitError(LLMProviderError):
    """LLM 限流"""

    pass


class LLMParseError(LLMProviderError):
    """LLM 返回解析失败"""

    pass


# ===================== 结果缓存 =====================
# 相同 prompt（同一 provider+model）直接复用上次解析结果，省去重复 LLM 调用。
# temperature 较低、分析类 prompt 高度可复现，缓存命中可显著降时延与 token 成本。
# 进程内 LRU；如需跨进程共享可替换为 Redis。
_LLM_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_LLM_CACHE_MAX = 256
# 多智能体并行执行时 chat_json 会被多线程并发调用，缓存读写需加锁
_LLM_CACHE_LOCK = threading.Lock()
_LLM_TRACE_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("llm_trace_context", default=None)


def _cache_key(provider: str, prompt: str) -> str:
    raw = f"{provider}|{settings.LLM_MODEL}|{prompt}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def clear_llm_cache() -> None:
    """清空 LLM 结果缓存（测试或强制刷新时用）。"""
    with _LLM_CACHE_LOCK:
        _LLM_CACHE.clear()


def set_llm_trace_context(context: dict[str, Any] | None = None) -> None:
    """Set current trace context for the next LLM call."""
    _LLM_TRACE_CONTEXT.set(dict(context or {}))


def get_llm_trace_context() -> dict[str, Any]:
    return dict(_LLM_TRACE_CONTEXT.get() or {})


def _consume_llm_trace_context() -> dict[str, Any]:
    context = get_llm_trace_context()
    _LLM_TRACE_CONTEXT.set({})
    return context


def reset_llm_usage() -> None:
    """Reset per-context LLM usage counters."""
    _LLM_USAGE_CONTEXT.set({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_cents": 0.0})


def get_llm_usage() -> dict[str, float]:
    """Return current per-context LLM usage counters."""
    usage = _LLM_USAGE_CONTEXT.get()
    if usage is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_cents": 0.0}
    return dict(usage)


def _record_usage(usage: dict | None, model: str | None = None) -> None:
    if not usage:
        return

    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    cost_cents = (prompt_tokens / 1000.0) * float(settings.LLM_INPUT_COST_PER_1K_CENTS or 0.0) + (
        completion_tokens / 1000.0
    ) * float(settings.LLM_OUTPUT_COST_PER_1K_CENTS or 0.0)

    current = _LLM_USAGE_CONTEXT.get()
    if current is None:
        current = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_cents": 0.0}
    updated = {
        "prompt_tokens": int(current.get("prompt_tokens", 0)) + prompt_tokens,
        "completion_tokens": int(current.get("completion_tokens", 0)) + completion_tokens,
        "total_tokens": int(current.get("total_tokens", 0)) + total_tokens,
        "cost_cents": float(current.get("cost_cents", 0.0)) + cost_cents,
    }
    _LLM_USAGE_CONTEXT.set(updated)
    logger.info(
        "LLM usage model=%s prompt_tokens=%s completion_tokens=%s cost_cents=%.6f",
        model or settings.LLM_MODEL,
        prompt_tokens,
        completion_tokens,
        cost_cents,
    )


def _validate_schema(result: dict[str, Any], schema: type[BaseModel] | None) -> dict[str, Any]:
    if schema is None:
        return result
    try:
        parsed = schema.model_validate(result)
        return parsed.model_dump()
    except ValidationError as e:
        raise ValueError(f"AI 返回内容未通过 schema 校验: {e}") from e


# ===================== Mock 数据 =====================
# mock 模式下，按 prompt 里的关键字分发，返回结构化结果

_MOCK_RESUME = {
    "name": "张三",
    "phone": "13800000001",
    "email": "zhangsan@example.com",
    "years_exp": 5,
    "education": "本科",
    "major": "计算机科学与技术",
    "current_company": "示例科技有限公司",
    "current_title": "Python 后端开发工程师",
    "skills": ["Python", "FastAPI", "MySQL", "Docker", "LangChain"],
    "work_experience": [
        {
            "company": "示例科技A",
            "title": "后端开发",
            "start": "2021-03",
            "end": "至今",
            "desc": "负责招聘平台后端开发与维护",
        }
    ],
    "project_experience": [
        {
            "name": "智能简历解析服务",
            "role": "主程",
            "desc": "基于 LLM 的简历结构化解析，支撑日均 1w+ 解析",
            "tech": ["FastAPI", "LangChain", "MySQL"],
        }
    ],
    "self_evaluation": "5 年后端开发经验，专注 Python / AI 应用落地",
}

_MOCK_JD = {
    "title": "Python 后端开发工程师",
    "company": "示例科技",
    "location": "北京",
    "salary_range": "20k-35k",
    "experience_requirement": "3-5年",
    "education_requirement": "本科及以上",
    "responsibilities": ["负责后端服务开发", "参与系统架构设计", "配合 AI 团队落地能力"],
    "required_skills": ["Python", "FastAPI", "MySQL", "Docker"],
    "nice_to_have": ["LangChain", "RAG 经验", "多智能体框架"],
    "keywords": ["Python", "FastAPI", "AI", "RAG", "Agent"],
}

_MOCK_MATCH = {
    "match_score": 82,
    "summary": "技术栈高度匹配，有 AI 项目经验，建议推进面试",
    "strengths": ["具备 LLM 应用落地经验", "熟练 FastAPI + MySQL", "项目经验与岗位契合"],
    "gaps": ["缺少大规模高并发经验", "未体现多智能体项目经验"],
    "risk_points": ["薪资可能略高于预算"],
    "dimension_scores": {"skills": 90, "experience": 80, "education": 75, "industry": 85},
    "recommendation": "推荐",
}

_MOCK_OPTIMIZE = {
    "overall": "突出 AI / RAG 相关经验，量化项目成果，对齐岗位关键词",
    "sections": [
        {"section": "技能", "suggestions": ["补充 LangChain / RAG / Agent 关键词", "删除'精通 Office'等无效项"]},
        {"section": "项目", "suggestions": ["增加数据指标量化：QPS、准确率", "突出与 JD 相关的责任"]},
        {"section": "工作经历", "suggestions": ["统一时间格式 YYYY-MM", "按 STAR 法则改写"]},
    ],
    "keywords_to_add": ["RAG", "Agent", "向量检索", "Prompt 工程"],
    "keywords_to_remove": ["精通 Office", "良好的沟通能力"],
    "format_tips": ["保持一页", "使用动词开头", "技术栈分行清晰列出"],
}

_MOCK_INTERVIEW = {
    "basic": [
        {
            "q": "请做一段 2 分钟的自我介绍",
            "intent": "表达与逻辑",
            "ref_answer": "突出 Python 后端 + AI 应用落地经验，按时间倒序讲项目",
        },
        {"q": "为什么看这个机会？", "intent": "动机", "ref_answer": "结合 AI 方向兴趣 + 公司业务理解"},
    ],
    "project": [
        {
            "q": "挑一个最有挑战的项目，讲讲你做了什么？",
            "intent": "问题解决 / 影响力",
            "ref_answer": "智能简历解析服务：拆解准确率/性能/成本，给出量化数据",
        },
    ],
    "tech": [
        {
            "q": "FastAPI 的依赖注入是怎么实现的？",
            "intent": "框架理解",
            "ref_answer": "Depends + 嵌套子依赖，结合 yield 处理资源",
        },
        {
            "q": "RAG 的核心链路是什么？召回效果差怎么排查？",
            "intent": "RAG 实战",
            "ref_answer": "解析 -> 分块 -> 嵌入 -> 召回 -> 重排 -> 生成；从分块/嵌入/召回分段排查",
        },
    ],
    "scenario": [
        {
            "q": "让你从 0 设计简历解析服务，如何兼顾准确率与成本？",
            "intent": "系统设计",
            "ref_answer": "小模型兜底 + LLM 精修；异步队列 + 缓存；Prompt 模板化",
        },
    ],
}


_MOCK_INTENT = {
    "intent": "full_analysis",
    "confidence": 0.95,
    "analysis_type": "full_analysis",
    "reason": "用户上传了简历和JD，需要全链路分析",
    "required_steps": [
        "intent_recognition",
        "resume_parse",
        "jd_parse",
        "task_planning",
        "knowledge_retrieval",
        "matching_analysis",
        "resume_optimization",
        "interview_question_generation",
        "self_check",
        "final_report",
    ],
    "focus_points": ["技能匹配", "项目经验", "学历要求", "职业发展"],
}

_MOCK_PLAN = [
    {
        "step_name": "knowledge_retrieval",
        "description": "检索岗位能力模型和面试题库",
        "depends_on": [],
        "expected_output": "知识切片列表",
    },
    {
        "step_name": "matching_analysis",
        "description": "分析简历与JD匹配度",
        "depends_on": ["knowledge_retrieval"],
        "expected_output": "匹配度评分和维度分析",
    },
    {
        "step_name": "resume_optimization",
        "description": "生成简历优化建议",
        "depends_on": ["matching_analysis"],
        "expected_output": "具体优化建议",
    },
    {
        "step_name": "interview_question_generation",
        "description": "生成面试题",
        "depends_on": ["matching_analysis"],
        "expected_output": "四类面试题",
    },
    {
        "step_name": "self_check",
        "description": "自我校验分析质量",
        "depends_on": ["matching_analysis", "resume_optimization", "interview_question_generation"],
        "expected_output": "校验报告",
    },
]

_MOCK_SELF_CHECK = {
    "passed": True,
    "score": 85,
    "issues": [],
    "improvement": {"overall": "内容完整，逻辑清晰", "details": []},
    "retry_needed": False,
    "summary": "分析结果完整且具体，质量良好",
}

_MOCK_FINAL_REPORT = {
    "report_title": "岗位匹配度综合分析报告",
    "summary": {
        "candidate_name": "张三",
        "target_position": "Python 后端开发工程师",
        "target_company": "示例科技",
        "match_score": 82,
        "overall_evaluation": "技术栈高度匹配，具备 AI 项目经验，建议推进面试",
        "recommendation": "推荐",
    },
    "match_analysis": {
        "score": 82,
        "strengths": ["熟练 FastAPI + MySQL", "具备 LLM/RAG 应用经验", "项目经验与岗位契合"],
        "gaps": ["缺少大规模高并发经验", "未体现多智能体项目经验"],
        "dimension_scores": {"skills": 90, "experience": 80, "education": 75, "industry": 85},
    },
    "optimization_suggestions": {
        "key_points": ["突出 RAG/Agent 经验", "量化项目成果（QPS、准确率）"],
        "quick_wins": ["补充 LangChain 关键词", "统一时间格式 YYYY-MM", "删除无效技能词"],
    },
    "interview_guide": {
        "key_questions_count": 4,
        "focus_areas": ["RAG 实战经验", "系统设计能力", "AI 落地经验"],
        "weakness_preparation": "针对高并发经验短板，准备压测和优化的案例",
    },
    "development_advice": {
        "short_term": ["补充向量数据库实战经验", "完善 Agent 框架项目"],
        "long_term": ["向 AI 架构师方向发展", "积累大规模系统设计经验"],
    },
    "quality_assurance": {
        "self_check_score": 85,
        "issues": [],
    },
}


# ===================== 多智能体 Mock 数据（第四阶段）=====================


def _wrap_json(data: Any) -> str:
    """把 dict/list 包装成 ```json``` 文本，模拟 LLM 返回格式"""
    return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"


_MOCK_AGENT_RESUME = {
    "basic_info": {
        "name": "张三",
        "years_exp": 5,
        "skills": ["Python", "FastAPI", "MySQL", "Docker", "LangChain"],
        "current_title": "Python 后端开发工程师",
        "education": "本科",
        "major": "计算机科学与技术",
    },
    "strengths": [
        {"aspect": "技术栈匹配", "detail": "熟练 Python 后端主流框架，契合岗位要求"},
        {"aspect": "AI 落地经验", "detail": "有 LLM/RAG 项目实战，稀缺加分项"},
    ],
    "weaknesses": [
        {
            "aspect": "成果量化",
            "severity": "高",
            "detail": "项目描述缺少数据指标",
            "suggestion": "补充 QPS、准确率、降本比例等量化结果",
        },
        {
            "aspect": "无效技能词",
            "severity": "中",
            "detail": "罗列'精通 Office'等弱相关项",
            "suggestion": "删除并替换为 RAG/Agent 等岗位关键词",
        },
    ],
    "expression_quality": {
        "score": 75,
        "issues": ["部分经历用被动语态", "动词使用单调"],
        "tips": ["统一用动词开头", "按 STAR 法则改写项目"],
    },
    "missing_keywords": ["RAG", "Agent", "向量检索", "高并发"],
    "format_score": 78,
    "format_tips": ["保持一页", "技术栈分行清晰列出", "统一时间格式 YYYY-MM"],
    "overall_assessment": "技术基础扎实、AI 经验突出，主要短板是成果未量化与关键词缺失，优化后竞争力强。",
    "optimization_priority": [
        {"item": "量化项目成果", "reason": "直接影响匹配度与面试说服力"},
        {"item": "补充岗位关键词", "reason": "提升简历过筛率"},
    ],
}

_MOCK_AGENT_JOB = {
    "position_info": {
        "title": "Python 后端开发工程师",
        "company": "示例科技",
        "location": "北京",
        "salary_range": "20k-35k",
    },
    "required_skills": [
        {"skill": "Python", "level": "精通", "importance": "核心"},
        {"skill": "FastAPI", "level": "熟练", "importance": "核心"},
        {"skill": "MySQL", "level": "熟练", "importance": "重要"},
        {"skill": "Docker", "level": "了解", "importance": "加分"},
        {"skill": "RAG/LangChain", "level": "熟练", "importance": "加分"},
    ],
    "responsibilities": [
        {"responsibility": "负责后端服务开发与维护", "weight": "主要"},
        {"responsibility": "参与系统架构设计", "weight": "主要"},
        {"responsibility": "配合 AI 团队落地能力", "weight": "辅助"},
    ],
    "hidden_requirements": [
        {"requirement": "具备高并发系统经验", "reason": "JD 强调系统架构设计"},
        {"requirement": "AI 工程化能力", "reason": "需配合 AI 团队落地"},
    ],
    "experience_requirement": {"years": "3-5年", "industry": "互联网/AI", "background": "后端开发"},
    "education_requirement": "本科及以上",
    "key_challenges": ["AI 能力工程化落地", "系统性能与成本平衡"],
    "career_path": "后端工程师 → 高级后端 → 技术专家/架构师",
    "company_insight": "AI 方向投入较大，业务处于成长期，技术挑战与成长空间并存。",
    "overall_assessment": "典型 Python 后端 + AI 融合岗位，核心看重工程能力与 AI 落地经验。",
}

_MOCK_AGENT_MATCH = {
    "match_score": 82,
    "dimension_scores": {
        "skills": {
            "score": 90,
            "analysis": "核心技术栈高度吻合",
            "matched": ["Python", "FastAPI", "MySQL"],
            "missing": ["大规模高并发"],
        },
        "experience": {"score": 80, "analysis": "5 年经验符合 3-5 年要求"},
        "education": {"score": 75, "analysis": "本科学历达标"},
        "industry": {"score": 85, "analysis": "AI 行业背景契合"},
    },
    "strengths": [
        {"item": "AI/RAG 实战经验", "impact": "直接命中加分项", "evidence": "智能简历解析服务项目"},
        {"item": "技术栈吻合", "impact": "可快速上手", "evidence": "Python+FastAPI+MySQL"},
    ],
    "gaps": [
        {"item": "缺少高并发经验", "severity": "中", "impact": "架构题可能受限", "action": "准备压测与性能优化案例"},
    ],
    "risk_points": ["薪资预期可能略高于预算"],
    "recommendation": "推荐投递",
    "overall_evaluation": "候选人技术与岗位高度匹配，AI 经验为突出亮点，建议推进面试，重点考察高并发与系统设计。",
}

_MOCK_AGENT_INTERVIEW = {
    "tech_questions": [
        {
            "question": "FastAPI 依赖注入的实现原理？",
            "focus": "框架理解",
            "difficulty": "中等",
            "expected_answer": "Depends + 子依赖树 + yield 资源管理",
            "preparation_tips": "结合源码理解作用域",
        },
        {
            "question": "RAG 召回效果差如何排查？",
            "focus": "RAG 实战",
            "difficulty": "困难",
            "expected_answer": "分块/嵌入/召回/重排分段定位",
            "preparation_tips": "准备一次真实调优经历",
        },
    ],
    "project_questions": [
        {
            "question": "简历解析服务如何兼顾准确率和成本？",
            "target_project": "智能简历解析服务",
            "focus": "系统设计/权衡",
            "expected_answer": "小模型兜底 + LLM 精修 + 缓存",
        },
    ],
    "hr_questions": [
        {
            "question": "为什么选择这个机会？",
            "focus": "动机与稳定性",
            "risk_point": "跳槽频率",
            "suggested_answer": "结合 AI 方向兴趣与公司业务",
        },
    ],
    "scenario_questions": [
        {
            "question": "QPS 突增 10 倍如何保障服务稳定？",
            "scenario": "流量高峰",
            "focus": "高并发设计",
            "evaluation_criteria": "限流/缓存/扩容/降级是否完整",
        },
    ],
    "total_questions": 5,
    "preparation_strategy": "以 AI 项目为主线讲故事，补强高并发与系统设计短板。",
    "weakness_areas": ["高并发架构", "大规模数据处理"],
    "confidence_boost": "突出稀缺的 RAG/Agent 落地经验建立差异化优势。",
}

_MOCK_AGENT_CAREER = {
    "current_status": {
        "level": "中级后端工程师",
        "strengths": ["Python 工程能力", "AI 落地经验"],
        "development_areas": ["高并发架构", "系统设计"],
        "career_stage": "成长期",
    },
    "skill_gaps": [
        {
            "skill": "高并发/分布式",
            "priority": "高",
            "current_level": "了解",
            "target_level": "熟练",
            "acquisition_method": "项目实战 + 系统设计课程",
        },
        {
            "skill": "多智能体框架",
            "priority": "中",
            "current_level": "了解",
            "target_level": "熟练",
            "acquisition_method": "开源项目贡献",
        },
    ],
    "learning_roadmap": [
        {
            "phase": "夯实基础",
            "duration": "1-3个月",
            "focus": "高并发与缓存",
            "resources": ["《设计数据密集型应用》", "Redis 实战"],
            "milestone": "完成一个高并发 Demo",
        },
        {
            "phase": "深入 AI 工程",
            "duration": "3-6个月",
            "focus": "RAG/Agent 工程化",
            "resources": ["LangGraph 文档", "向量数据库实战"],
            "milestone": "落地一个多智能体项目",
        },
    ],
    "project_recommendations": [
        {
            "project": "高并发短链服务",
            "reason": "补强高并发短板",
            "tech_stack": ["FastAPI", "Redis", "MySQL"],
            "complexity": "中等",
        },
    ],
    "short_term_plan": {"timeline": "1-3个月", "goals": ["补齐高并发知识"], "actions": ["完成压测实验"]},
    "mid_term_plan": {"timeline": "3-12个月", "goals": ["主导一个 AI 项目"], "actions": ["落地多智能体系统"]},
    "long_term_plan": {"timeline": "1-3年", "goals": ["成长为技术专家"], "career_direction": "AI 应用架构师"},
    "overall_advice": "以 AI 工程为差异化主线，同步补齐高并发与系统设计能力，向 AI 架构方向发展。",
}

_MOCK_AGENT_SUMMARY = {
    "report_title": "智能招聘综合分析报告",
    "generated_at": "2026-06-06",
    "summary": {
        "candidate": "张三",
        "target_position": "Python 后端开发工程师",
        "target_company": "示例科技",
        "match_score": 82,
        "verdict": "技术与岗位高度匹配，建议推进面试",
    },
    "resume_diagnosis": {
        "score": 78,
        "key_findings": ["技术栈契合", "AI 经验突出", "成果未量化"],
        "top_improvements": ["量化项目成果", "补充岗位关键词", "删除无效技能词"],
    },
    "job_analysis": {
        "position_summary": "Python 后端 + AI 融合岗位",
        "core_skills": ["Python", "FastAPI", "MySQL", "RAG"],
        "hidden_demands": ["高并发经验", "AI 工程化能力"],
    },
    "match_result": {
        "score": 82,
        "verdict": "推荐投递",
        "strengths_summary": "技术栈吻合且具备 AI 实战经验",
        "gaps_summary": "缺少大规模高并发经验",
    },
    "interview_preparation": {
        "questions_count": 5,
        "focus_areas": ["RAG 实战", "系统设计", "高并发"],
        "key_advice": "以 AI 项目为主线，补强高并发短板",
    },
    "career_plan": {
        "short_term": "补齐高并发知识，完成压测实验",
        "mid_term": "主导落地一个多智能体 AI 项目",
        "long_term": "成长为 AI 应用架构师",
    },
    "action_items": [
        {"priority": "高", "action": "量化简历项目成果", "reason": "提升匹配度与面试说服力"},
        {"priority": "高", "action": "准备高并发与系统设计案例", "reason": "弥补面试短板"},
        {"priority": "中", "action": "补充 RAG/Agent 关键词", "reason": "提升过筛率"},
    ],
    "next_steps": ["按建议优化简历", "投递目标岗位", "按学习路线补强高并发"],
}


_MOCK_DISPATCH = {
    "intent": "full",
    "target_agents": ["ResumeAgent", "JobAgent", "MatchAgent", "InterviewAgent", "CareerAgent"],
    "reason": "（mock）需求较综合，默认启动全部 5 个子智能体进行全面分析",
    "user_profile": "在职跳槽者",
    "notes": "",
}


def _mock_chat(prompt: str) -> str:
    """根据 prompt 关键字返回对应 mock JSON，包裹在 ```json``` 里"""
    # ---- 智能调度层：意图路由（优先级最高）----
    if "智能调度专家" in prompt:
        return _wrap_json(_MOCK_DISPATCH)

    # ---- 第四阶段：6 个智能体（按角色关键词精确匹配）----
    if "资深简历诊断专家" in prompt:
        return _wrap_json(_MOCK_AGENT_RESUME)
    if "资深招聘分析师" in prompt:
        return _wrap_json(_MOCK_AGENT_JOB)
    if "资深职业匹配专家" in prompt:
        return _wrap_json(_MOCK_AGENT_MATCH)
    if "资深面试辅导专家" in prompt:
        return _wrap_json(_MOCK_AGENT_INTERVIEW)
    if "资深职业规划师" in prompt:
        return _wrap_json(_MOCK_AGENT_CAREER)
    if "主控专家" in prompt:
        return _wrap_json(_MOCK_AGENT_SUMMARY)

    # ---- 第三阶段：Agentic RAG 工作流 + 基础解析 ----
    if "意图识别专家" in prompt:
        data = _MOCK_INTENT
    elif "任务规划专家" in prompt:
        data = _MOCK_PLAN
    elif "AI 输出质量审核专家" in prompt:
        data = _MOCK_SELF_CHECK
    elif "汇总为一份完整报告" in prompt:
        data = _MOCK_FINAL_REPORT
    elif "简历文本" in prompt:
        data = _MOCK_RESUME
    elif "JD 文本" in prompt:
        data = _MOCK_JD
    elif "匹配度分析" in prompt:
        data = _MOCK_MATCH
    elif "简历修改建议" in prompt:  # OPTIMIZE_PROMPT 正文关键词（原 "简历优化" 仅在 docstring，无法命中）
        data = _MOCK_OPTIMIZE
    elif "资深技术面试官" in prompt:  # INTERVIEW_PROMPT 正文关键词（原 "生成面试题" 不连续，无法命中）
        data = _MOCK_INTERVIEW
    else:
        data = {"result": "mock"}
    return _wrap_json(data)


# ===================== 真实 LLM 调用 =====================


def _openai_compatible_chat(prompt: str, base_url: str = None, *, json_mode: bool = True, model: str = None) -> str:
    """
    OpenAI 兼容协议调用（OpenAI / Qwen 兼容模式）
    用 requests 减少 SDK 依赖；生产可换成 openai SDK。
    """
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 未配置，请检查 .env 文件")

    base = base_url or settings.LLM_BASE_URL or "https://api.openai.com/v1"
    url = f"{base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是严谨的助手，输出尽量使用 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    def _do():
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=settings.LLM_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            _record_usage(data.get("usage"), model=payload["model"])
            return data["choices"][0]["message"]["content"]
        except requests.Timeout as e:
            raise _RetryableLLMError(f"AI 请求超时（{settings.LLM_TIMEOUT}s）") from e
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            # 仅对限流 / 5xx 这类可恢复错误重试；4xx（鉴权/参数）直接失败
            if status == 429:
                raise _RetryableLLMError(f"AI 接口调用被限流(HTTP {status})") from e
            if 500 <= status < 600:
                raise _RetryableLLMError(f"AI 接口服务端错误(HTTP {status})") from e
            if status in (401, 403):
                raise LLMAuthError(f"AI 接口鉴权失败(HTTP {status}): {str(e)}") from e
            raise RuntimeError(f"AI 接口调用失败: {str(e)}") from e
        except requests.RequestException as e:
            raise _RetryableLLMError(f"AI 接口调用失败: {str(e)}") from e
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise LLMParseError(f"AI 返回格式异常: {str(e)}") from e

    try:
        return retry_call(
            _do,
            max_retries=_LLM_MAX_RETRIES,
            retryable_exceptions=(_RetryableLLMError,),
            log_prefix="LLM",
        )
    except RuntimeError as e:
        err_msg = str(e)
        if "超时" in err_msg:
            raise LLMTimeoutError(f"AI 调用超时，请稍后重试: {err_msg}") from e
        if "限流" in err_msg:
            raise LLMRateLimitError(f"AI 调用被限流，请稍后重试: {err_msg}") from e
        raise LLMProviderError(f"AI 调用失败: {err_msg}") from e


def _local_chat(prompt: str, *, json_mode: bool = True) -> str:
    """本地模型占位（如 Ollama / vLLM 暴露 OpenAI 兼容端点时复用 _openai_compatible_chat）"""
    local_base = settings.LLM_BASE_URL or "http://localhost:11434/v1"
    return _openai_compatible_chat(prompt, base_url=local_base, json_mode=json_mode)


def _simplify_prompt(prompt: str) -> str:
    if len(prompt or "") <= _SIMPLIFIED_PROMPT_MAX_CHARS:
        return prompt
    return (
        "以下输入已因上游 LLM 调用失败而自动截断，请优先保留核心约束并输出合法 JSON。\n\n"
        + (prompt or "")[:_SIMPLIFIED_PROMPT_MAX_CHARS]
    )


def _call_with_fallbacks(primary_call: Callable[[str, str | None], str], prompt: str) -> str:
    """LLM fallback chain: primary model -> fallback model -> simplified prompt -> mock (dev only)."""
    errors: list[str] = []
    attempts: list[tuple[str, str, str | None]] = [("primary", prompt, None)]
    fallback_model = (settings.LLM_FALLBACK_MODEL or "").strip()
    if fallback_model and fallback_model != settings.LLM_MODEL:
        attempts.append(("fallback_model", prompt, fallback_model))
    if len(prompt or "") > _SIMPLIFIED_PROMPT_MAX_CHARS:
        attempts.append(("simplified_prompt", _simplify_prompt(prompt), fallback_model or None))

    for label, candidate_prompt, model in attempts:
        try:
            if label != "primary":
                logger.warning("LLM fallback attempt=%s model=%s", label, model or settings.LLM_MODEL)
            return primary_call(candidate_prompt, model)
        except (RuntimeError, LLMProviderError) as exc:
            errors.append(f"{label}: {exc}")

    if provider_allows_mock_fallback():
        logger.warning("LLM fallback attempt=mock after failures: %s", " | ".join(errors)[-500:])
        return _mock_chat(prompt)

    raise LLMProviderError("AI 调用失败，fallback 链路均未成功: " + " | ".join(errors)[-800:])


def provider_allows_mock_fallback() -> bool:
    """生产环境默认禁止回退到 mock；开发环境可通过 LLM_ALLOW_MOCK_FALLBACK=true 显式开启。"""
    if settings.is_production:
        return bool(settings.LLM_ALLOW_MOCK_FALLBACK)
    return str(settings.LLM_FALLBACK_MODEL or "").strip().lower() == "mock" or bool(settings.LLM_ALLOW_MOCK_FALLBACK)


# ===================== 对外统一接口 =====================


def chat_json(prompt: str, schema: type[BaseModel] | None = None) -> dict[str, Any]:
    """
    唯一对外接口：输入 prompt，输出解析后的 dict
    - mock：本地模板，无网络
    - openai / qwen / local：走 OpenAI 兼容协议

    异常处理：
    - AI 调用失败 → 抛 RuntimeError
    - 返回内容非合法 JSON → 尝试提取，仍失败抛 ValueError
    """
    provider = (settings.LLM_PROVIDER or "mock").lower()
    trace_context = _consume_llm_trace_context()
    prompt_metadata = dict(trace_context.get("prompt_metadata") or {})
    prompt_version = prompt_metadata.get("prompt_version") or trace_context.get("prompt_version") or "unknown"
    prompt_name = prompt_metadata.get("prompt_name") or trace_context.get("prompt_name")
    prompt_family = prompt_metadata.get("prompt_family") or trace_context.get("prompt_family")
    source = trace_context.get("source") or "llm_service.chat_json"
    request_id = trace_context.get("request_id") or get_request_id()
    trace_enabled = bool(trace_context.get("trace_enabled", True))
    trace_db = trace_context.get("db")
    trace_user_id = trace_context.get("user_id")
    trace_resume_id = trace_context.get("resume_id")
    trace_jd_id = trace_context.get("jd_id")
    trace_task_id = trace_context.get("task_id")
    trace_analysis_record_id = trace_context.get("analysis_record_id")
    trace_extra = {
        key: value
        for key, value in trace_context.items()
        if key
        not in {
            "source",
            "prompt_version",
            "prompt_name",
            "prompt_family",
            "request_id",
            "trace_enabled",
            "db",
            "user_id",
            "resume_id",
            "jd_id",
            "task_id",
            "analysis_record_id",
            "prompt_metadata",
        }
    }
    usage_before = get_llm_usage()

    def persist_trace(
        *,
        status: str,
        response_text: str | None = None,
        response_json: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        """Persist success and failure traces without affecting the LLM request result."""
        if not trace_enabled:
            return
        usage_after = get_llm_usage()
        call_usage = {
            key: max(0.0, float(usage_after.get(key, 0.0)) - float(usage_before.get(key, 0.0)))
            for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_cents")
        }
        try:
            from app.services.prompt_trace_service import build_trace_context, record_prompt_trace

            record_prompt_trace(
                prompt=prompt,
                response_text=response_text,
                response_json=response_json,
                provider=provider,
                model=settings.LLM_MODEL,
                prompt_version=prompt_version,
                source=source,
                prompt_name=prompt_name,
                prompt_family=prompt_family,
                status=status,
                cache_hit=False,
                duration_ms=int((time.time() - start_ts) * 1000),
                prompt_tokens=int(call_usage["prompt_tokens"]),
                completion_tokens=int(call_usage["completion_tokens"]),
                total_tokens=int(call_usage["total_tokens"]),
                cost_cents=call_usage["cost_cents"],
                error_message=error_message[:2000] if error_message else None,
                user_id=trace_user_id,
                resume_id=trace_resume_id,
                jd_id=trace_jd_id,
                task_id=trace_task_id,
                analysis_record_id=trace_analysis_record_id,
                trace_context=build_trace_context(
                    source=source,
                    prompt_name=prompt_name,
                    prompt_family=prompt_family,
                    request_id=request_id,
                    user_id=trace_user_id,
                    resume_id=trace_resume_id,
                    jd_id=trace_jd_id,
                    task_id=trace_task_id,
                    analysis_record_id=trace_analysis_record_id,
                    extra=trace_extra,
                ),
                prompt_metadata=prompt_metadata,
                db=trace_db,
            )
        except Exception:
            logger.exception("failed to persist prompt trace")

    # ---- 0) 查缓存（命中则返回深拷贝，避免调用方改动污染缓存）----
    key = _cache_key(provider, prompt)
    with _LLM_CACHE_LOCK:
        cached = _LLM_CACHE.get(key)
        if cached is not None:
            _LLM_CACHE.move_to_end(key)  # LRU：命中刷新到最新
            return _validate_schema(copy.deepcopy(cached), schema)

    start_ts = time.time()

    # ---- 1) 调用 AI 获取原始文本 ----
    try:
        if provider == "mock":
            raw = _mock_chat(prompt)
        elif provider in ("openai", "qwen"):
            raw = _call_with_fallbacks(
                lambda candidate_prompt, model: _openai_compatible_chat(candidate_prompt, json_mode=True, model=model),
                prompt,
            )
        elif provider == "local":
            raw = _call_with_fallbacks(
                lambda candidate_prompt, model: _openai_compatible_chat(
                    candidate_prompt,
                    base_url=settings.LLM_BASE_URL or "http://localhost:11434/v1",
                    json_mode=True,
                    model=model,
                ),
                prompt,
            )
        else:
            raise ValueError(f"unknown LLM_PROVIDER: {provider}")
    except LLMProviderError as e:
        error_type = type(e).__name__
        duration_seconds = time.time() - start_ts
        record_llm_error(provider=provider, model=settings.LLM_MODEL, error_type=error_type)
        record_llm_request(provider=provider, model=settings.LLM_MODEL, duration_seconds=duration_seconds)
        persist_trace(status="failed", error_message=str(e))
        raise  # 直接向上冒泡，保留类型化异常
    except RuntimeError as e:
        duration_seconds = time.time() - start_ts
        record_llm_error(provider=provider, model=settings.LLM_MODEL, error_type="RuntimeError")
        record_llm_request(provider=provider, model=settings.LLM_MODEL, duration_seconds=duration_seconds)
        persist_trace(status="failed", error_message=str(e))
        raise LLMProviderError(f"AI 调用失败: {str(e)}") from e
    except Exception as e:
        duration_seconds = time.time() - start_ts
        record_llm_error(provider=provider, model=settings.LLM_MODEL, error_type=type(e).__name__)
        record_llm_request(provider=provider, model=settings.LLM_MODEL, duration_seconds=duration_seconds)
        persist_trace(status="failed", error_message=str(e))
        raise LLMProviderError(f"AI 调用异常: {str(e)}") from e

    # 成功时记录指标
    duration_seconds = time.time() - start_ts
    record_llm_request(provider=provider, model=settings.LLM_MODEL, duration_seconds=duration_seconds)

    # ---- 2) 将 AI 返回文本解析为 JSON ----
    try:
        result = extract_json(raw)
    except ValueError as exc:
        persist_trace(status="failed", response_text=raw, error_message=str(exc))
        # 尝试兜底：AI 说了"抱歉"之类非 JSON 内容。
        # 注意：不要把 raw 原始响应片段拼进错误信息——它会沿外部 API 的错误路径
        # 原样回给调用方，造成 LLM 返回内容泄漏；raw 已由 persist_trace 落库留痕。
        raise ValueError("AI 返回内容不是合法 JSON，无法解析") from exc
    try:
        result = _validate_schema(result, schema)
    except ValueError as exc:
        persist_trace(status="failed", response_text=raw, error_message=str(exc))
        raise
    persist_trace(status="success", response_text=raw, response_json=result)

    # ---- 3) 写入缓存（带容量上限的 LRU 淘汰）----
    with _LLM_CACHE_LOCK:
        _LLM_CACHE[key] = copy.deepcopy(result)
        if len(_LLM_CACHE) > _LLM_CACHE_MAX:
            _LLM_CACHE.popitem(last=False)  # 淘汰最久未用
    return result


# ===================== Function Calling (Tool Use) =====================


def _openai_compatible_chat_with_tools(
    messages: list,
    tools: list = None,
) -> dict:
    """支持 tool_calling 的 OpenAI 兼容 API 调用。

    参数:
        messages: OpenAI 格式的消息列表 [{"role": "...", "content": "..."}, ...]
        tools:    OpenAI 格式的工具定义列表（Tool.to_openai_tool() 的输出）

    返回:
        API 完整响应 dict（包含 choice[0].message 和可能的 tool_calls）

    异常:
        RuntimeError — API 调用失败或返回格式异常
    """
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 未配置，请检查 .env 文件")

    base = settings.LLM_BASE_URL or "https://api.openai.com/v1"
    url = f"{base.rstrip('/')}/chat/completions"
    payload: dict = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    def _do():
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=settings.LLM_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.Timeout as e:
            raise _RetryableLLMError(f"AI 请求超时（{settings.LLM_TIMEOUT}s）") from e
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 429 or 500 <= status < 600:
                raise _RetryableLLMError(f"AI 接口调用失败(HTTP {status})") from e
            raise RuntimeError(f"AI 接口调用失败: {str(e)}") from e
        except requests.RequestException as e:
            raise _RetryableLLMError(f"AI 接口调用失败: {str(e)}") from e
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"AI 返回格式异常: {str(e)}") from e

    try:
        return retry_call(
            _do,
            max_retries=_LLM_MAX_RETRIES,
            retryable_exceptions=(_RetryableLLMError,),
            log_prefix="LLM-Tools",
        )
    except RuntimeError as e:
        raise RuntimeError(f"{e}，请稍后重试") from e


def chat_with_tools(
    prompt: str,
    tools: list = None,
    system_prompt: str = None,
    max_tool_rounds: int = 5,
) -> dict:
    """支持工具调用的 LLM 对话 — 循环调用直到 LLM 返回最终 JSON。

    工作流程:
        LLM 生成 → 解析 tool_calls → 执行工具 → 结果注回 → 重复 → 最终 JSON

    参数:
        prompt:         用户输入的 prompt 文本
        tools:          Tool 对象列表（来自 app.agents.tools.list_tools()）
        system_prompt:  系统角色提示。为 None 时使用默认提示
        max_tool_rounds: 最大工具调用轮次（防无限循环），默认 5

    返回:
        LLM 最终返回的 JSON dict。若超过最大轮次仍无 JSON，尝试从最后一条消息提取。

    异常:
        RuntimeError — 所有 provider 都失败
        ValueError   — 最终响应无法解析为 JSON

    注意:
        - mock provider 不支持工具调用，降级为 chat_json(prompt)
        - 工具调用有状态，不参与 LLM 结果缓存
    """
    provider = (settings.LLM_PROVIDER or "mock").lower()

    # ---- mock 无工具能力，降级 ----
    if provider == "mock":
        logger.info("[chat_with_tools] mock provider 不支持工具调用，降级为 chat_json")
        return chat_json(prompt)

    # ---- 准备工具定义（OpenAI 格式）----
    tool_defs = None
    tool_map = {}  # name → Tool 对象，用于执行回调
    if tools:
        tool_defs = [t.to_openai_tool() if isinstance(t, Tool) else t for t in tools]
        for t in tools:
            t.name if isinstance(t, Tool) else t.get("function", {}).get("name", "")
            if isinstance(t, Tool):
                tool_map[t.name] = t
            elif isinstance(t, dict):
                # 从纯 dict 定义中通过 get_tool 查找
                fn_name = (t.get("function") or {}).get("name", "")
                resolved = get_tool(fn_name)
                if resolved:
                    tool_map[fn_name] = resolved

    # ---- 构建消息序列 ----
    if system_prompt is None:
        system_prompt = (
            "你是智能招聘系统的专业分析助手。你可以使用提供的工具获取信息。\n"
            "请合理调用工具来收集所需信息，然后综合工具返回的结果给出最终分析。\n"
            "最终回复必须是一个合法的 JSON 对象（不包裹 markdown 代码块），"
            "包含你所有分析结果。"
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    # ---- 主循环：工具调用 ↔ LLM 推理 ----
    for _round in range(max_tool_rounds):
        response = _openai_compatible_chat_with_tools(messages, tools=tool_defs)
        choice = response["choices"][0]
        msg = choice["message"]

        # 情况 A: LLM 选择直接回复（无工具调用）
        if not msg.get("tool_calls"):
            content = msg.get("content", "")
            if content and content.strip():
                return extract_json(content)
            # content 为空但也没 tool_calls → 异常
            raise ValueError(f"LLM 返回空内容且无工具调用 (finish_reason={choice.get('finish_reason')})")

        # 情况 B: LLM 请求调用工具
        assistant_msg = {"role": "assistant", "content": msg.get("content")}
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        messages.append(assistant_msg)

        for tc in msg["tool_calls"]:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            logger.info(
                "[chat_with_tools] round=%d tool=%s args=%s",
                _round + 1,
                fn_name,
                fn_args,
            )

            tool = tool_map.get(fn_name) or get_tool(fn_name)
            if tool:
                result = tool.execute(**fn_args)
                content_str = json.dumps(result, ensure_ascii=False)
            else:
                content_str = json.dumps(
                    {
                        "success": False,
                        "error": f"未知工具 '{fn_name}'，可用工具: {list(tool_map.keys())}",
                    },
                    ensure_ascii=False,
                )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": content_str,
                }
            )

    # ---- 超过最大工具轮次，兜底提取 ----
    logger.warning("[chat_with_tools] 达到最大工具轮次 %d，尝试从最后消息提取 JSON", max_tool_rounds)
    last_content = messages[-1].get("content", "")
    if isinstance(last_content, str) and last_content.strip():
        try:
            return extract_json(last_content)
        except ValueError:
            pass
    raise RuntimeError(f"工具调用超过 {max_tool_rounds} 轮仍未返回有效 JSON，请简化任务或重试")
