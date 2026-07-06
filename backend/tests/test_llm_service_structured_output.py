# -*- coding: utf-8 -*-
from __future__ import annotations

from pydantic import BaseModel, Field

from app.services import llm_service


class TinyResult(BaseModel):
    score: int = Field(..., ge=0, le=100)
    label: str


def test_chat_json_validates_optional_pydantic_schema(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(llm_service, "_mock_chat", lambda prompt: '{"score": 88, "label": "ok"}')
    llm_service.clear_llm_cache()

    result = llm_service.chat_json("structured", schema=TinyResult)

    assert result == {"score": 88, "label": "ok"}


def test_chat_json_rejects_schema_violations(monkeypatch):
    monkeypatch.setattr(llm_service.settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(llm_service, "_mock_chat", lambda prompt: '{"score": 188, "label": "bad"}')
    llm_service.clear_llm_cache()

    try:
        llm_service.chat_json("structured-invalid", schema=TinyResult)
    except ValueError as exc:
        assert "schema 校验" in str(exc)
    else:
        raise AssertionError("schema violation should raise ValueError")


def test_usage_cost_accumulates_from_openai_compatible_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
            }

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["payload"] = json
        return FakeResponse()

    monkeypatch.setattr(llm_service.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_service.settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(llm_service.settings, "LLM_INPUT_COST_PER_1K_CENTS", 1.0)
    monkeypatch.setattr(llm_service.settings, "LLM_OUTPUT_COST_PER_1K_CENTS", 2.0)
    monkeypatch.setattr(llm_service.requests, "post", fake_post)
    llm_service.clear_llm_cache()
    llm_service.reset_llm_usage()

    assert llm_service.chat_json("usage-test") == {"ok": True}
    usage = llm_service.get_llm_usage()

    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert usage["total_tokens"] == 1500
    assert usage["cost_cents"] == 2.0


def test_chat_json_falls_back_to_configured_model(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, content):
            self._content = content

        def raise_for_status(self):
            if self._content is None:
                raise llm_service.requests.HTTPError("rate limited")

        def json(self):
            return {"choices": [{"message": {"content": '{"fallback": true}'}}]}

    def fake_post(url, json, headers, timeout):
        calls.append(json["model"])
        if len(calls) == 1:
            return FakeResponse(None)
        return FakeResponse("ok")

    monkeypatch.setattr(llm_service.settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(llm_service.settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(llm_service.settings, "LLM_MODEL", "primary-model")
    monkeypatch.setattr(llm_service.settings, "LLM_FALLBACK_MODEL", "fallback-model")
    monkeypatch.setattr(llm_service.requests, "post", fake_post)
    llm_service.clear_llm_cache()

    assert llm_service.chat_json("fallback-test") == {"fallback": True}
    assert calls == ["primary-model", "fallback-model"]
