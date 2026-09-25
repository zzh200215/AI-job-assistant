"""真实 provider 的 HTTP 路径在 CI 里跑一遍（E18）。

债表那条"测试覆盖真实路径为零"的具体含义是：`conftest` 把 `LLM_PROVIDER`/`EMBEDDING_PROVIDER`
钉成 mock，所以 `_openai_compatible_chat` / `_openai_compatible_chat_with_tools` 里
`requests.post` 那段**一行都没被执行过**——URL 拼接、鉴权头、payload 形状、超时/429/5xx 的
可重试分类、4xx 不重试、JSON 解析失败、以及 C6 那条工具循环，全是"写了但没人跑过"的代码。

这里不接真 provider（要花钱，且没批），而是把 `LLM_BASE_URL` 指向一个本地
OpenAI 兼容假服务：跑的是**生产同一段客户端代码**，包括 `requests` 的真实 socket。
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core.config import settings
from app.services import llm_service

CHOICE_CONTENT = {"answer": "好", "score": 88}


class FakeProvider:
    """按队列回答；队列耗尽后重复最后一条（这样"每次重试都失败"是默认行为）。"""

    def __init__(self) -> None:
        self.responses: list[tuple[int, dict]] = []
        self.requests: list[dict] = []
        self.sleep_seconds = 0.0

    def next(self) -> tuple[int, dict]:
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

    def completion(self, message: dict, finish_reason: str = "stop") -> tuple[int, dict]:
        return (
            200,
            {
                "choices": [{"message": message, "finish_reason": finish_reason}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            },
        )


@pytest.fixture
def provider():
    fake = FakeProvider()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            fake.requests.append({"path": self.path, "auth": self.headers.get("authorization"), "body": body})
            if fake.sleep_seconds:
                time.sleep(fake.sleep_seconds)
            status, payload = fake.next()
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            with contextlib.suppress(OSError):
                self.wfile.write(data)  # 客户端可能已超时断开（WinError 10053），别污染测试输出

        def log_message(self, *args):  # 静音
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    llm_service.clear_llm_cache()
    saved = {
        "LLM_PROVIDER": settings.LLM_PROVIDER,
        "LLM_API_KEY": settings.LLM_API_KEY,
        "LLM_BASE_URL": settings.LLM_BASE_URL,
        "LLM_MODEL": settings.LLM_MODEL,
        "LLM_FALLBACK_MODEL": settings.LLM_FALLBACK_MODEL,
        "LLM_ALLOW_MOCK_FALLBACK": settings.LLM_ALLOW_MOCK_FALLBACK,
        "LLM_TIMEOUT": settings.LLM_TIMEOUT,
    }
    settings.LLM_PROVIDER = "openai"
    settings.LLM_API_KEY = "sk-local-test-key"
    settings.LLM_BASE_URL = f"http://127.0.0.1:{server.server_address[1]}/v1"
    settings.LLM_MODEL = "configured-model"
    settings.LLM_FALLBACK_MODEL = ""
    settings.LLM_ALLOW_MOCK_FALLBACK = False
    settings.LLM_TIMEOUT = 3
    try:
        yield fake
    finally:
        for name, value in saved.items():
            setattr(settings, name, value)
        llm_service.clear_llm_cache()
        server.shutdown()
        server.server_close()


def _content_response(content_obj) -> tuple[int, dict]:
    text = content_obj if isinstance(content_obj, str) else json.dumps(content_obj, ensure_ascii=False)
    return 200, {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}


def test_chat_json_sends_the_openai_contract_and_reports_real_provenance(provider):
    provider.responses = [_content_response(CHOICE_CONTENT)]

    result = llm_service.chat_json("请给出一个 JSON")

    assert result == CHOICE_CONTENT
    assert len(provider.requests) == 1
    sent = provider.requests[0]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["auth"] == "Bearer sk-local-test-key"
    assert sent["body"]["model"] == "configured-model"
    assert sent["body"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in sent["body"]["messages"]] == ["system", "user"]
    assert llm_service.get_llm_provenance()["source"] == "real"


def test_5xx_is_retried_and_4xx_is_not(provider, monkeypatch):
    monkeypatch.setattr(llm_service, "_LLM_MAX_RETRIES", 2)
    provider.responses = [(500, {"error": "boom"})]

    with pytest.raises(llm_service.LLMProviderError) as info:
        llm_service.chat_json("5xx 场景")
    assert len(provider.requests) == 3, "5xx 应重试：1 次首发 + 2 次重试"
    assert "服务端错误" in str(info.value)

    provider.requests.clear()
    provider.responses = [(401, {"error": "nope"})]
    with pytest.raises(llm_service.LLMProviderError):
        llm_service.chat_json("401 场景")
    assert len(provider.requests) == 1, "鉴权失败重试没有意义，必须只发一次"
    assert llm_service.get_llm_provenance()["source"] != "real"


def test_timeout_is_treated_as_retryable(provider, monkeypatch):
    monkeypatch.setattr(llm_service, "_LLM_MAX_RETRIES", 1)
    settings.LLM_TIMEOUT = 0.2
    provider.sleep_seconds = 0.45
    provider.responses = [_content_response(CHOICE_CONTENT)]

    # 注意抛给调用方的不是 LLMTimeoutError 而是聚合后的 LLMProviderError：`_call_with_fallbacks`
    # 把每一链的失败收进 errors，全链失败才抛。所以能断言的是"超时被归成可重试类且真的重试了"，
    # 不是异常类名——这条本身也算这次测试的一个收获（类名在公开路径上不带信息）。
    with pytest.raises(llm_service.LLMProviderError) as info:
        llm_service.chat_json("超时会怎样")
    assert "超时" in str(info.value)
    assert len(provider.requests) == 2, "超时属于可重试类，至少要发过两次"
    provider.sleep_seconds = 0.0


def test_unparseable_json_is_a_parse_error_not_a_crash(provider):
    provider.responses = [_content_response("这不是 JSON，也没有代码块")]

    with pytest.raises(ValueError):
        llm_service.chat_json("坏 JSON")


def test_tool_loop_executes_two_rounds_against_the_wire(provider):
    """C6 那条路径：`chat_with_tools` 以前从没被执行过一次。

    第一轮让模型要求调用一个不存在的工具，第二轮给最终 JSON —— 覆盖 tool_calls 解析、
    工具回执注回消息序列、以及"未知工具"分支。
    """
    provider.responses = [
        (
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "probe_tool", "arguments": '{"x": 1}'},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"total_tokens": 5},
            },
        ),
        _content_response({"final": True}),
    ]

    result = llm_service.chat_with_tools("用工具分析一下", tools=None)

    assert result == {"final": True}
    assert len(provider.requests) == 2, "两轮：一轮工具调用 + 一轮最终应答"
    second = provider.requests[1]["body"]["messages"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "tool"]
    assert second[2]["tool_calls"][0]["function"]["name"] == "probe_tool"
    assert "未知工具" in second[3]["content"]
    assert llm_service.get_llm_provenance()["source"] == "real"
