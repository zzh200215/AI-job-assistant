"""D179：LLM 与向量化分属两家时，embedding 的 key/base 必须显式钉住——这条今天真撞过。

现量经过：把 LLM 从 dashscope（`qwen-turbo`，额度耗尽）换到另一家 OpenAI 兼容供应商时，
`backend/.env` 里原来只有 `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` 两行，key 与 base 都是空的——
`embedding_service.py:317/333/337` 写的是 `EMBEDDING_API_KEY or LLM_API_KEY`、
`EMBEDDING_BASE_URL or LLM_BASE_URL`。于是"向量化那一档不动"这句在代码上做不到：换了 LLM key，
向量化会跟着去新供应商找 `text-embedding-v3`（那家的 `/models` 现量 7 个 ID 全是生成侧，没有向量模型），
RAG 整条静默挂掉。这条守卫把它变成启动时就说话。
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
