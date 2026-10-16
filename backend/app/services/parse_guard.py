"""解析的地基防护：预算内取文本 → 单发解析 → 结构校验 → **一次**自纠 → 把伤害落到 `_meta` 里。

出处 `简历与面试优化.md` §4 P1.1。修之前这条链是"单发无防护"的：`raw_text[:6000]` 从头上硬切
（切掉的正是文档尾部，那里常放着最近的工作经历），`chat_json` 返回什么就存什么，下游各写各的兜底。

三处 LLM 解析入口共用这里（**阈值与截断函数只有一份**，别只改主入口）：
`resume_service.parse_and_save`、`external_service.parse_resume_text`、`jd_service.parse_and_save`
（`agents/jd_parse_agent.py` 只是后者的壳）。

第四处 `jd_embedding_service` 的 `RAWS_TEXT_LIMIT = 6000` **故意不并进来**：那个预算量的是 embedding
模型的窗口，不是 LLM 的上下文，把 15000 套上去会把它推过窗口边界——那正是本项目当成反面教材的
CHUNK_SIZE 超窗同族 bug。它共享的是截断**函数**的语义（整段丢、不硬切），不是那个数。

`chat` 是**注入进来**的而不是在本模块 import：三处入口各自 `from ...llm_service import chat_json`，
测试换的是**各自模块**上的那个名字。这里再 import 一份，夹具就打不到，重试计数会静默停在 1。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from app.prompts.rendering import render_prompt
from app.utils.text_budget import RESUME_SECTIONS, SectionMap, fit_structured_text

# 文档 §4 P1.1 的新阈值。改这个数必须同时改那份文档——前置度量已经证明本库量不出它够不够（max 4,758）。
PARSE_INPUT_BUDGET = 15000

# 回喂那一发必须让模型认出"这不是原文，是判卷单"。这串字在两支 prompt 里都不出现（已 grep），
# 所以 `test_parse_guardrails` 能用它证明第二次调用真的带了校验错误，而不是把原文重发一遍。
REPAIR_HEADER = "【上一次输出未通过结构校验】"


def validation_errors(schema: type[BaseModel], payload: Any) -> list[str]:
    """把 pydantic 的报错压成"键名: 原因"的短句。空列表 = 结构合格。

    只报**顶层键**，内层 item 的字段一律可缺（见两个 Schema 的注释），否则一份写了 12 段经历、
    其中 1 段少个 start 的简历会把整份判废。
    """
    if not isinstance(payload, dict):
        return ["整体: 模型没有返回 JSON 对象"]
    try:
        schema.model_validate(payload)
    except ValidationError as exc:
        return [f"{'.'.join(str(part) for part in err['loc']) or '整体'}: {err['msg']}" for err in exc.errors()]
    return []


def guarded_parse(
    *,
    raw_text: str,
    prompt_template: str,
    text_key: str,
    schema: type[BaseModel],
    chat: Callable[[str], Any],
    budget: int = PARSE_INPUT_BUDGET,
    sections: SectionMap = RESUME_SECTIONS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """返回 (要落库的解析结果, `_meta` 标记)。`_meta` 为空字典时表示一切正常，调用方可以整块不写。"""
    fit = fit_structured_text(raw_text or "", budget, sections)
    prompt = render_prompt(prompt_template, **{text_key: fit.text})

    payload = chat(prompt)
    errors = validation_errors(schema, payload)
    if errors:
        # 一次为限：文档 §4 P1.1 明确"把校验错误回喂 LLM 修正一次"，不做循环重试——上限是钱的上限。
        repair_prompt = (
            f"{prompt}\n\n{REPAIR_HEADER}\n"
            + "\n".join(f"- {line}" for line in errors)
            + "\n上一版输出里上述字段缺失或类型不对。只修正这些问题，其余内容保持不变，"
            "按同一个 JSON Schema 重新输出完整结果（不要输出 JSON 以外的文字）。"
        )
        payload = chat(repair_prompt)
        errors = validation_errors(schema, payload)

    result: dict[str, Any] = dict(payload) if isinstance(payload, dict) else {}
    # 模型自己写的 `_meta` 一律不信：标记只能由这一处盖，否则候选人正文里的注入文本就能自行宣告"已降级"。
    result.pop("_meta", None)

    meta: dict[str, Any] = {}
    if fit.truncated:
        meta["truncation"] = {
            "truncated": True,
            "dropped_chars": fit.dropped_chars,
            "dropped_sections": fit.dropped_sections,
            "budget": budget,
        }
    if errors:
        meta["parse_degraded"] = True
        meta["validation_errors"] = errors
    return result, meta
