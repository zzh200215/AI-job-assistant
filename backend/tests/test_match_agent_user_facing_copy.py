"""匹配分析失败时，那几个**会上屏**的字段只能用我们自己的话（D15）。

2026-11-16 真浏览器验收撞见的：结果页"匹配度 33"下面那行读起来是

    analysis unavailable: [LLM-Tools] 调用失败（已重试 2 次）: AI 接口调用失败(HTTP 429)，请稍后重试

也就是说 `match_analysis_agent` 把 provider 的异常原文当成了 `summary`，而 `summary` 会原样渲染。
同一处的 `gaps` / `risk_points` 也是英文技术句。这条判据钉三件事：

1. 上屏的三个字段里没有任何英文技术句 / 异常原文；
2. 原始异常仍然留在 `_error` 里（运维要证据，而且这条判据不许把证据一起删掉）；
3. `summary` 的默认值（模型回了 JSON 但缺字段）也不再是 `"analysis incomplete"`。
"""

from __future__ import annotations

from app.agents.match_analysis_agent import MatchAnalysisAgent

LEAK = "[LLM-Tools] 调用失败（已重试 2 次）: AI 接口调用失败(HTTP 429)，请稍后重试"
USER_FACING = ("summary", "gaps", "risk_points")


def _agent() -> MatchAnalysisAgent:
    agent = MatchAnalysisAgent.__new__(MatchAnalysisAgent)  # 不走 __init__，这条判据不碰 tool 注册
    return agent


def _texts(result: dict) -> str:
    parts: list[str] = []
    for key in USER_FACING:
        value = result.get(key)
        parts.extend(value if isinstance(value, list) else [value or ""])
    return " ".join(str(part) for part in parts)


def test_a_failed_call_never_puts_the_provider_error_on_screen(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError(LEAK)

    monkeypatch.setattr("app.services.llm_service.chat_with_tools", boom)

    result = _agent()._call_llm_with_tools("prompt", [])

    shown = _texts(result)
    assert "HTTP 429" not in shown, f"异常原文漏到上屏字段：{shown}"
    assert "LLM-Tools" not in shown
    assert "unavailable" not in shown.lower()
    assert "failed" not in shown.lower()
    # 自己的话说清楚了"没拿到"，而不是装作没事也没装成英文
    assert "没能拿到" in shown
    assert "不完整" in shown


def test_the_raw_error_is_still_kept_for_ops(monkeypatch):
    """反证：上面那条不许靠"把证据一起删掉"来变绿。"""

    def boom(*_args, **_kwargs):
        raise RuntimeError(LEAK)

    monkeypatch.setattr("app.services.llm_service.chat_with_tools", boom)

    result = _agent()._call_llm_with_tools("prompt", [])

    assert LEAK in result["_error"]


def test_a_reply_without_a_summary_gets_our_sentence_not_english(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm_service.chat_with_tools",
        lambda **_kwargs: {"match_score": 61},
    )

    result = _agent()._call_llm_with_tools("prompt", [])

    assert result["summary"] != "analysis incomplete"
    assert "摘要" in result["summary"]
