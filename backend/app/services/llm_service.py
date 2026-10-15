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
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import requests
from pydantic import BaseModel, ValidationError

from app.agents.tools import Tool, get_tool
from app.core.config import settings
from app.core.llm_quota import charge_if_real_provider
from app.core.prometheus_metrics import (
    record_llm_degraded_response,
    record_llm_error,
    record_llm_request,
    record_prompt_trace_write_failure,
)
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

# Where a response actually came from. `settings.LLM_PROVIDER` only records what
# was *configured*, so a reply served by the mock fallback used to be traced as
# the real provider. This contextvar carries the truth to the trace row and to
# any caller that needs to show a degraded badge.
_LLM_PROVENANCE_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("llm_provenance_context", default=None)

# Only answers straight from the configured primary model may be cached. Caching
# a mock reply would pin fabricated content under a real-looking cache key.
CACHEABLE_RESPONSE_SOURCES = frozenset({"real"})


def _provenance(
    source: str,
    *,
    reason: str | None = None,
    attempts: list[str] | None = None,
    cache_hit: bool = False,
) -> dict[str, Any]:
    return {
        "source": source,
        "degraded": source != "real",
        "reason": reason,
        "attempts": list(attempts or []),
        "cache_hit": cache_hit,
    }


def set_llm_provenance(provenance: dict[str, Any] | None) -> None:
    _LLM_PROVENANCE_CONTEXT.set(dict(provenance) if provenance else None)


def get_llm_provenance() -> dict[str, Any]:
    """Provenance of the most recent chat_json call in this context."""
    return dict(_LLM_PROVENANCE_CONTEXT.get() or _provenance("unknown"))


def reset_llm_provenance() -> None:
    _LLM_PROVENANCE_CONTEXT.set(None)


@dataclass
class LLMTraceScope:
    """一次 LLM 调用的审计落盘：成功、失败、降级都写同一份 prompt_trace。

    `chat_json` 曾经自带这段逻辑（一个 60 行闭包），`chat_with_tools` 一行都没有——
    工具调用节点的输入输出因此完全不在取证链里。两份调用现在共用这个 scope，
    免得又一个"只有一份带这个参数"的 bug。
    """

    prompt: str
    provider: str
    writer: str
    started_at: float
    usage_before: dict[str, float]
    context: dict[str, Any]
    source: str
    prompt_version: str
    prompt_name: str | None
    prompt_family: str | None
    prompt_metadata: dict[str, Any]
    request_id: str | None
    trace_enabled: bool
    db: Any = None
    user_id: int | None = None
    resume_id: int | None = None
    jd_id: int | None = None
    task_id: int | None = None
    analysis_record_id: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def begin(cls, *, prompt: str, provider: str, writer: str) -> "LLMTraceScope":
        """消费当前 trace 上下文并记下调用前的用量（用量差值即本次调用花费）。"""
        context = _consume_llm_trace_context()
        prompt_metadata = dict(context.get("prompt_metadata") or {})
        reserved = {
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
        return cls(
            prompt=prompt,
            provider=provider,
            writer=writer,
            started_at=time.time(),
            usage_before=get_llm_usage(),
            context=context,
            source=context.get("source") or writer,
            prompt_version=prompt_metadata.get("prompt_version") or context.get("prompt_version") or "unknown",
            prompt_name=prompt_metadata.get("prompt_name") or context.get("prompt_name"),
            prompt_family=prompt_metadata.get("prompt_family") or context.get("prompt_family"),
            prompt_metadata=prompt_metadata,
            request_id=context.get("request_id") or get_request_id(),
            trace_enabled=bool(context.get("trace_enabled", True)),
            db=context.get("db"),
            user_id=context.get("user_id"),
            resume_id=context.get("resume_id"),
            jd_id=context.get("jd_id"),
            task_id=context.get("task_id"),
            analysis_record_id=context.get("analysis_record_id"),
            extra={key: value for key, value in context.items() if key not in reserved},
        )

    def call_usage(self) -> dict[str, float]:
        after = get_llm_usage()
        return {
            key: max(0.0, float(after.get(key, 0.0)) - float(self.usage_before.get(key, 0.0)))
            for key in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_cents")
        }

    def persist(
        self,
        *,
        status: str,
        response_text: str | None = None,
        response_json: dict[str, Any] | None = None,
        error_message: str | None = None,
        provenance: dict[str, Any] | None = None,
        cache_hit: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """写取证行；失败只报警不改变调用结果。"""
        if not self.trace_enabled:
            return
        provenance = provenance or _provenance("unknown", cache_hit=cache_hit)
        usage = self.call_usage()
        try:
            from app.services.prompt_trace_service import build_trace_context, record_prompt_trace

            record_prompt_trace(
                prompt=self.prompt,
                response_text=response_text,
                response_json=response_json,
                provider=self.provider,
                model=settings.LLM_MODEL,
                response_source=str(provenance.get("source") or "unknown"),
                degraded=bool(provenance.get("degraded")),
                prompt_version=self.prompt_version,
                source=self.source,
                prompt_name=self.prompt_name,
                prompt_family=self.prompt_family,
                status=status,
                cache_hit=cache_hit or bool(provenance.get("cache_hit")),
                duration_ms=int((time.time() - self.started_at) * 1000),
                prompt_tokens=int(usage["prompt_tokens"]),
                completion_tokens=int(usage["completion_tokens"]),
                total_tokens=int(usage["total_tokens"]),
                cost_cents=usage["cost_cents"],
                error_message=error_message[:2000] if error_message else None,
                user_id=self.user_id,
                resume_id=self.resume_id,
                jd_id=self.jd_id,
                task_id=self.task_id,
                analysis_record_id=self.analysis_record_id,
                trace_context=build_trace_context(
                    source=self.source,
                    prompt_name=self.prompt_name,
                    prompt_family=self.prompt_family,
                    request_id=self.request_id,
                    user_id=self.user_id,
                    resume_id=self.resume_id,
                    jd_id=self.jd_id,
                    task_id=self.task_id,
                    analysis_record_id=self.analysis_record_id,
                    extra={**self.extra, **(extra or {})},
                ),
                prompt_metadata=self.prompt_metadata,
                db=self.db,
            )
        except Exception:
            # A trace row that silently fails to write turns "queryable
            # internally" into a fiction. Count it so the alerting layer can
            # report when the audit trail itself is unreliable.
            record_prompt_trace_write_failure(self.writer)
            logger.exception("failed to persist prompt trace; audit trail is incomplete for this call")

    def record_metrics(self, *, degraded: bool, provenance: dict[str, Any] | None = None) -> None:
        duration_seconds = time.time() - self.started_at
        record_llm_request(provider=self.provider, model=settings.LLM_MODEL, duration_seconds=duration_seconds)
        if degraded:
            record_llm_degraded_response(
                provider=self.provider,
                model=settings.LLM_MODEL,
                response_source=str((provenance or {}).get("source") or "unknown"),
            )
            logger.warning(
                "LLM degraded response provider=%s source=%s reason=%s",
                self.provider,
                (provenance or {}).get("source"),
                str((provenance or {}).get("reason") or "")[-200:],
            )

    def record_failure(self, *, error_type: str, error: BaseException, provenance: dict[str, Any] | None = None):
        duration_seconds = time.time() - self.started_at
        record_llm_error(provider=self.provider, model=settings.LLM_MODEL, error_type=error_type)
        record_llm_request(provider=self.provider, model=settings.LLM_MODEL, duration_seconds=duration_seconds)
        self.persist(status="failed", error_message=str(error), provenance=provenance)


def _cache_key(provider: str, prompt: str, disable_thinking: bool = False) -> str:
    # 同一个 prompt 在"关思考链"与"开思考链"两臂下不是同一个答案：D195 实测同一份简历 prompt
    # 关链给 3 条建议、开链给空 content。所以这个位必须进键，否则一臂的结果会喂给另一臂。
    raw = f"{provider}|{settings.LLM_MODEL}|{int(bool(disable_thinking))}|{prompt}"
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
    # 单价按型号取（`config.unit_costs_for`）：主备是两个不同型号，两个全局数表达不了。
    input_cost, output_cost = settings.unit_costs_for(model)
    cost_cents = (prompt_tokens / 1000.0) * input_cost + (completion_tokens / 1000.0) * output_cost

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
    "dimensions": {
        "metric_ownership": {
            "score": 12,
            "note": "（mock）工作经历那条只写负责什么，没有个人达成数；项目里那个日均量级是团队口径。",
        },
        "interview_hooks": {
            "score": 5,
            "note": "（mock）只有「日均 1w+」一个数字钩子，权衡、边界、踩坑三类都缺，追到第二层没纸可指。",
        },
        "role_fit": {
            "score": 16,
            "note": "（mock）技能写了 LangChain 但项目里没有对应实践，RAG / Agent 两条词表都没出现。",
        },
        "transferability": {
            "score": 10,
            "note": "（mock）技能清单是并列名词，没有选型依据与边界，看不出哪些能做主。",
        },
        "project_depth": {
            "score": 13,
            "note": "（mock）解析服务只有一句「基于 LLM 的结构化解析」，切片口径与失败处理都没写。",
        },
        "expression_structure": {
            "score": 6,
            "note": "（mock）通篇职责陈述句，没有一处结果句；自我评价里的年限与工作经历一致，这点好。",
        },
        "advantage_section": {
            "score": 3,
            "note": "（mock）有独立优势段，但讲覆盖面不讲差异化，没有方法论标签。",
        },
    },
    "missing_keywords": ["RAG", "Agent", "向量检索", "高并发"],
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
    # 这里**没有** `resume_diagnosis`：真 prompt（`AGENT_REPORT_PROMPT`）从没要求过这个键，
    # 而屏幕上那一格现在由 `SummaryAgent` 从 ResumeAgent 的七维结果拼出来（§10.41 ③）。
    # 留着它只会让 mock 演示出一个真链路里不存在的数据来源。
    "summary": {
        "candidate": "张三",
        "target_position": "Python 后端开发工程师",
        "target_company": "示例科技",
        "match_score": 82,
        "verdict": "技术与岗位高度匹配，建议推进面试",
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


_MOCK_REPORT_OVERVIEW = {
    "overall_score": 72,
    "verdict": {
        "direction": "（mock）Python 后端 + AI 应用落地（RAG 方向）",
        "direction_basis": "（mock）未附目标岗位，按简历关键词自动识别",
        "target_level": "中级",
        "level_basis": "（mock）相关工作年限 5 年、计算机强相关、本科，项目为生产级、角色为主程，落在中级区间",
    },
    "dimensions": {
        "metric_ownership": {
            "score": 12,
            "note": "（mock）工作经历那条「负责招聘平台后端开发与维护」只写了负责什么，没有达成数；"
            "项目成果「支撑日均 1w+ 解析」是团队量级，看不出你负责的模块贡献了多少。"
            "补一个你自己达成/优化出来的指标，口径写清楚。",
        },
        "interview_hooks": {
            "score": 5,
            "note": "（mock）钩子只有「日均 1w+」一个数字型钩子，权衡、边界、踩坑三类都没有。"
            "面试官追到第二层就没有纸面上的数可指。",
        },
        "role_fit": {
            "score": 16,
            "note": "（mock）技能区写了 LangChain，但项目技术栈里没有对应实践；"
            "RAG / Agent 两条词表都没出现，方向标签要读完整份简历才判得出。",
            "missing_keywords": ["RAG", "LangGraph", "评测集"],
        },
        "transferability": {
            "score": 10,
            "note": "（mock）技能清单是并列的名词堆，没有选型依据与边界，" "看不出哪些是 L2 能做主、哪些只是 L0 会用。",
        },
        "project_depth": {
            "score": 13,
            "note": "（mock）项目「智能简历解析服务」只有一句「基于 LLM 的结构化解析」，"
            "解析用的切片与字段口径、失败样本怎么处理都没写，约束和代价一处都没有。",
        },
        "expression_structure": {
            "score": 6,
            "note": "（mock）自我评价「5 年后端开发经验，专注 Python / AI 应用落地」与工作经历的"
            "「5 年」一致，这点好；但通篇是职责陈述句，没有一处结果句。",
        },
        "advantage_section": {"score": 3, "note": "（mock）有独立优势段，但讲的是覆盖面不是差异化，没有方法论标签。"},
    },
    "to_next_grade": [
        "① 工作经历那一条补一个你负责并达成的指标（带口径），这一处补上就能过 75",
        "② 项目成果补「优化前 → 优化后」，把「日均 1w+」拆成你负责的那一段",
    ],
    "competition": {
        "positioning_badge": "（mock）B 档（中上）",
        "positioning_note": "（mock）这里评的是背景在同类人里站哪，与七维评级不是一回事："
        "5 年经验加生产级项目是硬的基本盘，拖后腿的是没有一处可核验的个人指标，只能靠补数据走。",
        "cards": ["（mock）「解析链路和评测是我负责的那一段」——打招呼第一句就说这句"],
        "gaps": ["（mock）项目成果只有团队量级，1–2 天能补出个人口径"],
        "advice": ["（mock）投 AI 应用开发的方向，别去碰纯后端，你的差异化在 LLM 落地这条线上"],
        "salary_note": "（mock）候选人未提供期望薪资，按中级档给参考：15K–22K，这是参考不是报价",
    },
}

# 批改稿与面试预演的 mock 载荷。
#
# 这一份和上面那份概览同一个身份：**声明式的演示夹具**，不是降级产物。降级时"这一节没出来"
# 仍由 `validate_redline_edits`/`build_interview` 那两条 honesty 规则守着（批改全被拒 ⇒ 整节缺席，
# 不写"这一版可以原样用"），这里配的载荷不影响那一条。
#
# `del` 逐字取自 `_MOCK_RESUME` 经 `build_report_sections` 展开后的块文本，所以这份载荷在
# mock 世界里是**真的能过服务端复核**的（tests/test_resume_report_mock_stages.py 把这一条钉住：
# 块文本一改，这里就得跟着改，否则测试红）。换一份真简历进来，这些 `del` 命中不了，
# 会被复核整条拒掉——那是正确行为，不是这份载荷的失败。
# 改写里不新增简历中没有的事实，该有数而还没有的一律走 `【待补：…】`；`ins` 不带 `（mock）`
# 前缀，因为它会被"采纳"原样写回简历正文，标记留在 `note` 上。
_MOCK_REPORT_REDLINE = {
    "edits": [
        {
            "block_id": "work[0].desc",
            "del": "负责招聘平台后端开发与维护",
            "ins": "负责招聘平台【待补：由你作主的具体模块】的开发与维护，【待补：你达成的一个指标及其统计口径】",
            "note": "（mock）这一句只有职责动词，没有一个可核验的个人达成数，面试官在这里一定会追"
            "「哪一块是你写的」。先把范围收到你能作主的模块，再补一个自己跑出来的数和它的口径。",
            "tier": "key",
        },
        {
            "block_id": "proj[0].tech",
            "del": "FastAPI、LangChain、MySQL",
            "ins": "FastAPI、LangChain、MySQL【待补：按项目里真实用到的顺序排，并挑出你能讲清边界的那一个】",
            "note": "（mock）三个词并列，看不出哪个真在这个项目里跑过。这一栏是字段值，采纳不会写回简历，"
            "请自己在简历文件里落笔。",
            "tier": "key",
        },
        {
            "block_id": "proj[0].desc",
            "del": "基于 LLM 的简历结构化解析",
            "ins": "基于 LLM 与 LangChain 的简历结构化解析：字段口径与切片策略【待补：字段数、切片方式、失败样本怎么处理】",
            "note": "（mock）项目只写了一句「是什么」，没写约束和代价，面试官追到第二层就没有纸面可指。"
            "技能清单里已经列了 LangChain，把它在这段里对应上。",
            "tier": "key",
        },
        {
            "block_id": "proj[0].desc",
            "del": "支撑日均 1w+ 解析",
            "ins": "支撑日均 1w+ 解析【待补：其中由你负责的那一段的量与口径】",
            "note": "（mock）这个数是整条链路的团队量级，看不出你个人贡献了多少，很容易被当成蹭量。",
            "tier": "normal",
        },
        {
            "block_id": "skills",
            "del": "Python、FastAPI、MySQL、Docker、LangChain",
            "ins": "后端：Python、FastAPI、MySQL；部署：Docker；LLM 应用：LangChain",
            "note": "（mock）并列的名词堆看不出层次，也没标哪些能做主、哪些只是调用过。"
            "按用途分组之后，面试官才知道该往哪一层追。",
            "tier": "normal",
        },
        {
            "block_id": "self_evaluation",
            "del": "专注 Python / AI 应用落地",
            "ins": "专注 Python 后端与 AI 应用落地，能讲清【待补：一条自己走完的落地链路】",
            "note": "（mock）「专注」在纸面上不算证据，要么挂到一个具体的项目名上，" "要么把方向收到一两个能指的词。",
            "tier": "normal",
        },
    ],
    "no_change_note": "",
}

# 8 题（不是 §6 的 18–22 题）：这是夹具，只负责把模块四的形状摆齐——五种题型都出现一次、
# 十个追问类型标签全覆盖、三条需补强各点名缺的是哪个数。题数由服务端数出来，
# 页面上「共 8 题」与分布条永远自洽；真 provider 那一发的题量由 prompt 里的 18–22 约束。
_MOCK_REPORT_INTERVIEW = {
    "questions": [
        {
            "question": "（mock）智能简历解析服务这条链路是怎么搭起来的？你负责哪一段？",
            "kind": "项目深挖",
            "project": "项目 1 · 智能简历解析服务",
            "answer": "（mock）这个项目里我负责的是解析链路那一段。整体形状是这样：简历文件先进来，"
            "抽成正文，再用大模型把正文收成结构化字段，收完之后过一遍字段级的校验，"
            "校验不过的样本回到人工看的队列里。我写的是收字段那一段和它后面的校验，"
            "服务对外的那层接口也是我用 FastAPI 起的。存储用的是 MySQL，一份简历落一行，"
            "按人可以回溯版本。要说明的是，这条链路的整体吞吐是团队量级，"
            "我个人能作主的是解析与校验那一段；这一段自己跑出来的数我还没调到纸面上，"
            "这个数我要回去调一下再补，不想在这里给一个听起来合理的值。",
            "followups": [
                {"kind": "为什么", "text": "（mock）为什么用大模型抽字段，而不是规则加正则？"},
                {"kind": "权衡/代价", "text": "（mock）换成模型之后，慢和贵这两件事你怎么处理的？"},
                {"kind": "边界", "text": "（mock）什么样的简历这份链路会抽错？"},
            ],
            "status": "需补强",
            "missing": ["由我负责的这一段跑出来的解析准确率与样本口径", "抽错样本的回流队列量级"],
        },
        {
            "question": "（mock）字段口径是怎么定下来的？抽错了怎么发现？",
            "kind": "项目深挖",
            "project": "项目 1 · 智能简历解析服务",
            "answer": "（mock）口径是先按下游要什么倒推的：推荐和匹配要拿哪些字段去比，这些字段就必须有；"
            "比不到的字段就先不收，免得多一处就多一处会错的地方。定完之后写了一份清单，"
            "每个字段一个含义加一个例子，模型那边的提示词直接引这份清单。发现错误靠两条："
            "一条是每字段一条形状校验，日期、电话、邮箱这种能机器判的先机器判；"
            "另一条是抽出来和原文对不上的样本进队列，人看一眼归因，是提示词没写清还是这一版式本来就没写过。"
            "至于每一类的比例，我手上只有零散的记录，正式的数字要回去把队列捞一遍才有，"
            "这个数我要回去调一下再补。",
            "followups": [
                {"kind": "数据", "text": "（mock）这些字段里最容易抽错的是哪一个？"},
                {"kind": "如果", "text": "（mock）如果再加一个字段，你的流程要多付什么代价？"},
                {"kind": "踩坑", "text": "（mock）口径改过吗？哪一次改动引出过问题？"},
            ],
            "status": "需补强",
            "missing": ["各类字段的错误比例（要回队列里捞）", "最易错那一类的具体样本数"],
        },
        {
            "question": "（mock）日均 1w+ 这个量级里，瓶颈在哪一段？你怎么定位的？",
            "kind": "项目深挖",
            "project": "项目 1 · 智能简历解析服务",
            "answer": "（mock）先说清口径：这个量是整条链路的，我个人负责的是解析与校验那一段。"
            "定位瓶颈的做法是把一次投递拆成几段各自计时，然后看长尾而不是均值。"
            "我们那段最慢的一向不是自己算，是等模型回，所以要控并发和重试；"
            "MySQL 那边按人查历史走过一次慢查询，加了合适的索引之后就不是问题了。"
            "再往细一层的数字——每一段各占多少时间、长尾在哪一个分位——"
            "我当时看的是临时日志，没有落成一份能引用的表，这个数我要回去调一下再补。"
            "如果重来一次，我会在上线那天就把分段耗时打成指标。",
            "followups": [
                {"kind": "权衡/代价", "text": "（mock）加并发和加重试之间你怎么选的？"},
                {"kind": "边界", "text": "（mock）这条链路量级再上去一档，先撑不住的是哪里？"},
                {"kind": "预期指标", "text": "（mock）你要看到什么数才敢说瓶颈真的挪走了？"},
            ],
            "status": "需补强",
            "missing": ["分段耗时与长尾分位（当时只有临时日志）"],
        },
        {
            "question": "（mock）这条解析链路里你踩过最大的一个坑是什么？",
            "kind": "踩坑与边界",
            "project": "项目 1 · 智能简历解析服务",
            "answer": "（mock）最大的是我一开始把模型的输出当成可信数据在写库。它会把没有的字段填得很像有，"
            "日期格式也一会儿这样一会儿那样，等发现的时候库里的脏东西已经混进正常行里了。"
            "后来做了三件事：一是所有字段先过形状校验再入库；二是模型给的原文片段要能在这份简历里"
            "逐字找到，找不到就当成没抽到；三是同一份简历重跑要能对比，改出来的差异留记录。"
            "这三件事之后我没再见过整批脏数据，但一次都没有的那个数我也没有，"
            "只做过一轮回归，样本量很小，这个数我要回去调一下再补。"
            "这件事让我后面的默认做法变成：模型的输出先当外部输入看。",
            "followups": [
                {"kind": "为什么", "text": "（mock）为什么逐字回查这一条能挡住编造？"},
                {"kind": "踩坑", "text": "（mock）这三条里有没有一条后来反而添了麻烦？"},
                {"kind": "对比", "text": "（mock）和你们规则解析那版比，谁的错法更难查？"},
            ],
            "status": "可答",
            "missing": [],
        },
        {
            "question": "（mock）技能里写了 LangChain，在这条链路里它具体做了哪一段？",
            "kind": "基础概念",
            "project": "项目 1 · 智能简历解析服务",
            "answer": "（mock）它管的是模型调用这一层的编排：提示词的装配、把上一轮的输出接到下一轮、"
            "以及把返回的文本收成能直接用的结构。我自己写的部分是它前后的两段——"
            "前面是文件到正文，后面是字段校验和入库，这两段跟框架无关。"
            "为什么只让它在中间这一层：框架换起来代价小，前后两段是我们自己的口径，"
            "写在哪儿都不亏。边界也说清：这条链路的并发、重试和观测是我自己接的，"
            "没有全交给框架的默认行为，因为它默认的那套在超时和重试上我们不好控。"
            "至于把它换成自己写一遍要多少钱，我没真做过对照，不报数。",
            "followups": [
                {"kind": "对比", "text": "（mock）不用框架，自己写一遍这段编排要多付什么？"},
                {"kind": "为什么", "text": "（mock）哪些部分你刻意不交给框架？"},
                {"kind": "边界", "text": "（mock）框架的默认重试在什么场景下会伤到你？"},
            ],
            "status": "可答",
            "missing": [],
        },
        {
            "question": "（mock）FastAPI 在那条链路上怎么起服务的？异步用在哪儿了？",
            "kind": "基础概念",
            "project": "通用",
            "answer": "（mock）对外是 FastAPI 起的一层，路由进去之后先落一条任务记录，"
            "把慢的那一段交给后台去跑，请求这一路立刻回一个编号，前端拿编号轮询。"
            "这么做的原因很直接：等模型那一发是十几秒到几十秒的量级，"
            "如果占着请求线程不放，人不多就能把线程池顶满，这是我在别的接口上真见过的事。"
            "异步用在等外部的地方——等模型、等别的系统；数据库这一层我沿用的是同步会话，"
            "没有把整条 ORM 换成异步，因为那一条我要的收益不明显。"
            "线程池被顶满那一次的具体数字我没有留下记录，这个数我要回去调一下再补。",
            "followups": [
                {"kind": "如果", "text": "（mock）把数据库那一层也换成异步，你预计先看到什么变化？"},
                {"kind": "权衡/代价", "text": "（mock）轮询和长连接两种回法你选哪个，代价各是什么？"},
                {"kind": "数据", "text": "（mock）你怎么知道任务有没有卡在队列里？"},
            ],
            "status": "可答",
            "missing": [],
        },
        {
            "question": "（mock）你自己觉得这份简历现在最明显的短板是哪一个？",
            "kind": "对比权衡",
            "project": "通用",
            "answer": "（mock）最明显的是没有一个属于我个人的可核验指标。"
            "工作经历那行只写了负责什么，项目里那个日均量级是整条链路的，"
            "面试官追到第二层就没纸可指——要么信我，要么换个问法试探我。"
            "我权衡过两条路：一条是回去把自己那一段跑出数来再投；"
            "另一条是先投出去，在面试口头讲清口径。"
            "我选第一条，因为补数这件事是有边界的：解析与校验那一段我可以自己造一批样本跑一遍，"
            "不需要别人配合；而要把整条链路的量拆干净，就得跟团队要口径，慢且不一定给。"
            "这份简历里的技术栈覆盖面不缺，缺的是深度证据，这是我自己的判断。",
            "followups": [
                {"kind": "为什么", "text": "（mock）为什么先补个人那一段，而不是先把覆盖面铺宽？"},
                {"kind": "预期指标", "text": "（mock）你打算补出哪几个数才算补到位？"},
                {"kind": "代价", "text": "（mock）为了补这几个数你会牺牲掉什么？"},
            ],
            "status": "需补强",
            "missing": ["由我个人达成、可核验的指标至少一个（含统计口径）"],
        },
        {
            "question": "（mock）现在给你一批没有版式约定的简历，还会带图片，你会怎么改这条链路？",
            "kind": "场景设计",
            "project": "通用",
            "answer": "（mock）我会先把问题从解析挪到判定上。第一步定一份字段清单和它的评价口径，"
            "先让机器能判一份简历收回来算不算对，否则改到哪里都不知道；"
            "第二步分两路，正文抽得出来的走原来那条，抽不出来的（带图片的、版式很散的）"
            "加一路把版面先转成规整文本再进原来那层，不去改下游的校验；"
            "第三步是兜不住的那些——宁可回一句这一份没吃下，也不要给一个像样的空结果，"
            "这是我踩过的那个坑留下的习惯。落到人手上的顺序也是这三步，"
            "先口径再分流最后处理失败。存量数据要不要回算我拿不定，"
            "回算一遍要多少时间这个数我要回去调一下再补。",
            "followups": [
                {"kind": "场景", "text": "（mock）这批简历如果有一千份，你的步骤哪一步先变形？"},
                {"kind": "权衡/代价", "text": "（mock）加一路版面转换，你放弃了什么？"},
                {"kind": "如果", "text": "（mock）如果只给你一周，你先砍掉哪一步？"},
            ],
            "status": "可答",
            "missing": [],
        },
    ]
}

_MOCK_DISPATCH = {
    "intent": "full",
    "target_agents": ["ResumeAgent", "JobAgent", "MatchAgent", "InterviewAgent", "CareerAgent"],
    "reason": "（mock）需求较综合，默认启动全部 5 个子智能体进行全面分析",
    "user_profile": "在职跳槽者",
    "notes": "",
}


# ---------------------------------------------------------------- 单项目分析（四大节）的 mock 载荷
# 这四支是**声明为夹具的载荷**，不是"模型挂了时的等价替代文本"：每一支都必须能被
# `project_report_service` 的真实复核吃下（逐字红线、锚定扣分点、图与表的数字必须来自原文、
# 两轮追问、三态状态），过不了就是这份夹具坏了，由 `tests/test_project_report_mock_stages.py` 钉住。
# 载荷里所有 `（mock）` 前缀都在告诉读的人：这不是候选人写下的话，也不是模型真的判出来的话。
#
# 取材限定在 `_MOCK_RESUME` 那一条项目上（正文只有一句"基于 LLM 的简历结构化解析，
# 支撑日均 1w+ 解析"，技术栈三个词），所以：
# * 能逐字引用的短语只有那一句与那几个组件名；
# * 除 "1"（来自 1w+）以外不写任何阿拉伯数字——写了就会被"新数字"那条复核拒掉，
#   而这正是这一族要演示的界：该有个数而没有的，走 `【待补】`。
def _mock_project_answer(tail: str) -> str:
    """mock 口述稿的公共前半句。

    它自带那条**逐字引用**（`_MOCK_RESUME` 项目正文里唯一可引的一句），
    所以每一段都天然满足"数字必须来自原文"这条复核；尾部再展开具体做法。
    """
    return "（mock）「基于 LLM 的简历结构化解析」这一条我负责的是解析与回查两段。" + tail


_MOCK_PROJECT_PROFILE = {
    "portrait": {
        "domain": "（mock）HR 科技",
        "scene": "（mock）简历进库前的结构化解析",
        "main_line": "（mock）LLM 结构化抽取 + 逐字回查校验",
        "components": "（mock）FastAPI、LangChain、MySQL",
    },
    "dimensions": {
        "d1_role_signal": {
            "score": 20,
            "note": "（mock）技能带踩中大模型应用这条主线：「基于 LLM 的简历结构化解析」一句就认得出是同行；"
            "技术栈里的 MySQL 在正文里没有落点，方向词因此少一层佐证。",
        },
        "d2_depth": {
            "score": 12,
            "note": "（mock）只有「支撑日均 1w+ 解析」一个规模数，字段类别数、抽取失败率、回查覆盖范围"
            "这些能证明做过的细节都没有。",
        },
        "d3_metric": {
            "score": 8,
            "note": "（mock）这一条给了绝对值没给前后：1w+ 是日均量，不是本人优化出来的差值；"
            "缺一条【待补：按上线前后同一口径跑一遍得到的解析成功率差值】。",
        },
        "d4_transfer": {
            "score": 8,
            "note": "（mock）「简历结构化解析」抽掉 HR 场景在别的长文档场景也成立，但项目里没写怎么切分、"
            "怎么校验，方法论那一层没露出来。",
        },
        "d5_interview": {
            "score": 7,
            "note": "（mock）「支撑日均 1w+ 解析」会被追问怎么统计、成功率多少，原文里答不上；"
            "技术栈里的 LangChain 在这条链路里做了什么也说不清。",
        },
    },
    "red_lines": [],
    "difficulty": {
        "level": "L3",
        "reason": "（mock）链路上有解析与逐字校验两段，并留下一个日均量口径；没有编排、模型适配与线上观测。",
    },
    "highlights": [
        {"metric": "（mock）日均解析量", "value": "1w+ 份", "basis": "（mock）原文没有写统计周期、成功率与标注口径"},
    ],
    "hooks": [
        "（mock）为什么把逐字回查放在生成之后，而不是让模型一次出干净",
        "为什么用 LangChain 而不是自己拼提示词与解析两段",
        "结构化字段口径变了之后，历史简历要不要重新解析一遍",
    ],
    "risks": [
        {
            "point": "（mock）只有绝对值没有前后对比",
            "detail": "追问「解析成功率从多少提到多少」时给不出差值，只能把日均量再说一遍",
            "fix": "【待补：按上线前后同一批简历各跑一遍，得到成功率与人工返修率的差值】",
        }
    ],
    "peer_dimensions": [],
}

_MOCK_PROJECT_DIAGRAMS = {
    "background": "（mock）这是一套把简历原文变成结构化字段的解析服务，用在候选人上传附件之后、匹配计算开始之前。"
    "原来靠人工按模板录一遍，同一份简历不同人录出的字段口径不一样。",
    "needs": {
        "items": [
            {
                "title": "（mock）字段口径不一致",
                "detail": "不同人录出的字段名与粒度不一样，下游匹配只能按最粗的那一层算。",
            },
            {"title": "（mock）版式杂导致丢字段", "detail": "扫描件与表格式简历会让抽取丢字段，丢了不能猜，要标出来。"},
        ],
        "roles": "（mock）候选人自助投递，运营做复核与返修。",
        "delivery": "（mock）上传附件后输出结构化字段与逐字回查结论，供后续匹配计算使用。",
        "constraints": "（mock）原文里没有的字段不允许由模型补造，缺失一律标记待人工。",
    },
    "function_arch": {
        "layers": [
            {
                "name": "（mock）使用角色",
                "mine": False,
                "cells": [{"title": "候选人", "lines": ["上传附件"]}, {"title": "运营", "lines": ["复核与返修"]}],
            },
            {"name": "（mock）业务入口", "mine": False, "cells": [{"title": "简历上传", "lines": ["原文与附件"]}]},
            {
                "name": "（mock）AI 能力层",
                "mine": True,
                "cells": [
                    {"title": "结构化抽取", "lines": ["按字段表出结果"]},
                    {"title": "逐字回查", "lines": ["结论要能对上原文"]},
                ],
            },
            {
                "name": "（mock）依托组件",
                "mine": False,
                "cells": [{"title": "FastAPI", "lines": ["服务入口"]}, {"title": "MySQL", "lines": ["结果落库"]}],
            },
        ],
        "boundary": "（mock）★ 我负责：字段表设计、抽取与回查这两段链路，以及它们在服务里的编排；"
        "FastAPI、LangChain、MySQL 是既有组件，本人负责选型与接入。",
        "deep_dive": [
            {
                "where": "（mock）我负责的边界怎么答",
                "point": "哪几段是本人设计实现，哪几段是选型接入",
                "source": "「基于 LLM 的简历结构化解析」",
            },
            {
                "where": "（mock）为什么回查放在生成之后",
                "point": "生成会给出不存在的字段，放后面才拦得住",
                "source": "技术栈里的 LangChain",
            },
        ],
    },
    "core_flow": {
        "input": {"title": "（mock）输入", "lines": ["一份简历附件"]},
        "nodes": [
            {"no": 1, "title": "（mock）取原文", "lines": ["把版式变成可读文本", "段落边界不清就标出来"]},
            {"no": 2, "title": "（mock）按字段表抽取", "lines": ["输出字段与它对应的原文位置"]},
            {"no": 3, "title": "（mock）逐字回查", "lines": ["字段值必须能在原文里找到", "找不到的标待人工"]},
            {"no": 4, "title": "（mock）落库与出口", "lines": ["结构化结果进关系库", "缺字段留标记"]},
        ],
        "exit": {"title": "（mock）出口", "lines": ["结构化简历，进后续匹配计算"]},
        "fallbacks": ["（mock）回查对不上 → 该字段作废并标待人工，不猜内容", "版式还原失败 → 退回人工录入"],
        "state": "（mock）每个环节只写自己产出的字段，下游只读自己需要的，改一段不牵到别处。",
        "deep_dive": [
            {"where": "（mock）为什么切成四段", "point": "每一段都能被人单独验收", "source": "职责第 1 条"},
            {
                "where": "（mock）最容易错在哪一段",
                "point": "抽取会把表格里的内容当成正文",
                "source": "「基于 LLM 的简历结构化解析」",
            },
        ],
    },
    "system_arch": {
        "layers": [
            {
                "name": "（mock）服务层",
                "components": [
                    {"title": "FastAPI", "line": "接上传与查询"},
                    {"title": "任务队列", "line": "解析是慢活，异步跑"},
                ],
            },
            {
                "name": "（mock）能力层",
                "components": [{"title": "抽取", "line": "按字段表生成"}, {"title": "回查", "line": "逐字比对"}],
            },
            {
                "name": "（mock）存储层",
                "components": [{"title": "MySQL", "line": "结构化结果"}, {"title": "对象存储", "line": "原始附件"}],
                "principle": "（mock）原文要能追溯到段落，结果要能按人检索，所以分开存、靠同一份简历标识对齐。",
            },
        ],
        "deep_dive": [
            {
                "where": "（mock）原文与结果怎么对齐",
                "point": "同一份简历一个标识，两边都能查",
                "source": "技术栈里的 MySQL",
            },
            {
                "where": "（mock）为什么任务队列单独一层",
                "point": "解析耗时不稳定，同步会把请求按住",
                "source": "项目中解析那一段",
            },
        ],
    },
    "sequence": {
        "lanes": ["（mock）候选人", "服务层", "抽取", "回查", "存储层"],
        "messages": [
            {"from": "（mock）候选人", "to": "服务层", "text": "上传附件"},
            {"from": "服务层", "to": "抽取", "text": "取原文与字段表"},
            {"from": "抽取", "to": "回查", "text": "字段值与它的原文位置"},
            {"from": "回查", "to": "存储层", "text": "对得上的结果与对不上的标记"},
            {"from": "存储层", "to": "服务层", "text": "结构化简历"},
        ],
        "branches": ["（mock）回查对不上 → 字段作废并回到人工录入，不往下游发", "版式还原失败 → 直接标待人工"],
        "artifacts": {
            "task": "（mock）简历标识与附件路径",
            "process": "字段列表、原文位置、回查结论",
            "control": "待人工标记、重试次数",
        },
        "deep_dive": [
            {"where": "（mock）哪一步最容易吞错", "point": "回查对不上却被当成解析成功", "source": "职责第 1 条"},
            {
                "where": "（mock）失败之后数据长什么样",
                "point": "字段为空并带一个待人工标记",
                "source": "「支撑日均 1w+ 解析」",
            },
        ],
    },
    "reading_note": "（mock）教学先看背景与需求两张，再按功能架构、流程、系统架构、时序的顺序讲；"
    "面试先看功能架构里高亮那一层，把「我负责什么」一句话站稳。",
}

_MOCK_PROJECT_ADVICE = {
    "teaching": {
        "suitable": "（mock）长文本到结构化字段的抽取设计 / 逐字回查这道防线放在哪里 / 缺失字段为什么不许模型补",
        "steps": "（mock）第一步把抽取跑通并只看字段齐不齐；第二步加逐字回查并把对不上的标出来；"
        "第三步统计人工返修的量；第四步改字段表并做前后对照",
        "entry": "（mock）先拿一批真实简历和一张字段表，把「哪些字段错了会被下游发现」这件事定下来",
        "stage": "（mock）适合放在学完基础检索与提示词之后的结构化抽取环节",
    },
    "reuse": {
        "structure": "（mock）先写这条链路在流程里的位置，再写抽取与校验两段，最后写一个量",
        "expression": "（mock）「原文与结果分开存、靠同一标识对齐」这种说法可以搬到任何长文档场景",
        "replace": "（mock）字段表内容、日均量与统计口径都要换成自己真实接触过的",
        "counterexample": "（mock）照搬「日均 1w+」会被追问怎么统计、成功率多少，答不上就露",
    },
    "practice": {
        "method": "（mock）先自己口述一遍录音，再逐句检查每个数字有没有口径",
        "rehearsal": "（mock）每一句都自己追问到第三层，答不上的那句要么补细节要么删掉",
        "timing": "（mock）主答案控制在两分钟内，每轮追问一分钟内",
    },
    "strengthen": [
        {
            "gap": "（mock）只有绝对值没有前后对比",
            "action": "【待补：按上线前后同一批简历各跑一遍，得到成功率差值与人工返修率】",
            "expected": "（mock）D3 指标责任 弱 → 中，D5 面试承载力能撑到第二轮",
        }
    ],
    "citation": {
        "borrow": "（mock）可借鉴：把校验放在生成之后、缺失不许模型补这条防线",
        "adapt": "（mock）需改造：字段表与统计口径必须换成自己业务里的",
        "breaks": "（mock）一抄就穿：日均量那一个数字与「逐字回查」的说法",
    },
}

_MOCK_PROJECT_QUESTIONS = {
    "questions": [
        {
            "question": "（mock）这个项目当初解决的是什么问题？",
            "kind": "背景与定位",
            "answer": _mock_project_answer(
                "原来靠人工按模板把简历录进系统，一份简历不同人录出来的字段名和粒度都不一样，下游匹配只能按最粗的那一层算。"
                "我把系统定位在候选人上传之后、匹配计算之前这一道，让它把原文变成按字段表落库的结构化结果，"
                "再把对不上原文的字段标成待人工，由运营在标记上补，而不是让系统自己猜一个填进去。"
            ),
            "followups": [
                {"kind": "为什么", "text": "（mock）为什么定位成前置解析，不做成自动定稿"},
                {"kind": "边界", "text": "（mock）标了待人工的那部分谁来处理"},
            ],
            "status": "可答",
        },
        {
            "question": "（mock）整条链路是怎么走的？",
            "kind": "链路与选型",
            "answer": _mock_project_answer(
                "四段：先把版式变成可读文本并把段落边界取出来，再按字段表抽取字段和它对应的原文位置，"
                "然后逐字回查——每个字段值都要能在原文里找到出处，找不到的不猜，标成待人工，"
                "最后把结构化结果与这些标记一起落库，下游按有没有标记决定要不要等人工。"
                "这么切的理由是每一段都能被单独验收，出问题能定位到底是哪一段。"
            ),
            "followups": [
                {"kind": "为什么", "text": "（mock）为什么单独设回查那一段"},
                {"kind": "踩坑", "text": "（mock）哪一段最先出过事"},
            ],
            "status": "可答",
            "diagram": {
                "title": "（mock）四段链路：回查是最后那道闸",
                "cards": [
                    {"title": "取原文", "lines": ["版式变文本", "边界不清就标出来"]},
                    {"title": "抽取", "lines": ["按字段表出结果和位置"]},
                    {"title": "回查", "lines": ["逐字找出处", "找不到标待人工"]},
                    {"title": "落库", "lines": ["结果与标记一起存"]},
                ],
                "note": "（mock）画完补一句：这一段不让模型补内容，缺失就是缺失。",
                "how_to_draw": "（mock）从左到右一次画完四段，每段说清输入什么、产出什么；"
                "再圈住回查那一格讲它为什么放在生成之后——生成会给出不存在的字段，只有放后面才拦得住。",
            },
        },
        {
            "question": "（mock）为什么用 LangChain，自己拼不行吗？",
            "kind": "链路与选型",
            "answer": _mock_project_answer(
                "自己拼也能跑，但这条链路里要串的不止一次调用：取原文、抽取、回查三段之间要传结构化结果，"
                "还要能单独测每一段。用 LangChain 主要是拿它的链式组织与字段约束，让每一段的输入输出形状固定下来。"
                "代价是链路里多了一层框架的约定，出问题时要多看一眼它替你做了什么；"
                "所以我把回查这一段写成自己的函数，没有交给框架的默认行为。"
            ),
            "followups": [
                {"kind": "代价", "text": "（mock）用框架带来的麻烦具体是哪一处"},
                {"kind": "对比", "text": "（mock）哪些段落你故意没交给框架"},
            ],
            "status": "需补强",
            "missing": ["（mock）缺一个对比口径：同一批简历走框架与走自己拼的耗时与失败率各多少"],
        },
        {
            "question": "（mock）日均 1w+ 这个数是怎么统计出来的？",
            "kind": "数据与评测",
            "answer": _mock_project_answer(
                "这一条我要老实说清楚：原文里写的日均量是这份系统跑起来的总量级，不是我一个人优化出来的差值。"
                "它统计的是进入解析链路的简历份数，按天汇总。口径里没有写成功率的判定标准——"
                "什么算解析成功、字段缺几个算失败、这部分是谁标的，都没有留在原文里。"
                "面试官一定会顺着这里问，所以这一块要么把口径补上，要么把这句话改成不含糊的说法。"
            ),
            "followups": [
                {"kind": "数据", "text": "（mock）成功率按什么判定"},
                {"kind": "如果", "text": "（mock）如果只能补一项，补哪项"},
            ],
            "status": "高危",
            "missing": ["【待补：成功率的判定标准与样本量】", "【待补：统计周期的取数窗口】"],
            "risk_ref": 1,
        },
        {
            "question": "（mock）回查这一步具体怎么做？",
            "kind": "工程与部署",
            "answer": _mock_project_answer(
                "抽取出来的每个字段值都带一个原文位置。回查拿这个位置前后一段文本，把字段值做逐字比对："
                "对得上的放行，对不上的不猜内容，直接标成待人工并留下两边的原文。"
                "这一步的判据我定得偏严——漏判一个错字段的代价比多标一个人工大，"
                "因为错字段会一路带到匹配计算里，而且看起来完全正常，很难被发现。"
            ),
            "followups": [
                {"kind": "边界", "text": "（mock）位置本身取错的时候怎么办"},
                {"kind": "踩坑", "text": "（mock）早期有没有把对的判成错的"},
            ],
            "status": "可答",
        },
        {
            "question": "（mock）哪一处最难，怎么过的？",
            "kind": "权衡与代价",
            "answer": _mock_project_answer(
                "最难的是让失败以人能处理的形式呈现。抽取本身不算难，难的是它错的时候很安静："
                "字段填上了、格式也对，值却是模型按常识补的。我最后选了把不确定性显式化这条路——"
                "宁可让一条数据带着待人工标记进库，也不让它带着一个看不出错的结果进库。"
                "这个选择的代价是人工要处理的量上来了，所以还得让人只处理标出来的那部分。"
            ),
            "followups": [
                {"kind": "权衡", "text": "（mock）人工量涨了多少，值不值"},
                {"kind": "代价", "text": "（mock）这条路的副作用是什么"},
            ],
            "status": "可答",
            "diagram": {
                "title": "（mock）两种失败形态：安静地错 vs 带着标记停住",
                "cards": [
                    {"title": "猜内容", "lines": ["字段填满", "看起来正常", "错会一路带下去"]},
                    {"title": "标待人工", "lines": ["该空的空着", "带出处", "人能只看这一小块"]},
                    {"title": "我的取舍", "lines": ["不确定就停住", "代价是人工量"]},
                ],
                "note": "（mock）收尾一句：错得安静比错得多更危险。",
                "how_to_draw": "（mock）左右画两格对照——左边猜内容、右边标待人工，"
                "各自写清它对下游意味着什么；中间补一格写下我的判据：不确定就停住。"
                "讲的时候把代价一起说，人工量确实上来了，这样听起来才是真做过的。",
            },
        },
        {
            "question": "（mock）字段表改了，历史数据怎么办？",
            "kind": "沉淀与迁移",
            "answer": _mock_project_answer(
                "分两类：加字段不重跑，旧记录那一列留空，新数据按新表出；改字段含义就必须重跑，"
                "否则同一列里混着两种口径，下游匹配会拿它算出没人能解释的结果。"
                "我留下的做法是把字段表当成有版本的契约：每条结果记住它是按哪一版抽的，"
                "重跑按版本挑，不靠人记。这套说法放到任何结构化抽取上都成立，不绑简历这个业务。"
            ),
            "followups": [
                {"kind": "为什么", "text": "（mock）为什么不干脆全部重跑"},
                {"kind": "对比", "text": "（mock）留版本和留时间戳差别在哪"},
            ],
            "status": "需补强",
            "missing": ["（mock）缺一次重跑的实际量级：多少份、跑多久、花多少调用"],
        },
        {
            "question": "（mock）换一个业务域，这套还成立吗？",
            "kind": "沉淀与迁移",
            "answer": _mock_project_answer(
                "成立的部分是三层判断：原文与结果分开存并靠同一标识对齐；不确定的结果不许猜、要带出处停下来；"
                "字段表是有版本的契约。这三条都不依赖简历这个业务。"
                "一定要重做的是字段本身与成功率的判定——那两个是业务方的标准，不是技术选择。"
                "我的判断顺序是先看要抽取的内容是命中型还是结构型，再决定校验放在哪一步，"
                "最后才谈要不要训练，顺序反了会发现前面两件事都没定。"
            ),
            "followups": [
                {"kind": "对比", "text": "（mock）换域时哪一段最省事"},
                {"kind": "如果", "text": "（mock）如果只能带一条经验走，带哪条"},
            ],
            "status": "可答",
            "diagram": {
                "title": "（mock）换域能带走的三件事与要重做的两件",
                "cards": [
                    {"title": "能带走", "lines": ["分层与对齐", "停下来带出处", "字段表是契约"]},
                    {"title": "要重做", "lines": ["字段本身", "成功率的判定"]},
                    {"title": "顺序", "lines": ["先看形态", "再定校验位置", "最后谈训练"]},
                ],
                "note": "（mock）收尾：越靠近业务的越要重做，越靠近工程的越可复用。",
                "how_to_draw": "（mock）上下两层画：上层写三件能带走的，下层写两件要重做的，"
                "右边单独画一条箭头写判断顺序。讲的时候强调顺序反了会返工，这是踩过之后才明确的。",
            },
        },
    ]
}


# ---------------------------------------------------------------- 组合分析（四大节）的 mock 载荷
# 这一族比单项目那一族多一件事：它要对着**任意**被选中的项目数（两到 N 个）自己长出形状，
# 所以四支都现从 prompt 里读项目清单，而不是写死两个项目——写死的夹具只钉得住"两个项目"
# 那一种组合，第三个项目进来就变成假阳性。读的是服务端 `_projects_block` 渲染的那一行
# `（project_index=…，简历里第 … 个）` 与其下的正文条目，这条耦合由
# `tests/test_portfolio_report_mock_stages.py` 钉住。
# 载荷里除了从原文 lifted 的那一句之外**不写阿拉伯数字**：写了就会被"新数字"那条复核拒掉，
# 而这一族要演示的恰恰是"该有个数而没有的，走 `【待补】`"。

_PORTFOLIO_PROJECT_HEAD = re.compile(r"【项目 \d+ · (.*?)】（project_index=(\d+)，简历里第 \d+ 个）")
_PORTFOLIO_POINT_LINE = re.compile(r"^- (.+)$", re.M)
_PORTFOLIO_KINDS = ("差异与取舍", "选型与理由", "真实与边界", "评测与归因", "整合与演进", "沉淀与成长")


def _mock_portfolio_projects(prompt: str) -> list[tuple[int, str, str]]:
    """[(project_index, 项目名, 这一段的第一条正文)]，按 prompt 里出现的顺序。

    每一段只读到**下一个 `【…】` 区块标题**为止：最后那一条项目的正文后面紧着的是量表与
    示例 JSON（里面满是数字），一路读到结尾就会把口径行的数字 lift 进答案里，
    然后被"数字必须来自原文"那条复核判成编造——这是夹具的边界，不是产品该拦的形状。
    """
    matches = list(_PORTFOLIO_PROJECT_HEAD.finditer(prompt))
    out: list[tuple[int, str, str]] = []
    for position, match in enumerate(matches):
        stop = prompt.find("\n【", match.end())
        if position + 1 < len(matches):
            stop = min(stop if stop > 0 else len(prompt), matches[position + 1].start())
        if stop < 0 or stop > len(prompt):
            stop = len(prompt)
        body = prompt[match.end() : stop]
        lines = [line.strip() for line in _PORTFOLIO_POINT_LINE.findall(body)]
        out.append((int(match.group(2)), match.group(1).strip(), lines[0] if lines else ""))
    return out


def _mock_lift(quote: str, limit: int) -> str:
    """把 lifted 的原文截到 limit，且**截完末尾不许停在数字串里**。

    截出"9."或"3%"这种半截数字，会在"图与表里的数字必须来自原文"那条复核上被判成编造——
    那是夹具的锅，不是产品该拦的东西。所以末尾落在数字串上时整串退掉。
    """
    head = quote[:limit]
    if head == quote:
        return quote
    return head.rstrip("0123456789.,%+－→- ")


def _mock_portfolio_quote(projects: list[tuple[int, str, str]], position: int) -> str:
    """lifted 一条原文当逐字引用：既过"数字必须来自原文"，也天然满足扣分点要点名位置。"""
    if not projects:
        return "（mock）这一段项目原文里的一句话"
    index = position % len(projects)
    quote = projects[index][2]
    lifted = _mock_lift(quote, 26) if quote else ""
    if not lifted:
        return "（mock）这一段项目原文里的一句话"
    return f"（mock）「{lifted}」"


def _mock_portfolio_cells(projects: list[tuple[int, str, str]], all_full: bool) -> list[dict[str, Any]]:
    cells = []
    for position, (index, _name, _quote) in enumerate(projects):
        if all_full or position == 0:
            cell = "重点覆盖"
        elif position == 1:
            cell = "部分覆盖"
        else:
            cell = "未覆盖"
        cells.append({"project_index": index, "cell": cell})
    return cells


def _mock_portfolio_profile(prompt: str) -> dict[str, Any]:
    projects = _mock_portfolio_projects(prompt)
    names = "、".join(name or f"项目 {index + 1}" for index, name, _ in projects) or "（mock）这一组项目"
    compare_rows = []
    for key in ("domain", "skeleton", "orchestration", "retrieval", "highlight", "metric", "transferable"):
        compare_rows.append(
            {
                "row": key,
                "cells": [
                    {
                        "project_index": index,
                        "text": f"（mock）这一行的说法只引用该项目原文里的写法，取自「{_mock_lift(quote, 18)}」"
                        if _mock_lift(quote, 18)
                        else "（mock）这一行的说法只引用该项目原文里的写法",
                    }
                    for index, _name, quote in projects
                ],
            }
        )
    capabilities = []
    for position, key in enumerate(("doc_parsing", "hybrid_retrieval", "agent_orchestration", "refusal", "llmops")):
        capabilities.append({"capability": key, "cells": _mock_portfolio_cells(projects, all_full=position == 0)})
    return {
        "summary": {
            "projects_line": f"（mock）这一组是 {names} 叠在一起看的组合分析，只用原文里出现过的名词。",
            "common_skeleton": "（mock）几个项目都落在同一条骨架上：非结构化内容进库、多路召回取依据、在依据上判断、"
            "把不确定的部分交给人复核。这一句只描述原文写过的做法。",
            "difference_line": "（mock）差异要一个一个点：每个项目最独特的那一点只能从它自己那段原文里引，"
            "不能用同一句话套几个项目。",
        },
        "dimensions": {
            "d1_role_signal": {
                "score": 20,
                "note": f"{_mock_portfolio_quote(projects, 0)}这一条把技能带对上了岗位方向；"
                "少的那一层是几个项目叠起来仍然只覆盖检索与编排两段，评测与部署那一段没有落点。",
            },
            "d2_combo_distinct": {
                "score": 16,
                "note": f"{_mock_portfolio_quote(projects, 1)}几个项目的骨架重合，"
                "差异只体现在领域词上，技术决策层面说不出「这一个有、那几个没有」的那一条，扣分在这里。",
            },
            "d3_metric": {
                "score": 14,
                "note": "（mock）几个项目都有绝对量没有差值，归因也没有拆开——"
                "要补的是【待补：固定其他变量、每次只改一处、同一批样本跑对照得到的差值】。",
            },
            "d4_growth_line": {
                "score": 11,
                "note": f"{_mock_portfolio_quote(projects, 2)}能看出一条从检索优化往编排走的线，"
                "但最后一段（工程化与运营）在原文里没有落点，纵深少一层。",
            },
            "d5_interview": {
                "score": 10,
                "note": "（mock）跨项目那几问里，「只留一个留哪个」与「行业跨度这么大怎么做到的」"
                "在原文里给不出投入分配与时间线，这两问一追问就空。",
            },
        },
        "red_lines": [],
        "difficulty": {
            "level": "L3",
            "reason": "（mock）这一组叠了检索与编排两类做法，都留有口径但没有微调与多模态那一层，按范式叠加数定这一档。",
        },
        "compare": compare_rows,
        "capabilities": capabilities,
        "shared_stack": [],
        "risks": [
            {
                "point": "（mock）几个项目说的都是同一套骨架",
                "detail": f"追问「这几个项目有什么本质不同」时只能把 {_mock_portfolio_quote(projects, 0)}"
                "那一套做法重说一遍，给不出只有某一个项目才有的技术决策",
                "fix": "在每个项目那一段里各补一条「别的项目没有的那一个决策」，并写清为什么这个场景要它",
            },
            {
                "point": "（mock）归因都合在一起测",
                "detail": "几个项目都是两三项改动一起上，各自贡献没拆开，被追问「这一层各值多少」时答不出",
                "fix": "【待补：固定其他变量、每次只改一处、同一套样本跑对照得到的分项差值】",
            },
            {
                "point": "（mock）业务效果这一族普遍偏薄",
                "detail": "几个项目都只有技术指标，没有采纳率、人工节省、复用率这类业务口径",
                "fix": "【待补：按使用埋点跑一遍得到人工复核通过率与退回率的差值】",
            },
        ],
    }


def _mock_portfolio_diagrams(prompt: str) -> dict[str, Any]:
    projects = _mock_portfolio_projects(prompt)
    stage_names = ("阶段一 · 找得到", "阶段二 · 判得准", "阶段三 · 可运营", "阶段四 · 收得住", "阶段五 · 说得清")
    stages = []
    for position, (index, name, quote) in enumerate(projects):
        points = [
            f"（mock）这一阶段的每条要点都只写「{_mock_lift(quote, 16)}」这一段的原文里有的动作"
            if _mock_lift(quote, 16)
            else "（mock）这一阶段的要点只写原文里有的动作",
            "（mock）做法：把依据与判断分开，依据不足时不硬下结论",
            "（mock）痕迹：留下了自己的口径与一次对照，不是照教程搭一遍",
            "（mock）边界：这一段没有写上线多久、谁在用，追问时要承认没测",
        ]
        stages.append(
            {
                "project_index": index,
                "stage_name": stage_names[min(position, len(stage_names) - 1)],
                "points": points,
                "core_question": f"（mock）项目 {name or index + 1} 要回答的核心问题是判断能不能复现",
                "keywords": "（mock）检索、依据、复核",
            }
        )
    rounds = [
        {
            "key": "single_deep_dive",
            "text": "（mock）面试官先挑一个项目问链路与口径，这一轮拿的是单项目的技术深度，"
            "答案要落到那一段原文写过的动作上。",
        },
        {
            "key": "selection_reason",
            "text": "（mock）这一轮问的是为什么这么选：为什么用这一种融合而不是加权求和、"
            "为什么依据和判断要分开——考的是判断，不是执行。",
        },
        {
            "key": "cross_compare",
            "text": "（mock）这一轮把几个项目放在一起问：有什么本质不同、只留一个留哪个、哪个最难。"
            "答得好，面试官得到的是「做过三个项目」；答不好，得到的是「有三个项目经历」。",
        },
        {
            "key": "authenticity",
            "text": "（mock）这一轮质疑真实性：跨度这么大一个人怎么做、栈重叠这么多是不是同一套。"
            "答得诚实就是边界清楚，答得圆滑就是包装，这两句的差别全在投入分配说不说得清。",
        },
        {
            "key": "next_step",
            "text": "（mock）收尾问如果继续做怎么改：把没拆开的归因、缺的那一套评测、没埋的业务指标讲成下一步计划。",
        },
    ]
    return {
        "narrative": {
            "title": "（mock）把这一组项目讲成一条从「找得到」到「判得准」再到「可运营」的成长线",
            "stages": stages,
            "one_line": "（mock）先解决依据从哪来，再解决判断能不能复现，最后解决系统能不能越用越好——"
            "这几个项目不是同一件事做几遍，是同一套能力在几种约束下的不同组合。",
        },
        "rounds": rounds,
        "reuse_read": "（mock）共用的那几只组件说明这套选型是稳定的，不是每个项目现学一遍。",
        "unique_read": "（mock）只在一个项目里出现的那几只，说明选型是跟着场景走的，不是照搬上一版。",
        "sameness_answer": "（mock）回答「是不是换皮」分两层：先说共用栈证明熟练，再说差异栈证明跟着场景走；"
        "顺序反了就像在辩解，先承认骨架相同再给差异点才站得住。",
        "strategy": "（mock）每一轮备一段能讲一分钟的口述稿；第三轮与第四轮是组合层的胜负手，"
        "单项目准备得再足，跨项目对比答不好也显得这几个项目之间没有想过。",
        "usage": "（mock）讲组合时先看横向对比找到每个项目最独特的那一点，再用叙事主线串成递进，"
        "陪练时重点过跨项目对比与质疑真实性那两轮。",
    }


def _mock_portfolio_advice(prompt: str) -> dict[str, Any]:
    projects = _mock_portfolio_projects(prompt)
    order = [index for index, _name, _quote in projects]
    reverse = list(reversed(order))
    arrangements = [
        {
            "project_indices": order,
            "scenario": "（mock）目标岗位偏这条主线时按简历顺序排",
            "pros": "（mock）最亮的那一条排在前面抓眼球，后面的托底",
            "cons": "（mock）如果排在第二位的那一份分数更高，会被问为什么不把更强的放前面",
        }
    ]
    if reverse != order:
        arrangements.append(
            {
                "project_indices": reverse,
                "scenario": "（mock）目标岗位偏另一条方向时把它们倒过来排",
                "pros": "（mock）指标最完整的那一份放最前面最稳，追问时先立住",
                "cons": "（mock）最能体现架构能力的那一条被挪到最后，容易被忽略",
            }
        )
    else:
        arrangements.append(
            {
                "project_indices": order,
                "scenario": "（mock）只保留其中一份时的取舍（两个项目这一种排法与上面相同）",
                "pros": "（mock）留最完整的那一份，另一份的亮点作为补充讲",
                "cons": "（mock）少了一个领域跨度，广度这一层要另找地方体现",
            }
        )
    return {
        "arrangements": arrangements,
        "default_choice": 0,
        "default_reason": "（mock）默认按简历顺序，因为它正好形成一条递进；目标岗位明确偏向另一个方向时再调整。",
        "asked_before": [
            {
                "asked": "（mock）这几个项目有什么本质不同？",
                "answer": "（mock）骨架确实相同，解决的核心问题不一样：一个解决依据从哪来，一个解决判断能不能复现，"
                "一个解决系统能不能越用越好。所以它们是同一套能力在几种约束下的不同组合。",
            },
            {
                "asked": "（mock）为什么技术栈重叠这么多？",
                "answer": "（mock）重叠的那几只是这一类系统的基础组件，都用到说明熟练；"
                "差异的那几只是跟着场景选的，说明不是照搬。两层分开说才不会像在辩解。",
            },
            {
                "asked": "（mock）跨度这么大，你一个人怎么做的？",
                "answer": "（mock）先说参与边界：每个项目我负责的模块不一样，有的偏检索、有的偏编排、有的偏知识库。"
                "骨架是通用的，要学的是每个领域的判断标准，那部分是跟业务方一起定的，不是我一个人拍。",
            },
            {
                "asked": "（mock）如果只留一个，你留哪个？",
                "answer": "（mock）留指标闭环最完整的那一份：它有前后对比、有明确的工程边界、有人工介入的那一档口径，"
                "从任何角度问都接得住；其余几份的亮点可以作为补充在这一个项目里带出来。",
            },
        ],
        "strengthen": [
            {
                "gap": "（mock）归因都合在一起测",
                "action": "固定其他变量、每次只改一处、同一套样本跑对照，每个项目各补一版分项",
                "expected": "（mock）组合 D3 指标责任这一维站得住，D2 区分度也更实",
            },
            {
                "gap": "（mock）业务效果普遍偏薄",
                "action": "每个项目补一到两个业务口径：复核通过率、退回率、复用次数",
                "expected": "（mock）补上之后 D2 组合区分度与真实感更稳，追问不落空",
            },
            {
                "gap": "（mock）叙事顺序没有设计",
                "action": "按递进关系重排并给每段写一句「它解决的那一个核心问题」",
                "expected": "（mock）D6 位次与叙事这一维不靠运气，D4 纵深那条线也看得清",
            },
        ],
        "citation": {
            "borrow": "（mock）值得学的是这一组的组织方式：每个项目抓一个最独特的点，项目之间形成递进，"
            "共用栈展示熟练、差异栈展示判断。",
            "adapt": "（mock）不能照搬的是领域词与指标口径：换个方向就要把自己真做过的那一处决策写出来，"
            "否则几个项目会塌成同一套技术换个领域。",
            "breaks": "（mock）一抄就穿的是把几个项目都写成「我主导」、都套同一套指标口径、"
            "把跨度讲得理所当然——这三处都要先有参与边界与时间线才敢写。",
        },
    }


def _mock_portfolio_questions(prompt: str) -> dict[str, Any]:
    projects = _mock_portfolio_projects(prompt)
    tail = (
        "把这几个项目放在一起看，骨架确实是同一套：非结构化内容进库、多路召回取依据、在依据上做判断、"
        "不确定的部分交给人复核。但每个项目要解决的核心问题不一样，所以组合出来的方案也不一样。"
        "我负责的是把这套通用骨架落到具体领域里，领域的判断标准是跟业务方一起定的、不是我一个人拍的。"
        "如果重来一次，我会把每一项改动的贡献单独测一遍，而不是几项一起上——归因不清楚，后面的优化方向就是盲目的。"
    )
    items = []
    for position in range(12):
        kind = _PORTFOLIO_KINDS[position % len(_PORTFOLIO_KINDS)]
        status = "需补强" if position == 10 else "可答"
        items.append(
            {
                "question": f"（mock）跨项目追问（{kind}这一类）：面试官把几个项目摊在桌上会问出口的那一句",
                "kind": kind,
                "answer": _mock_portfolio_quote(projects, position) + tail,
                "followups": [
                    {"kind": "为什么", "text": "（mock）追问一：这一条为什么这么定，换一个方案会怎样"},
                    {"kind": "数据", "text": "（mock）追问二：这一层的口径怎么测、样本量多少、谁在看"},
                ],
                "status": status,
                "missing": ["（mock）缺一个分项差值：没拆开测就不敢说这一层各贡献多少"] if status != "可答" else [],
                "risk_ref": None,
            }
        )
    return {"questions": items}


def _mock_chat(prompt: str) -> str:
    """根据 prompt 关键字返回对应 mock JSON，包裹在 ```json``` 里"""
    # ---- 智能调度层：意图路由（优先级最高）----
    if "智能调度专家" in prompt:
        return _wrap_json(_MOCK_DISPATCH)

    # ---- 第五阶段：简历评估报告的三支（模块一~二/三 概览、批改稿、面试预演）----
    # 这一段必须排在智能体那一段**之前**：面试预演的 prompt 角色行逐字写着
    # 「你是一名资深面试辅导专家」，与 InterviewAgent 的派发关键字一模一样，
    # 顺序放后面就会把报告那一发领到 _MOCK_AGENT_INTERVIEW 上去（形状完全不同，且不报错）。
    # 三支都取正文那行「本次任务：简历评估报告 · X」，与各 prompt 同处改动。
    # 概览载荷的 `overall_score` 与七维之和不等于同一个数（72 vs 65），正是
    # `test_resume_report_overview.py` 要用的现成对照。
    if "简历评估报告 · 概览段" in prompt:
        return _wrap_json(_MOCK_REPORT_OVERVIEW)
    if "简历评估报告 · 批改稿" in prompt:
        return _wrap_json(_MOCK_REPORT_REDLINE)
    if "简历评估报告 · 面试预演" in prompt:
        return _wrap_json(_MOCK_REPORT_INTERVIEW)

    # ---- 单项目分析的四支（前三节三发 + 第四节一发）----
    # 同样必须排在智能体那一段之前：项目报告的 prompt 里也写着"资深"/"专家"式的角色行，
    # 排在后面就会被智能体的关键字先领走，形状完全不同还不报错（这条教训来自 D231）。
    if "单项目分析 · 一、项目档案" in prompt:
        return _wrap_json(_MOCK_PROJECT_PROFILE)
    if "单项目分析 · 二、项目图解" in prompt:
        return _wrap_json(_MOCK_PROJECT_DIAGRAMS)
    if "单项目分析 · 三、使用建议" in prompt:
        return _wrap_json(_MOCK_PROJECT_ADVICE)
    if "单项目分析 · 四、面试准备" in prompt:
        return _wrap_json(_MOCK_PROJECT_QUESTIONS)

    # ---- 组合分析的四支（前三节三发 + 第四节一发）----
    # 同上，这一族的 prompt 角色行也写着"技术负责人"，必须排在智能体段之前；
    # 四支都要现读 prompt 里被选中的项目清单，所以不能是写死的字典。
    if "组合分析 · 一、组合档案" in prompt:
        return _wrap_json(_mock_portfolio_profile(prompt))
    if "组合分析 · 二、组合图解" in prompt:
        return _wrap_json(_mock_portfolio_diagrams(prompt))
    if "组合分析 · 三、使用建议" in prompt:
        return _wrap_json(_mock_portfolio_advice(prompt))
    if "组合分析 · 四、跨项目面试" in prompt:
        return _wrap_json(_mock_portfolio_questions(prompt))

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


def _openai_compatible_chat(
    prompt: str,
    base_url: str = None,
    *,
    json_mode: bool = True,
    model: str = None,
    disable_thinking: bool = False,
) -> str:
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
    if disable_thinking:
        # 那一边照单执行，不是把未知字段丢掉（D194：reasoning_tokens=0、reasoning_content 消失）。
        payload["thinking"] = {"type": "disabled"}

    def _do():
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=settings.LLM_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            _record_usage(data.get("usage"), model=payload["model"])
            choice = data["choices"][0]
            message = choice["message"]
            content = message["content"]
            if not (content or "").strip():
                # 空 content 不是"JSON 不合法"：`finish_reason=length` + 一整串 reasoning token
                # 才是这一族的真形状（D189 在真上游量到 95.33s、8192 token 全花在思考链上）。
                # 判成 provider 失败：同一型号再打两次还是空，所以不进重试；但兜底链会换一发型号。
                raise LLMProviderError(
                    f"LLM 返回空内容 (finish_reason={choice.get('finish_reason')}, "
                    f"reasoning_chars={len(message.get('reasoning_content') or '')})"
                )
            return content
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


def _call_with_fallbacks(primary_call: Callable[[str, str | None], str], prompt: str) -> tuple[str, dict[str, Any]]:
    """LLM fallback chain: primary model -> fallback model -> simplified prompt -> mock (dev only).

    Returns (raw_text, provenance). Provenance reports which link in the chain
    actually produced the answer, because the configured provider alone does not
    tell a caller whether the content came from the model it thinks it asked.
    """
    errors: list[str] = []
    attempts: list[tuple[str, str, str | None]] = [("primary", prompt, None)]
    fallback_model = (settings.LLM_FALLBACK_MODEL or "").strip()
    if fallback_model and fallback_model != settings.LLM_MODEL:
        attempts.append(("fallback_model", prompt, fallback_model))
    if len(prompt or "") > _SIMPLIFIED_PROMPT_MAX_CHARS:
        attempts.append(("truncated", _simplify_prompt(prompt), fallback_model or None))

    for label, candidate_prompt, model in attempts:
        try:
            if label != "primary":
                logger.warning("LLM fallback attempt=%s model=%s", label, model or settings.LLM_MODEL)
            raw = primary_call(candidate_prompt, model)
            if label == "primary":
                return raw, _provenance("real")
            return raw, _provenance(
                label,
                reason=f"主模型调用失败，改由 {label} 链路应答: " + " | ".join(errors)[-300:],
                attempts=list(errors),
            )
        except (RuntimeError, LLMProviderError) as exc:
            errors.append(f"{label}: {exc}")

    if provider_allows_mock_fallback():
        logger.warning("LLM fallback attempt=mock after failures: %s", " | ".join(errors)[-500:])
        return _mock_chat(prompt), _provenance(
            "mock",
            reason="真实模型链路全部失败，已回退到本地 mock 模板，内容并非模型生成",
            attempts=list(errors),
        )

    raise LLMProviderError("AI 调用失败，fallback 链路均未成功: " + " | ".join(errors)[-800:])


def provider_allows_mock_fallback() -> bool:
    """生产环境默认禁止回退到 mock；开发环境可通过 LLM_ALLOW_MOCK_FALLBACK=true 显式开启。"""
    if settings.is_production:
        return bool(settings.LLM_ALLOW_MOCK_FALLBACK)
    return str(settings.LLM_FALLBACK_MODEL or "").strip().lower() == "mock" or bool(settings.LLM_ALLOW_MOCK_FALLBACK)


# ===================== 对外统一接口 =====================


def chat_json(prompt: str, schema: type[BaseModel] | None = None, *, disable_thinking: bool = False) -> dict[str, Any]:
    """
    唯一对外接口：输入 prompt，输出解析后的 dict
    - mock：本地模板，无网络
    - openai / qwen / local：走 OpenAI 兼容协议

    异常处理：
    - AI 调用失败 → 抛 RuntimeError
    - 返回内容非合法 JSON → 尝试提取，仍失败抛 ValueError

    `disable_thinking` 只给**同步等这一发、且输出预算会被思考链吃光**的调用（默认 False ⇒ 其余
    34 个调用方行为不变）。它不是性能开关：D189 量到同一份简历 prompt 开着思考链 91.77s / 95.33s
    返回 `content` 长度 0，D195 关掉后 10.68s 出 3 条可用建议。
    """
    provider = (settings.LLM_PROVIDER or "mock").lower()
    # E28：真花钱之前先扣用户的额度。放在 trace 之前，超额的那次不会留下"看起来跑过"的审计行；
    # 也放在降级/重试链之外 —— 抛出的 LLMQuotaExceededError 不会被 `_call_with_fallbacks` 吞成降级。
    charge_if_real_provider(provider=provider)
    scope = LLMTraceScope.begin(prompt=prompt, provider=provider, writer="chat_json")
    persist_trace = scope.persist

    # ---- 0) 查缓存（命中则返回深拷贝，避免调用方改动污染缓存）----
    # 只有 source=real 的结果会被写入，所以命中必然等价于一次真实应答。
    key = _cache_key(provider, prompt, disable_thinking)
    with _LLM_CACHE_LOCK:
        cached = _LLM_CACHE.get(key)
        if cached is not None:
            _LLM_CACHE.move_to_end(key)  # LRU：命中刷新到最新
            # Cache holds only source=real entries, so a hit is still a genuine
            # model answer. Deliberately not traced: the cache path is the
            # DB-free fast path, and `cache_hit` in provenance carries the signal.
            set_llm_provenance(_provenance("real", cache_hit=True))
            return _validate_schema(copy.deepcopy(cached["result"]), schema)

    # Seed before calling so an exception path cannot leave the previous
    # call's provenance behind in the context.
    provenance = _provenance("unknown")
    set_llm_provenance(provenance)

    # 只在关的那一臂上出现这个 kwarg：默认臂对 `_openai_compatible_chat` 的调用形状与改动前
    # 逐字相同，其余 34 个调用方（以及按旧签名打桩的测试）一律不受影响。
    thinking_kwargs = {"disable_thinking": True} if disable_thinking else {}

    # ---- 1) 调用 AI 获取原始文本 ----
    try:
        if provider == "mock":
            raw = _mock_chat(prompt)
            provenance = _provenance("mock", reason="LLM_PROVIDER=mock，内容由本地模板生成，非模型输出")
        elif provider in ("openai", "qwen"):
            raw, provenance = _call_with_fallbacks(
                lambda candidate_prompt, model: _openai_compatible_chat(
                    candidate_prompt, json_mode=True, model=model, **thinking_kwargs
                ),
                prompt,
            )
        elif provider == "local":
            raw, provenance = _call_with_fallbacks(
                lambda candidate_prompt, model: _openai_compatible_chat(
                    candidate_prompt,
                    base_url=settings.LLM_BASE_URL or "http://localhost:11434/v1",
                    json_mode=True,
                    model=model,
                    **thinking_kwargs,
                ),
                prompt,
            )
        else:
            raise ValueError(f"unknown LLM_PROVIDER: {provider}")
        set_llm_provenance(provenance)
    except LLMProviderError as e:
        scope.record_failure(error_type=type(e).__name__, error=e, provenance=provenance)
        raise  # 直接向上冒泡，保留类型化异常
    except RuntimeError as e:
        scope.record_failure(error_type="RuntimeError", error=e, provenance=provenance)
        raise LLMProviderError(f"AI 调用失败: {str(e)}") from e
    except Exception as e:
        scope.record_failure(error_type=type(e).__name__, error=e, provenance=provenance)
        raise LLMProviderError(f"AI 调用异常: {str(e)}") from e

    # 成功时记录指标
    scope.record_metrics(degraded=bool(provenance["degraded"]), provenance=provenance)

    # ---- 2) 将 AI 返回文本解析为 JSON ----
    try:
        result = extract_json(raw)
    except ValueError as exc:
        persist_trace(status="failed", response_text=raw, error_message=str(exc), provenance=provenance)
        # 尝试兜底：AI 说了"抱歉"之类非 JSON 内容。
        # 注意：不要把 raw 原始响应片段拼进错误信息——它会沿外部 API 的错误路径
        # 原样回给调用方，造成 LLM 返回内容泄漏；raw 已由 persist_trace 落库留痕。
        raise ValueError("AI 返回内容不是合法 JSON，无法解析") from exc
    try:
        result = _validate_schema(result, schema)
    except ValueError as exc:
        persist_trace(status="failed", response_text=raw, error_message=str(exc), provenance=provenance)
        raise
    persist_trace(status="success", response_text=raw, response_json=result, provenance=provenance)

    # ---- 3) 写入缓存（带容量上限的 LRU 淘汰）----
    # mock / truncated / fallback 应答一律不缓存：否则一次瞬时故障会把伪造内容
    # 长期钉在缓存键上，之后每次命中都被当成真实模型输出。
    if provenance["source"] in CACHEABLE_RESPONSE_SOURCES:
        with _LLM_CACHE_LOCK:
            _LLM_CACHE[key] = {"result": copy.deepcopy(result), "source": provenance["source"]}
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
            data = resp.json()
            # Tool calls were previously the only LLM path that spent tokens
            # without recording them, so any agent using tools billed as zero.
            _record_usage(data.get("usage"), model=payload["model"])
            return data
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
    # 工具循环一轮就是一次真调用，所以在这里按整次请求扣一格（与 chat_json 同口径）。
    charge_if_real_provider(provider=provider)

    # ---- mock 无工具能力，降级 ----
    if provider == "mock":
        logger.info("[chat_with_tools] mock provider 不支持工具调用，降级为 chat_json")
        result = chat_json(prompt)
        set_llm_provenance({**get_llm_provenance(), "reason": "mock provider 不支持工具调用，已降级为模板应答"})
        return result

    # ---- 准备工具定义（OpenAI 格式）----
    tool_defs = None
    tool_map = {}  # name → Tool 对象，用于执行回调
    if tools:
        tool_defs = [t.to_openai_tool() if isinstance(t, Tool) else t for t in tools]
        for t in tools:
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

    # 工具路径过去一行取证都不写：唯一调用它的 MatchAnalysisAgent（线性策略最关键
    # 一步）的输入输出因此完全不在审计链里。用量在 A 阶段已经记上了，缺的是这条。
    scope = LLMTraceScope.begin(prompt=prompt, provider=provider, writer="chat_with_tools")
    tools_used: set[str] = set()
    provenance = _provenance("unknown")
    set_llm_provenance(provenance)

    def _trace_extra(round_index: int) -> dict[str, Any]:
        return {
            "tool_rounds": round_index,
            "tools_used": sorted(tools_used),
            "tools_offered": sorted(tool_map) or None,
            "max_tool_rounds": max_tool_rounds,
        }

    # ---- 主循环：工具调用 ↔ LLM 推理 ----
    for _round in range(max_tool_rounds):
        try:
            response = _openai_compatible_chat_with_tools(messages, tools=tool_defs)
        except Exception as exc:
            scope.record_failure(error_type=type(exc).__name__, error=exc, provenance=provenance)
            raise
        choice = response["choices"][0]
        msg = choice["message"]

        # 情况 A: LLM 选择直接回复（无工具调用）
        if not msg.get("tool_calls"):
            content = msg.get("content", "")
            if content and content.strip():
                provenance = _provenance("real", reason=f"含 {_round + 1} 轮工具调用后的模型应答")
                set_llm_provenance(provenance)
                result = extract_json(content)
                scope.record_metrics(degraded=False, provenance=provenance)
                scope.persist(
                    status="success",
                    response_text=content,
                    response_json=result,
                    provenance=provenance,
                    extra=_trace_extra(_round + 1),
                )
                return result
            # content 为空但也没 tool_calls → 异常
            error = ValueError(f"LLM 返回空内容且无工具调用 (finish_reason={choice.get('finish_reason')})")
            scope.record_failure(error_type="ValueError", error=error, provenance=provenance)
            raise error

        # 情况 B: LLM 请求调用工具
        assistant_msg = {"role": "assistant", "content": msg.get("content")}
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        messages.append(assistant_msg)

        for tc in msg["tool_calls"]:
            fn_name = tc["function"]["name"]
            tools_used.add(fn_name)
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
    # NOTE: after a tool round messages[-1] is the *tool* reply, so this parses
    # tool output as if it were the model's analysis. Flagged degraded rather
    # than silently presented as a model answer; fixing the behaviour itself
    # needs its own regression test.
    logger.warning("[chat_with_tools] 达到最大工具轮次 %d，尝试从最后消息提取 JSON", max_tool_rounds)
    last_content = messages[-1].get("content", "")
    if isinstance(last_content, str) and last_content.strip():
        try:
            result = extract_json(last_content)
        except ValueError:
            result = None
        if result is not None:
            provenance = _provenance(
                "tool_output",
                reason=f"模型在 {max_tool_rounds} 轮工具调用内未给出最终答复，此处返回的是工具输出而非模型分析",
            )
            set_llm_provenance(provenance)
            scope.record_metrics(degraded=True, provenance=provenance)
            scope.persist(
                status="success",
                response_text=last_content,
                response_json=result,
                provenance=provenance,
                extra=_trace_extra(max_tool_rounds),
            )
            return result

    error = RuntimeError(f"工具调用超过 {max_tool_rounds} 轮仍未返回有效 JSON，请简化任务或重试")
    scope.record_failure(error_type="RuntimeError", error=error, provenance=provenance)
    raise error
