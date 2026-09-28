"""embedding 的真实 HTTP 路径第一次被执行（E20）。

E18 收了 LLM 那半，这半是 `EMBEDDING_PROVIDER`：`conftest` 把它钉成 mock，所以
`_openai_embed`（`embedding_service.py:323-355`）里 `requests.post` 那一段在 764 条测试里
**一行都没执行过**——覆盖率报的是 missing `325-355`（整个函数体）外加 dispatch 的 `482-485`。
这里接的不是真 provider（要花钱、也没批），而是一个本地 OpenAI 兼容假服务：跑的是生产同一段
客户端代码，包括 `requests` 的真实 socket。
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.core.config import settings
from app.services import embedding_service
from app.services.embedding_service import EmbeddingAuthError, EmbeddingProviderError


class FakeEmbeddingProvider:
    """按队列回答；队列耗尽后重复最后一条（"每次都失败"因此是默认行为）。"""

    def __init__(self) -> None:
        self.responses: list[tuple[int, dict]] = []
        self.requests: list[dict] = []
        self.sleep_seconds = 0.0

    def next(self) -> tuple[int, dict]:
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

    @staticmethod
    def vector(seed: int) -> list[float]:
        return [float(seed) / 10.0, 0.5, 0.25]

    @staticmethod
    def ok(start: int = 0, count: int = 1) -> tuple[int, dict]:
        rows = [{"index": i, "embedding": FakeEmbeddingProvider.vector(i + start)} for i in range(start, start + count)]
        return 200, {"data": rows, "model": "configured-embed-model"}


@pytest.fixture
def provider(db_session):
    """假服务 + 把 settings 换成 openai 兼容形态；`db_session` 是给 embedding 统计用的库。"""
    fake = FakeEmbeddingProvider()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            fake.requests.append({"path": self.path, "auth": self.headers.get("authorization"), "body": body})
            if fake.sleep_seconds:
                time.sleep(fake.sleep_seconds)
            status, payload = fake.next()
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            with contextlib.suppress(OSError):
                self.wfile.write(data)  # 客户端可能已超时断开（WinError 10053）

        def log_message(self, *args):  # 静音
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    embedding_service.clear_embed_cache()
    saved = {
        name: getattr(settings, name)
        for name in (
            "EMBEDDING_PROVIDER",
            "EMBEDDING_API_KEY",
            "EMBEDDING_BASE_URL",
            "EMBEDDING_MODEL",
            "EMBEDDING_TIMEOUT",
            "EMBEDDING_MAX_RETRIES",
            "LLM_API_KEY",
        )
    }
    settings.EMBEDDING_PROVIDER = "openai"
    settings.EMBEDDING_API_KEY = "sk-embed-local"
    settings.EMBEDDING_BASE_URL = f"http://127.0.0.1:{server.server_address[1]}/v1"
    settings.EMBEDDING_MODEL = "configured-embed-model"
    settings.EMBEDDING_MAX_RETRIES = 0
    try:
        yield fake
    finally:
        for name, value in saved.items():
            setattr(settings, name, value)
        embedding_service.clear_embed_cache()
        server.shutdown()
        server.server_close()


def _ok_response(count: int, start: int = 0):
    return FakeEmbeddingProvider.ok(start=start, count=count)


def test_the_openai_embedding_request_contract(provider):
    """URL 拼接、鉴权头、请求体形状、模型名取配置值——这四件事以前只是写在代码里。"""
    provider.responses = [_ok_response(2)]

    vectors = embedding_service.embed_texts(["第一段", "第二段"])

    assert len(provider.requests) == 1
    sent = provider.requests[0]
    assert sent["path"] == "/v1/embeddings"
    assert sent["auth"] == "Bearer sk-embed-local"
    assert sent["body"]["model"] == "configured-embed-model"
    assert sent["body"]["input"] == ["第一段", "第二段"]
    assert vectors == [[0.0, 0.5, 0.25], [0.1, 0.5, 0.25]]


def test_out_of_order_index_is_reordered_back_to_input_order(provider):
    """响应里的 `data[].index` 乱序返回时，必须按 index 排回输入顺序（`sorted(..., key=index)`）。
    不排就会把第 2 段的向量安到第 1 段头上——这种错位不报错，只会静默毁掉召回。"""
    provider.responses = [
        (
            200,
            {
                "data": [
                    {"index": 1, "embedding": [9.0, 9.0]},
                    {"index": 0, "embedding": [1.0, 1.0]},
                ]
            },
        )
    ]

    vectors = embedding_service.embed_texts(["甲", "乙"])

    assert vectors == [[1.0, 1.0], [9.0, 9.0]], "响应顺序被当成输入顺序用了"


def test_more_than_the_batch_cap_is_split_instead_of_failing(provider):
    """`_EMBED_BATCH_SIZE=10` 是 dashscope 的单次上限（文档里写的理由），网络型 provider 统一走它。
    12 条必须变成 2 次请求，且切分顺序保持。"""

    def respond(start_hint: int, count: int):
        return 200, {"data": [{"index": i, "embedding": [float(i + start_hint)]} for i in range(count)]}

    # 两批发回去：第一批 10 条、第二批 2 条，各按自己的起始下标回向量
    provider.responses = [respond(0, 10), respond(10, 2)]
    texts = [f"t{i}" for i in range(12)]

    vectors = embedding_service.embed_texts(texts)

    assert [len(r["body"]["input"]) for r in provider.requests] == [10, 2], "没有按 10 条一批切"
    assert provider.requests[1]["body"]["input"] == ["t10", "t11"]
    assert len(vectors) == 12
    # 跨批次回填必须按下标走（`missing_indices[idx]`）：第 11 条的向量不能是第 1 批的第 1 条
    assert vectors[10] == [10.0] and vectors[11] == [11.0]


def test_no_api_key_fails_before_touching_the_socket(provider):
    """没配 key 是配置错误，不该发出请求、也不该被退避重试成一次网络故障。"""
    settings.EMBEDDING_API_KEY = ""
    settings.LLM_API_KEY = ""
    provider.responses = [_ok_response(1)]

    with pytest.raises(EmbeddingAuthError) as info:
        embedding_service.embed_texts(["缺 key 也要报对"])

    assert provider.requests == [], "没 key 也发出了请求"
    assert "EMBEDDING_API_KEY" in str(info.value)


def test_5xx_is_retried_and_the_last_error_is_reported(provider):
    """5xx 是瞬时故障：默认 `EMBEDDING_MAX_RETRIES=2` 时应该发 3 次，全失败才报错。"""
    settings.EMBEDDING_MAX_RETRIES = 1
    provider.responses = [(500, {"error": "boom"})]

    with pytest.raises(EmbeddingProviderError) as info:
        embedding_service.embed_texts(["5xx 场景"])

    assert len(provider.requests) == 2, "5xx 属可重试类，至少要发过两次"
    assert "Embedding" in str(info.value) or "500" in str(info.value)


def test_a_401_is_not_retried_and_keeps_its_own_class(provider):
    """鉴权失败重试没有意义：多花的每一发都是一次退避 + 一次真 socket，而且退化成
    `EmbeddingProviderError` 之后，运维看到的错误分类是错的（401 记成通用 provider 故障）。
    """
    settings.EMBEDDING_MAX_RETRIES = 2
    provider.responses = [(401, {"error": "bad key"})]

    with pytest.raises(EmbeddingAuthError) as info:
        embedding_service.embed_texts(["401 场景"])

    assert len(provider.requests) == 1, f"鉴权失败被重试了 {len(provider.requests)} 次"
    assert type(info.value) is EmbeddingAuthError, f"异常类型退化成了 {type(info.value).__name__}"


def test_the_timeout_floor_is_five_seconds_not_the_configured_value(provider):
    """`timeout=max(5, settings.EMBEDDING_TIMEOUT)`：配 1 秒实际给 requests 的是 5 秒。
    这条把那个下限钉成事实——慢 1.6 秒的请求在"配 1 秒"的口径下本该超时，实际没有。"""
    settings.EMBEDDING_TIMEOUT = 1
    settings.EMBEDDING_MAX_RETRIES = 0
    provider.sleep_seconds = 1.6
    provider.responses = [_ok_response(1)]

    vectors = embedding_service.embed_texts(["慢一点但别超时"])

    provider.sleep_seconds = 0.0
    assert vectors == [[0.0, 0.5, 0.25]]
    assert len(provider.requests) == 1
