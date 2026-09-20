"""C6 — 工具调用路径的取证。

`chat_json` 一直自带 prompt_trace 落盘，`chat_with_tools` 一行都没有：于是
`MatchAnalysisAgent`（线性策略里唯一调工具、也是最关键的匹配节点）的输入输出
完全不在审计链里——出了问题只能看到"这个节点花了 729 token"，看不到它问了什么、
调了哪些工具、最后拿什么当答案。
"""

from typing import Any

import pytest

from app.core.config import settings
from app.models.prompt_trace import PromptTrace
from app.services import llm_service


class _FakeTool:
    name = "search_knowledge"

    def execute(self, **kwargs) -> dict[str, Any]:
        return {"success": True, "results": [{"chunk_id": "c1", "text": "知识内容"}]}


def _tool_call_response(name: str = "search_knowledge", arguments: str = '{"query":"x"}') -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [{"id": "call_1", "function": {"name": name, "arguments": arguments}}],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }


def _content_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


@pytest.fixture
def live_provider(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "qwen")
    monkeypatch.setattr(llm_service, "get_tool", lambda name: _FakeTool() if name == "search_knowledge" else None)


@pytest.fixture
def trace_db(db_session, normal_user):
    llm_service.set_llm_trace_context(
        {"source": "agent.MatchAnalysisAgent", "task_id": 4242, "user_id": normal_user.id, "db": db_session}
    )
    return db_session


def _rows(db) -> list[PromptTrace]:
    return db.query(PromptTrace).filter_by(task_id=4242).order_by(PromptTrace.id).all()


def test_tool_answer_is_traced_with_rounds_and_tools(live_provider, trace_db, monkeypatch):
    """一轮工具 + 一轮作答：留一行 success，带 tool_rounds / tools_used。"""
    calls = iter([_tool_call_response(), _content_response('{"match_score": 88}')])
    monkeypatch.setattr(llm_service, "_openai_compatible_chat_with_tools", lambda *a, **k: next(calls))

    result = llm_service.chat_with_tools("分析这份简历", tools=None)

    assert result == {"match_score": 88}
    rows = _rows(trace_db)
    assert len(rows) == 1
    row = rows[0]
    assert (row.status, row.response_source, row.degraded) == ("success", "real", False)
    assert row.source == "agent.MatchAnalysisAgent"
    assert row.response_json == {"match_score": 88}
    # build_trace_context 会把 extra 平铺进 context，所以这些键是顶层的
    assert row.trace_context["tool_rounds"] == 2
    assert row.trace_context["tools_used"] == ["search_knowledge"]


def test_rounds_exhausted_is_traced_as_degraded(live_provider, trace_db, monkeypatch):
    """轮次耗尽后返回的是工具输出——必须留成 degraded 行，而不是冒充模型分析。"""
    monkeypatch.setattr(llm_service, "_openai_compatible_chat_with_tools", lambda *a, **k: _tool_call_response())

    result = llm_service.chat_with_tools("分析这份简历", tools=None, max_tool_rounds=2)

    assert result["results"][0]["chunk_id"] == "c1"
    row = _rows(trace_db)[0]
    assert row.response_source == "tool_output"
    assert bool(row.degraded) is True
    assert row.trace_context["tool_rounds"] == 2


def test_provider_failure_is_traced_as_failed(live_provider, trace_db, monkeypatch):
    """模型侧报错也要有一行 failed：否则审计里这次调用根本发生过。"""

    def _boom(*_a, **_k):
        raise RuntimeError("AI 接口调用失败")

    monkeypatch.setattr(llm_service, "_openai_compatible_chat_with_tools", _boom)

    with pytest.raises(RuntimeError):
        llm_service.chat_with_tools("分析这份简历", tools=None)

    row = _rows(trace_db)[0]
    assert row.status == "failed"
    assert "AI 接口调用失败" in (row.error_message or "")


def test_unparseable_final_json_is_traced_as_failed(live_provider, trace_db, monkeypatch):
    """兜底提取也拿不到 JSON 时同样留失败行。"""

    def _tool_only(*_a, **_k):
        return _tool_call_response()

    def _no_json(_text):
        raise ValueError("AI 返回内容不是合法 JSON")

    monkeypatch.setattr(llm_service, "_openai_compatible_chat_with_tools", _tool_only)
    monkeypatch.setattr(llm_service, "extract_json", _no_json)

    with pytest.raises(RuntimeError):
        llm_service.chat_with_tools("分析这份简历", tools=None, max_tool_rounds=1)

    assert _rows(trace_db)[0].status == "failed"


def test_empty_content_without_tool_calls_is_traced(live_provider, trace_db, monkeypatch):
    monkeypatch.setattr(llm_service, "_openai_compatible_chat_with_tools", lambda *a, **k: _content_response("   "))

    with pytest.raises(ValueError):
        llm_service.chat_with_tools("分析这份简历", tools=None)

    row = _rows(trace_db)[0]
    assert row.status == "failed"
    assert "空内容" in (row.error_message or "")


def test_mock_provider_still_delegates_without_its_own_row(live_provider, trace_db, monkeypatch):
    """mock 无工具能力时降级为 chat_json——由 chat_json 那一侧留一行，不重复记账。"""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")

    llm_service.chat_with_tools("分析这份简历", tools=None)

    assert len(_rows(trace_db)) == 1
