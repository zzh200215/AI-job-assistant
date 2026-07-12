"""
LLM 输出解析与降级工具。
提供安全的 JSON 解析、空结果处理和结构化数据提取。
"""
import json
import logging
import re
from typing import Any, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def safe_parse_json(
    raw: str,
    default: Any = None,
    log_error: bool = True,
) -> Optional[dict]:
    """
    安全解析 LLM 返回的 JSON。
    
    降级策略：
    1. 直接 json.loads
    2. 尝试提取 ```json ... ``` 代码块
    3. 尝试提取最外层 {...}
    4. 返回 default
    """
    if not raw or not raw.strip():
        if log_error:
            logger.warning("safe_parse_json: 输入为空")
        return default

    # 策略 1：直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 策略 2：提取 ```json ... ``` 块
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 策略 3：提取最外层 {...}
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    if log_error:
        logger.warning("safe_parse_json: 所有解析策略均失败，raw=%s", raw[:200])

    return default


def safe_extract_list(
    raw: Any,
    default: Optional[list] = None,
) -> list:
    """
    安全提取列表数据。
    处理 LLM 返回的字段可能是 list、单个 dict、逗号分隔字符串等情况。
    """
    if default is None:
        default = []

    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, str):
        # 可能是 JSON 字符串
        parsed = safe_parse_json(raw, default=default)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        # 可能是逗号分隔
        items = [s.strip() for s in raw.split(",") if s.strip()]
        return items if items else default

    return default


def safe_extract_score(
    raw: Any,
    field_names: list[str],
    min_val: float = 0,
    max_val: float = 100,
    default: float = 60,
) -> float:
    """
    安全提取数值评分。
    尝试多个字段名（LLM 不同版本可能返回不同字段名）。
    """
    if not isinstance(raw, dict):
        return default

    for f in field_names:
        val = raw.get(f)
        if val is not None:
            try:
                v = float(val)
                if min_val <= v <= max_val:
                    return v
            except (ValueError, TypeError):
                continue

    return default


def ensure_json_output(
    raw: str,
    schema_template: dict,
) -> dict:
    """
    确保 LLM 输出为指定结构的 JSON。
    如果解析失败，返回 template 的副本。
    """
    result = safe_parse_json(raw, default=None)
    if result is not None and isinstance(result, dict):
        # 合并：用 LLM 返回的值覆盖 template 中的默认值
        merged = dict(schema_template)
        merged.update(result)
        return merged

    logger.warning("ensure_json_output: 解析失败，返回模板默认值")
    return dict(schema_template)
