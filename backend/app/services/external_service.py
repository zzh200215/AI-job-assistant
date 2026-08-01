"""外部能力 API 适配层（T6-1）：无状态封装，复用共享服务层。

复用共享构建块（prompts / llm_service / file_parser），不复制分析逻辑。
外部调用方直接传内容（无平台 DB 行），区别于平台端点基于 resume_id/jd_id 的流程。
RAG 检索上下文：外部端点通过 api_key.tenant_id 注入租户上下文后可走 `use_rag=true`
复用 rag_service.build_rag_context_multi；默认不走 RAG，保证端点确定性。
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from app.prompts.answer_evaluation import ANSWER_EVALUATION_PROMPT
from app.prompts.interview import INTERVIEW_PROMPT
from app.prompts.match import MATCH_PROMPT
from app.prompts.rendering import render_prompt
from app.prompts.resume_parse import RESUME_PARSE_PROMPT
from app.services.llm_service import chat_json, set_llm_trace_context
from app.utils.file_parser import parse_resume

_RESUME_TEXT_MAX = 6000  # 与 resume_service.parse_and_save 一致


def _trace(db, *, source: str, prompt_name: str, **extra: Any) -> None:
    set_llm_trace_context(
        {
            "source": source,
            "prompt_name": prompt_name,
            "prompt_family": "external",
            "db": db,
            **extra,
        }
    )


def _jsonify(value: Any) -> dict:
    """接受 dict 或 JSON 字符串输入，统一返回 dict；纯文本回落为 {'raw_text': ...}。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass
        return {"raw_text": value}
    return {}


# ===== 简历解析 =====


def parse_resume_text(raw_text: str, db=None) -> dict:
    """简历文本 → 结构化 JSON（复用 RESUME_PARSE_PROMPT + chat_json）。"""
    if not raw_text or not raw_text.strip():
        raise ValueError("content 不能为空")
    prompt = render_prompt(RESUME_PARSE_PROMPT, resume_text=raw_text[:_RESUME_TEXT_MAX])
    _trace(db, source="external_service.parse_resume_text", prompt_name="resume_parse")
    return chat_json(prompt) or {}


def parse_resume_file(file_bytes: bytes, filename: str, db=None) -> dict:
    """简历文件字节 → 文本 → 结构化 JSON（复用 file_parser.parse_resume）。"""
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "txt").lower()
    fd, tmp = tempfile.mkstemp(suffix=f".{ext}")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(file_bytes)
        raw_text = parse_resume(tmp, ext)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return parse_resume_text(raw_text, db=db)


# ===== 匹配评估 =====


def evaluate_match(resume: Any, jd: Any, rag_context: str = "", db=None) -> dict:
    """简历 × JD 匹配度评估（复用 MATCH_PROMPT + chat_json）。"""
    resume_json = _jsonify(resume)
    jd_json = _jsonify(jd)
    prompt = render_prompt(
        MATCH_PROMPT,
        rag_context=rag_context,
        resume_json=json.dumps(resume_json, ensure_ascii=False),
        jd_json=json.dumps(jd_json, ensure_ascii=False),
    )
    _trace(db, source="external_service.evaluate_match", prompt_name="match")
    result: dict[str, Any] = chat_json(prompt) or {}
    try:
        result["match_score"] = max(0, min(100, int(result.get("match_score") or 0)))
    except (ValueError, TypeError):
        result["match_score"] = 0
    return result


# ===== 模拟面试（简化版） =====


def generate_interview_questions(resume: Any, jd: Any, rag_context: str = "", db=None) -> dict:
    """生成结构化面试题（复用 INTERVIEW_PROMPT + chat_json）。"""
    resume_json = _jsonify(resume)
    jd_json = _jsonify(jd)
    prompt = render_prompt(
        INTERVIEW_PROMPT,
        rag_context=rag_context,
        resume_json=json.dumps(resume_json, ensure_ascii=False),
        jd_json=json.dumps(jd_json, ensure_ascii=False),
    )
    _trace(db, source="external_service.generate_interview_questions", prompt_name="interview")
    return chat_json(prompt) or {}


def evaluate_answer(question: str, ref_answer: str, user_answer: str, db=None) -> dict:
    """逐题评分（复用 ANSWER_EVALUATION_PROMPT + chat_json）。"""
    prompt = render_prompt(
        ANSWER_EVALUATION_PROMPT,
        question=question or "",
        ref_answer=ref_answer or "",
        user_answer=user_answer or "",
    )
    _trace(db, source="external_service.evaluate_answer", prompt_name="answer_evaluation")
    return chat_json(prompt) or {}
