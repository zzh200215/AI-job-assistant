"""启动期的两条"供应商形状"守卫（D179/D181 那条 embedding 回退 + D184 那条 LLM 端点）。

**为什么两条放一个文件**：它们判的是同一件事——`LLM_*` 与 `EMBEDDING_*` 这几行配错时，
坏的不是某一次请求，而是"整条链静默走错端点"。分开两个文件就会各测各的，而真正会同时
踩到它们的是同一个人、同一次改配置。

embedding 那一条的起因（2026-10-09 真撞）：`embedding_service.py` 里是
`EMBEDDING_API_KEY or LLM_API_KEY`、`EMBEDDING_BASE_URL or LLM_BASE_URL`。把 LLM 从 dashscope
换到另一家 OpenAI 兼容供应商时，如果只改 `LLM_*`，向量化会跟着去新供应商找 `text-embedding-v3`
（那家 `/models` 现量 7 个 ID 全是生成侧，没有向量模型），RAG 整条静默挂掉。
LLM 端点那一条是同一次切换的另一半：`openai` 这个值从此只表示"走兼容协议"，
留空 `LLM_BASE_URL` 会静默打到 `api.openai.com`。
"""

from __future__ import annotations

import logging

import pytest

from app.core.config import Settings

PROD_BASE = {
    "APP_ENV": "production",
    "APP_DEBUG": False,
    "AUTO_CREATE_TABLES": False,
    "JWT_SECRET": "x" * 40,
    "MYSQL_PASSWORD": "not-a-weak-password",
    "LLM_PROVIDER": "openai",
    "LLM_API_KEY": "sk-new-vendor",
    "LLM_BASE_URL": "https://token.sensenova.cn/v1",
    "LLM_MODEL": "deepseek-v4-flash",
    "EMBEDDING_PROVIDER": "qwen",
    "EMBEDDING_MODEL": "text-embedding-v3",
}


def _settings(**over):
    """每个字段都显式给，别让本机 `backend/.env` 混进判据。"""
    payload = dict(PROD_BASE)
    payload.update(over)
    payload.setdefault("EMBEDDING_API_KEY", "")
    payload.setdefault("EMBEDDING_BASE_URL", "")
    return Settings(**payload)


def test_production_refuses_an_embedding_that_would_silently_follow_the_llm_vendor():
    with pytest.raises(ValueError) as caught:
        _settings()
    message = str(caught.value)
    assert (
        "EMBEDDING_API_KEY" in message and "EMBEDDING_BASE_URL" in message
    ), f"两条都缺时要把两条都点名，只点一条会误导：{message}"
    assert "sensenova" not in message  # 判据不许把具体供应商写死进报错


def test_only_the_missing_line_is_named():
    with pytest.raises(ValueError) as caught:
        _settings(EMBEDDING_API_KEY="sk-dashscope-key")
    message = str(caught.value)
    assert "EMBEDDING_BASE_URL" in message
    assert "EMBEDDING_API_KEY" not in message, f"key 已经配了还点名它，报错在说谎：{message}"


def test_pinning_both_lines_is_accepted_in_production():
    ok = _settings(
        EMBEDDING_API_KEY="sk-dashscope-key", EMBEDDING_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert ok.EMBEDDING_BASE_URL.endswith("/v1")


def test_one_vendor_on_both_sides_needs_nothing_extra():
    same = _settings(LLM_PROVIDER="qwen", EMBEDDING_PROVIDER="qwen", LLM_MODEL="qwen-turbo")
    assert same.EMBEDDING_PROVIDER == "qwen"


# ---- 下面三条是 D181 补的：D179 那版一刀切，把三种合法/半合法配置一起误杀了 ----


def test_dashscope_embedding_does_not_need_a_base_url():
    """`EMBEDDING_PROVIDER=dashscope` 走阿里云 SDK（`_dashscope_embed:306-319`），不读 base_url。

    D179 那版要求"两家不同就必须钉 base_url"，于是这份合法配置在生产直接起不来。
    """
    ok = _settings(EMBEDDING_PROVIDER="dashscope", EMBEDDING_API_KEY="sk-aliyun-key", EMBEDDING_BASE_URL="")
    assert ok.EMBEDDING_PROVIDER == "dashscope"


def test_same_vendor_under_two_names_is_not_a_split():
    """`qwen` 与 `dashscope` 都是阿里云、同一把 key —— 家族相同就不该拦。"""
    ok = _settings(LLM_PROVIDER="qwen", EMBEDDING_PROVIDER="dashscope", EMBEDDING_API_KEY="", EMBEDDING_BASE_URL="")
    assert ok.LLM_PROVIDER == "qwen"


def test_cross_family_still_refuses_a_borrowed_key_on_the_sdk_path():
    """跨家族时 SDK 那一支仍然要显式 key——但**只点 key**，不冤枉那个它用不到的 base_url。"""
    with pytest.raises(ValueError) as caught:
        _settings(EMBEDDING_PROVIDER="dashscope", EMBEDDING_API_KEY="", EMBEDDING_BASE_URL="")
    message = str(caught.value)
    assert "EMBEDDING_API_KEY" in message
    assert "EMBEDDING_BASE_URL" not in message, f"dashscope 不读 base_url，点它是误导：{message}"
    assert "SDK" in message or "密钥" in message


def test_production_refuses_a_network_llm_without_an_explicit_endpoint():
    """2026-10-09 换供应商之后，`openai` 只表示"走 OpenAI 兼容协议"，不再等于"用 OpenAI 的端点"。

    留空 `LLM_BASE_URL` 会静默落到代码里的 `api.openai.com` 默认值 ⇒ 新供应商的 key 被发给旧端点，
    每次调用都 401；而 `/api/system` 那一格只看 `bool(api_key)`（`api/system.py:86-88`），
    管理员面板上仍然写着 "Configured"。所以这条必须在启动时就拒绝。
    """
    with pytest.raises(ValueError) as caught:
        _settings(LLM_BASE_URL="")
    assert "LLM_BASE_URL" in str(caught.value)


def test_the_shipped_production_example_still_boots():
    """新守卫不许把**文档里那条路**堵死：`.env.production.example` 的 provider 行必须能启动。

    D181 刚教过我一课——守卫写进生产启动路径之后，第一件事是量它会不会误杀合法配置。
    这里不复制值（复制就会漂），直接把 example 里的 provider 相关行读进来。
    """
    from pathlib import Path

    lines = (Path(__file__).resolve().parents[2] / ".env.production.example").read_text(encoding="utf-8").splitlines()
    provider = {}
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key.startswith(("LLM_", "EMBEDDING_")):
            provider[key] = line.split("=", 1)[1].strip()
    assert provider.get("LLM_BASE_URL"), "example 里 LLM_BASE_URL 没了——这条测试的锚点要重取"

    ok = _settings(**provider)
    assert provider["LLM_PROVIDER"] == ok.LLM_PROVIDER
    assert provider["LLM_BASE_URL"] == ok.LLM_BASE_URL


def test_production_refuses_a_mock_llm_and_that_is_a_different_rule():
    """生产不许把 LLM 配成 `mock`——这条早就在，但从没被测过（本条补上）。

    **这条的边界要写清楚，别把它当成端点判据的守卫**：变异 W2 把 `mock` 加进端点判据的
    provider 集合里，本条**照样绿**——因为 `mock` 先被前面那条判据拒了，端点那条根本走不到它。
    所以它钉的是"抛的是哪条规则的话"，不钉端点判据的射程；端点判据的红绿由
    `test_production_refuses_a_network_llm_without_an_explicit_endpoint` 与变异 W1 负责。
    """
    with pytest.raises(ValueError) as caught:
        _settings(LLM_PROVIDER="mock", LLM_API_KEY="", LLM_BASE_URL="")
    message = str(caught.value)
    assert "mock" in message
    assert "LLM_BASE_URL" not in message


def test_development_warns_instead_of_refusing_the_same_shape(caplog):
    # 两行必须显式给空串：不写就会从本机 `backend/.env` 读到真值，判据当场变成数空气
    # （这条第一版就是这么"通过"了 raise 那几条、却在 warning 这条上红的）。
    dev = dict(
        PROD_BASE,
        APP_ENV="development",
        AUTO_CREATE_TABLES=True,
        APP_DEBUG=True,
        EMBEDDING_API_KEY="",
        EMBEDDING_BASE_URL="",
    )
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        Settings(**dev)
    assert any(
        "EMBEDDING_BASE_URL" in r.getMessage() for r in caplog.records
    ), "开发机上换供应商是常态，不该硬挡——但必须留话，否则又是静默挂 RAG"
