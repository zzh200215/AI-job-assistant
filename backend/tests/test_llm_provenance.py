"""A1: every LLM response must report where it actually came from.

Guards the two silent-corruption paths that existed before: mock replies were
cached under real-looking keys, and `prompt_trace.provider` recorded the
*configured* provider so a fabricated answer was indistinguishable from a model
answer in the audit trail.
"""

from __future__ import annotations

import pytest

from app.services import llm_service, prompt_trace_service

PROBE_PROMPT = "provenance-probe"


class FakeResponse:
    def __init__(self, content, usage=None):
        self._content = content
        self._usage = usage

    def raise_for_status(self):
        if self._content is None:
            raise llm_service.requests.HTTPError("boom")

    def json(self):
        payload = {"choices": [{"message": {"content": self._content}}]}
        if self._usage:
            payload["usage"] = self._usage
        return payload


@pytest.fixture
def trace_kwargs(monkeypatch):
    """Capture what chat_json would have persisted, without touching a DB."""
    captured: list[dict] = []
    monkeypatch.setattr(prompt_trace_service, "record_prompt_trace", lambda **kw: captured.append(kw))
    llm_service.clear_llm_cache()
    llm_service.reset_llm_provenance()
    yield captured
    llm_service.clear_llm_cache()


def _use_mock_provider(monkeypatch, payload: str):
    monkeypatch.setattr(llm_service.settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(llm_service, "_mock_chat", lambda prompt: payload)


def _use_openai(monkeypatch, responder):
    monkeypatch.setattr(llm_service.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_service.settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(llm_service.settings, "LLM_MODEL", "primary-model")
    monkeypatch.setattr(llm_service, "_openai_compatible_chat", responder)


# ---------------------------------------------------------------- mock provider


def test_mock_provider_reports_mock_not_real(trace_kwargs, monkeypatch):
    _use_mock_provider(monkeypatch, '{"ok": true}')

    assert llm_service.chat_json(PROBE_PROMPT) == {"ok": True}

    provenance = llm_service.get_llm_provenance()
    assert provenance["source"] == "mock"
    assert provenance["degraded"] is True
    assert trace_kwargs[-1]["response_source"] == "mock"
    assert trace_kwargs[-1]["degraded"] is True


def test_mock_answers_are_never_cached(trace_kwargs, monkeypatch):
    """Regression: mock content used to be pinned under a real-looking key."""
    calls = {"n": 0}

    def counting_mock(prompt: str) -> str:
        calls["n"] += 1
        return '{"ok": true}'

    monkeypatch.setattr(llm_service.settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(llm_service, "_mock_chat", counting_mock)

    llm_service.chat_json(PROBE_PROMPT)
    llm_service.chat_json(PROBE_PROMPT)

    assert calls["n"] == 2, "mock reply was served from cache on the second call"
    assert llm_service._LLM_CACHE == {}, "mock result must not enter the LLM cache"


# ------------------------------------------------------------------- real path


def test_real_answer_is_cached_and_hit_reports_cache_hit(trace_kwargs, monkeypatch):
    posts = {"n": 0}

    def responder(prompt, base_url=None, *, json_mode=True, model=None):
        posts["n"] += 1
        return '{"ok": true}'

    _use_openai(monkeypatch, responder)

    assert llm_service.chat_json(PROBE_PROMPT) == {"ok": True}
    assert llm_service.get_llm_provenance()["source"] == "real"
    assert llm_service.get_llm_provenance()["degraded"] is False

    assert llm_service.chat_json(PROBE_PROMPT) == {"ok": True}
    hit = llm_service.get_llm_provenance()
    assert posts["n"] == 1, "second call should have been served from cache"
    assert hit["source"] == "real"
    assert hit["cache_hit"] is True
    assert hit["degraded"] is False, "a cached real answer is not degraded"


def test_fallback_model_attempt_is_labelled(trace_kwargs, monkeypatch):
    seen: list[str | None] = []

    def responder(prompt, base_url=None, *, json_mode=True, model=None):
        seen.append(model)
        if model is None:
            raise llm_service.LLMProviderError("primary down")
        return '{"via": "fallback"}'

    monkeypatch.setattr(llm_service.settings, "LLM_FALLBACK_MODEL", "secondary-model")
    _use_openai(monkeypatch, responder)

    assert llm_service.chat_json(PROBE_PROMPT) == {"via": "fallback"}
    assert seen == [None, "secondary-model"]

    provenance = llm_service.get_llm_provenance()
    assert provenance["source"] == "fallback_model"
    assert provenance["degraded"] is True
    assert "primary down" in provenance["reason"]
    assert llm_service._LLM_CACHE == {}, "fallback_model answers must not be cached"


def test_truncated_attempt_is_labelled(trace_kwargs, monkeypatch):
    truncation_marker = "以下输入已因上游 LLM 调用失败而自动截断"

    def responder(prompt, base_url=None, *, json_mode=True, model=None):
        # Only the simplified (truncated) re-ask is allowed to succeed.
        if truncation_marker not in prompt:
            raise llm_service.LLMProviderError("primary rejected the long prompt")
        return '{"via": "truncated"}'

    monkeypatch.setattr(llm_service.settings, "LLM_FALLBACK_MODEL", "")
    _use_openai(monkeypatch, responder)

    long_prompt = "x" * (llm_service._SIMPLIFIED_PROMPT_MAX_CHARS + 500)
    assert llm_service.chat_json(long_prompt) == {"via": "truncated"}

    provenance = llm_service.get_llm_provenance()
    assert provenance["source"] == "truncated"
    assert provenance["degraded"] is True
    assert llm_service._LLM_CACHE == {}, "truncated answers must not be cached"


def test_mock_fallback_after_real_failures_is_labelled_mock(trace_kwargs, monkeypatch):
    def responder(prompt, base_url=None, *, json_mode=True, model=None):
        raise llm_service.LLMProviderError("all models down")

    monkeypatch.setattr(llm_service.settings, "LLM_ALLOW_MOCK_FALLBACK", True)
    monkeypatch.setattr(llm_service.settings, "LLM_FALLBACK_MODEL", "")
    monkeypatch.setattr(llm_service, "_mock_chat", lambda prompt: '{"ok": "mock"}')
    _use_openai(monkeypatch, responder)

    assert llm_service.chat_json(PROBE_PROMPT) == {"ok": "mock"}

    provenance = llm_service.get_llm_provenance()
    assert provenance["source"] == "mock", "mock fallback must never be reported as real"
    assert trace_kwargs[-1]["provider"] == "openai"
    assert trace_kwargs[-1]["response_source"] == "mock"
    assert llm_service._LLM_CACHE == {}


def test_exhausted_chain_leaves_no_stale_provenance(trace_kwargs, monkeypatch):
    def responder(prompt, base_url=None, *, json_mode=True, model=None):
        raise llm_service.LLMProviderError("nothing works")

    monkeypatch.setattr(llm_service.settings, "LLM_ALLOW_MOCK_FALLBACK", False)
    monkeypatch.setattr(llm_service.settings, "LLM_FALLBACK_MODEL", "")
    _use_openai(monkeypatch, responder)

    with pytest.raises(llm_service.LLMProviderError):
        llm_service.chat_json(PROBE_PROMPT)

    assert llm_service.get_llm_provenance()["source"] == "unknown"


# ------------------------------------------------------------------ tool path


def test_chat_with_tools_records_usage(trace_kwargs, monkeypatch):
    """The tool path previously spent tokens without ever billing them."""
    monkeypatch.setattr(llm_service.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_service.settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(llm_service.settings, "LLM_INPUT_COST_PER_1K_CENTS", 1.0)
    monkeypatch.setattr(llm_service.settings, "LLM_OUTPUT_COST_PER_1K_CENTS", 2.0)
    monkeypatch.setattr(
        llm_service.requests,
        "post",
        lambda *a, **kw: FakeResponse(
            '{"done": true}',
            usage={"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
        ),
    )
    llm_service.reset_llm_usage()

    assert llm_service.chat_with_tools("tool-probe") == {"done": True}

    usage = llm_service.get_llm_usage()
    assert usage["total_tokens"] == 1500
    assert usage["cost_cents"] == 2.0


def test_chat_with_tools_mock_degrade_is_labelled(trace_kwargs, monkeypatch):
    _use_mock_provider(monkeypatch, '{"ok": "mock"}')

    assert llm_service.chat_with_tools("tool-probe") == {"ok": "mock"}

    provenance = llm_service.get_llm_provenance()
    assert provenance["source"] == "mock"
    assert "工具调用" in provenance["reason"]
