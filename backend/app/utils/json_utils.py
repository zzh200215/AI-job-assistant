# -*- coding: utf-8 -*-
"""稳健的 JSON 抽取：兼容 ```json``` 包裹、夹杂解释文字、嵌套对象等"""
import json
import re
from typing import Any, Optional


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _find_balanced_span(s: str) -> Optional[str]:
    """从字符串中找出第一个**括号配对平衡**的 JSON 值（对象或数组）。

    通过逐字符扫描并对 {}/[] 计数实现，正确处理嵌套结构与字符串字面量
    （含转义），避免非贪婪正则把嵌套对象截断到第一个 } 的问题。
    """
    start = None
    open_ch = close_ch = None
    for i, ch in enumerate(s):
        if ch in "{[":
            start = i
            open_ch = ch
            close_ch = "}" if ch == "{" else "]"
            break
    if start is None:
        return None

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None  # 括号未闭合


def extract_json(text: str) -> Any:
    """
    输入 LLM 原始返回，输出 dict/list。
    失败抛 ValueError。
    """
    if text is None:
        raise ValueError("empty LLM response")

    s = str(text).strip()

    # 1) 优先取 ```json ... ``` 代码块内容
    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()

    # 2) 抽取首个括号平衡的 JSON 片段（正确处理嵌套）
    span = _find_balanced_span(s)
    if span is not None:
        s = span

    # 3) 尝试解析
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        # 4) 兜底：去掉尾部多余逗号等小问题再试一次
        cleaned = re.sub(r",\s*([}\]])", r"\1", s)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            raise ValueError(f"无法从 LLM 返回中抽取 JSON: {e}; raw={text[:300]}")
