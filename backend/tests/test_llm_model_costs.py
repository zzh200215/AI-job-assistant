"""D187：LLM 成本按型号算——`_record_usage` 早就拿得到 `model`，只是没用过它。

**先钉住一个前提**：今天 SenseNova 官方页写"公测期完全免费开放，付费档位即将上线"，
所以 `cost_cents` 为 0 **是准的**，这一族测试不是在修一个错的数。要修的是结构：
只有 `LLM_INPUT/OUTPUT_COST_PER_1K_CENTS` 两个全局数，而 2026-10-10 起主备是两个不同型号
（`deepseek-v4-flash` + `glm-5.2`），付费档位上线那天两个数无法分别表达，成本会静默错。
"""

from __future__ import annotations

import logging

import pytest

from app.core.config import Settings
from app.services import llm_service

PROD_BASE = {
    "APP_ENV": "development",
    "LLM_PROVIDER": "openai",
    "LLM_API_KEY": "sk-x",
    "LLM_BASE_URL": "https://token.sensenova.cn/v1",
    "LLM_MODEL": "deepseek-v4-flash",
    "LLM_INPUT_COST_PER_1K_CENTS": 9.0,
    "LLM_OUTPUT_COST_PER_1K_CENTS": 9.0,
}


def _settings(**over):
    payload = dict(PROD_BASE)
    payload.update(over)
    payload.setdefault("LLM_MODEL_COSTS", "")
    return Settings(**payload)


def test_a_listed_model_beats_the_global_pair_and_an_unlisted_one_falls_back():
    s = _settings(LLM_MODEL_COSTS="deepseek-v4-flash:0.02:0.2")
    assert s.unit_costs_for("deepseek-v4-flash") == (0.02, 0.2)
    assert s.unit_costs_for("glm-5.2") == (9.0, 9.0), "没列出的型号必须退回两个全局数（今天的行为）"
    assert s.unit_costs_for(None) == (9.0, 9.0)


def test_the_lookup_is_case_and_space_tolerant():
    """型号名会从小写配置一路传到大写响应里，判据不该被大小写与空格绊倒。"""
    s = _settings(LLM_MODEL_COSTS="DeepSeek-V4-Flash:0.02:0.2")
    assert s.unit_costs_for("  deepseek-v4-flash ") == (0.02, 0.2)


def test_malformed_entries_are_skipped_with_a_warning_not_a_crash(caplog):
    """单价表是运维配置：一个逗号不能让算钱或启动崩，但也不能静默吞。"""
    s = _settings(LLM_MODEL_COSTS="no-colon, broken:1, ok:1:2, numeric-name:5:x")
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        costs = s.llm_model_costs
    assert costs == {"ok": (1.0, 2.0)}
    warnings = [r.getMessage() for r in caplog.records]
    assert sum("LLM_MODEL_COSTS" in m for m in warnings) == 3, warnings


def test_record_usage_prices_by_the_model_that_answered(monkeypatch):
    """同一次调用里主备换了型号，成本要跟着型号走——这正是两个全局数做不到的事。"""
    monkeypatch.setattr(
        llm_service, "settings", _settings(LLM_MODEL_COSTS="deepseek-v4-flash:0.02:0.2,glm-5.2:0.06:0.4")
    )
    llm_service._LLM_USAGE_CONTEXT.set(
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_cents": 0.0}
    )

    llm_service._record_usage({"prompt_tokens": 1000, "completion_tokens": 1000}, model="deepseek-v4-flash")
    after_primary = llm_service.get_llm_usage()
    assert round(after_primary["cost_cents"], 6) == round(0.02 + 0.2, 6)

    llm_service._record_usage({"prompt_tokens": 1000, "completion_tokens": 1000}, model="glm-5.2")
    after_fallback = llm_service.get_llm_usage()
    assert round(after_fallback["cost_cents"], 6) == round(0.22 + 0.06 + 0.4, 6), "第二发没按 glm-5.2 的单价算"


def test_the_shipped_default_is_still_zero_because_the_vendor_is_free_in_beta():
    """这条钉的是**前提**：留空 = 0 成本是当下的事实，不是漏配。

    谁要"顺手补个数"，得先把 SenseNova 的付费档位页拿到手——不然管理页那个
    `avg_cost_cents` 会从"真 0"变成"假 0.02"，比现在更糟。
    """
    assert Settings.model_fields["LLM_MODEL_COSTS"].default == ""
    assert Settings.model_fields["LLM_INPUT_COST_PER_1K_CENTS"].default == 0.0
    assert Settings.model_fields["LLM_OUTPUT_COST_PER_1K_CENTS"].default == 0.0
    fresh = Settings()
    assert fresh.unit_costs_for("deepseek-v4-flash") == (0.0, 0.0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", {}),
        ("   ", {}),
        ("a:1:2,,b:3:4", {"a": (1.0, 2.0), "b": (3.0, 4.0)}),
        ("  a:1:2  ", {"a": (1.0, 2.0)}),
    ],
)
def test_blank_and_padded_lists_parse_to_exactly_what_they_say(raw: str, expected: dict):
    s = _settings(LLM_MODEL_COSTS=raw)
    assert s.llm_model_costs == expected
